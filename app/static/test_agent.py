import pytest
from unittest import mock
from fastapi.testclient import TestClient
from app.main import app
from app.workspace import workspace_root

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

@mock.patch("app.graph._invoke_llm")
@mock.patch("app.graph._choose_next_action")
def test_scaffold_and_plan_mocked(mock_choose, mock_invoke):
    # Mock the analysis/router
    mock_invoke.return_value = '{"intent": "build_new_app", "mode": "act", "reason": "user wants an app"}'
    
    # Mock the tool caller returning final_answer
    mock_choose.return_value = {"tool": "final_answer", "input": "I have created the scaffold", "reason": "done"}

    payload = {"command": "mock command", "execute": True, "reasoning_level": "easy"}
    res = client.post("/v1/command", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["intent"] == "build_new_app"
    assert "created the scaffold" in data["final"]
    assert len(data["plan"]) == 1

def test_cancellation():
    # Create a session
    session_id = "test-cancel-session"
    response = client.post(f"/v1/sessions/{session_id}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

def test_trace_endpoint():
    session_id = "fake-trace-id"
    response = client.get(f"/v1/trace/{session_id}")
    # Will return 404 because no trace was appended
    assert response.status_code == 404