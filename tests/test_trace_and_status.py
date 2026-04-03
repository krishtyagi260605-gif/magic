from __future__ import annotations

from app.trace import append_trace


def test_trace_endpoint_returns_events(client):
    append_trace("trace-session", "llm_retry", {"attempt": 1, "provider": "google"})
    response = client.get("/v1/trace/trace-session")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "trace-session"
    assert data["events"][0]["type"] == "llm_retry"


def test_status_exposes_last_provider_fields(client):
    response = client.get("/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert "last_provider_used" in data["fallback"]
    assert "last_fallback_used" in data["fallback"]
