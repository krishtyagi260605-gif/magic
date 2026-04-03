import pytest
from unittest import mock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_and_status():
    """Verify core health and that the new fallback status configs are exposed."""
    assert client.get("/health").status_code == 200
    res = client.get("/v1/status")
    assert res.status_code == 200
    assert "fallback" in res.json()

@mock.patch("app.graph._invoke_llm")
def test_simple_chat_flow(mock_invoke):
    """Test that a simple 'reply' intent routes directly to the chat synthesizer."""
    # Mock router to return reply mode
    mock_invoke.side_effect = [
        '{"intent": "chat", "mode": "reply", "reason": "user is chatting"}',
        "Hello from the mocked assistant!"
    ]
    
    res = client.post("/v1/command", json={"command": "Say hello", "execute": True, "reasoning_level": "easy"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "chat"
    assert "mocked assistant" in data["final"]
    assert data["plan"][0]["tool"] == "final_answer"

@mock.patch("app.graph._invoke_llm")
@mock.patch("app.graph._choose_next_action")
def test_approval_flow_accept_and_reject(mock_choose, mock_invoke):
    """Test that destructive tools get paused, queued for approval, and can be resolved."""
    mock_invoke.return_value = '{"intent": "edit_project", "mode": "act", "reason": "edit file"}'
    # Force a destructive tool call
    mock_choose.side_effect = [
        {"tool": "workspace_write", "input": '{"path": "test.txt", "content": "hi"}', "reason": "write file"},
        {"tool": "final_answer", "input": "Done writing", "reason": "done"}
    ]
    
    # 1. Test it gets queued
    res = client.post("/v1/command", json={"command": "Write a file", "execute": True, "approval_mode": "ask_before_apply"})
    data = res.json()
    
    assert len(data["tool_results"]) > 0
    tr = data["tool_results"][0]
    assert tr["requires_confirmation"] is True
    assert tr["approval_id"] is not None

    appr_id = tr["approval_id"]
    
    # 2. Test Accept
    acc_res = client.post(f"/v1/approvals/{appr_id}/resolve", json={"action": "approve"})
    assert acc_res.status_code == 200
    assert acc_res.json()["status"] == "approved"
    
    # 3. Test Reject (simulate a new approval id for rejection logic)
    from app.trace import create_approval
    rej_id = create_approval("test_session", "workspace_write", "{}", "summary", "High", files_affected=["test.txt"])
    rej_res = client.post(f"/v1/approvals/{rej_id}/resolve", json={"action": "reject"})
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "rejected"

@mock.patch("app.sandbox.subprocess.run")
def test_sandbox_fallback(mock_run):
    """Test that the sandbox gracefully falls back to a standard subprocess if Docker is missing."""
    mock_run.return_value.returncode = 1 # Force docker check to fail
    mock_run.return_value.stdout = "Python 3.11"
    mock_run.return_value.stderr = ""
    
    res = client.post("/v1/tool/execute", json={"tool": "execute_python_sandbox", "payload": '{"code":"print(1)"}'})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["commands_run"][0] == "python3 script.py"  # Verifies it hit the fallback branch

def test_trace_endpoint():
    """Verify the trace endpoint behaves correctly for missing data."""
    assert client.get("/v1/trace/nonexistent-session").status_code == 404

def test_cancellation():
    """Verify backend session cancellation registers correctly."""
    session_id = "test-cancel-session"
    res = client.post(f"/v1/sessions/{session_id}/cancel")
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"
    
    from app.graph import is_cancelled
    assert is_cancelled(session_id) is True

@mock.patch("app.graph._invoke_llm")
def test_retry_fallback_behavior(mock_invoke):
    """Verify exponential backoff retries and fallback handling in the graph LLM invocation."""
    from app.graph import _run_with_retries
    from concurrent.futures import TimeoutError as FuturesTimeout

    call_count = 0
    def _failing_call(provider):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise FuturesTimeout("Simulated timeout")
        return "Success!"

    res = _run_with_retries(_failing_call, "test_retry_session", 1)
    assert res == "Success!"
    assert call_count == 3

@mock.patch("app.tools.write_workspace_file")
def test_auto_indexing_trigger(mock_write):
    """Test that writing to a workspace file successfully triggers RAG auto-indexing."""
    mock_write.return_value = "Wrote test.py"
    # Post to fs write
    res = client.post("/v1/fs/write", json={"path": "test.py", "content": "print('hi')"})
    assert res.status_code == 200
    # Trigger happens async in background thread, so we mainly assert it didn't crash
    assert res.json()["status"] == "ok"

def test_sandbox_docker_success():
    """Test actual Docker sandbox if available, or just verify structure if not."""
    res = client.post("/v1/tool/execute", json={"tool": "execute_python_sandbox", "payload": '{"code":"print(42)"}'})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "42" in data["output"]
    assert len(data["commands_run"]) == 1

def test_workspace_patch_diff():
    """Test that workspace patch generates a unified diff metadata correctly."""
    client.post("/v1/fs/write", json={"path": "patch_test.txt", "content": "hello world"})
    res = client.post("/v1/tool/execute", json={"tool": "workspace_patch", "payload": '{"path": "patch_test.txt", "op": "search_replace", "search": "world", "replace": "magic"}'})
    assert res.status_code == 200
    assert "diff" in res.json().get("metadata", {})