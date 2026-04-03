from unittest import mock

@mock.patch("app.graph._invoke_llm")
def test_simple_chat_flow(mock_invoke, client):
    """Test that a basic 'reply' intent bypasses execution and goes to the chat synthesizer."""
    mock_invoke.side_effect = [
        '{"intent": "chat", "mode": "reply", "reason": "user is chatting"}',
        "Hello from the mocked Magic assistant!"
    ]
    
    res = client.post("/v1/command", json={"command": "Say hello", "execute": True, "reasoning_level": "easy"})
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "chat"
    assert "mocked Magic" in data["final"]
    assert len(data["plan"]) == 1
    assert data["plan"][0]["tool"] == "final_answer"

@mock.patch("app.graph._invoke_llm")
def test_sisi_selection_action(mock_invoke, client):
    """Test that Sisi's IDE context is injected properly into the LLM flow."""
    mock_invoke.side_effect = [
        '{"intent": "code_generation", "mode": "act", "reason": "edit code"}',
        "Analysis complete.",
    ]
    
    cmd = "Refactor and improve this code from index.js (lines 1-5):\n\n```\nconsole.log('hi');\n```"
    res = client.post("/v1/command", json={"command": cmd, "execute": False, "app_mode": "sisi"})
    assert res.status_code == 200

def test_cancellation(client):
    """Verify backend session cancellation registers correctly with LangGraph states."""
    session_id = "test-cancel-session-id"
    res = client.post(f"/v1/sessions/{session_id}/cancel")
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"
    
    from app.graph import is_cancelled
    assert is_cancelled(session_id) is True