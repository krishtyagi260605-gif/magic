def test_health(client):
    """Verify the core health liveness endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_status_fallback_readiness(client):
    """Verify that the status endpoint correctly exposes the fallback chain."""
    response = client.get("/v1/status")
    assert response.status_code == 200
    data = response.json()
    assert "fallback" in data
    assert "primary_provider" in data["fallback"]
    assert "configured_providers" in data["fallback"]
    assert "ready_providers" in data["fallback"]
    assert "last_provider_used" in data["fallback"]
    assert "last_fallback_used" in data["fallback"]