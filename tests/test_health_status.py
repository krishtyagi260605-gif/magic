from __future__ import annotations


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_status_reports_fallback_readiness(client):
    response = client.get("/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert data["llm"]["provider"] == "google"
    assert "fallback" in data
    assert "configured_providers" in data["fallback"]
    assert "ready_providers" in data["fallback"]
    assert "last_provider_used" in data["fallback"]
    assert "last_fallback_used" in data["fallback"]
    assert "google" in data["fallback"]["configured_providers"]
