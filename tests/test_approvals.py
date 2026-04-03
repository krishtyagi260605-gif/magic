from __future__ import annotations

from app.trace import create_approval


def test_approval_create_list_and_resolve(client):
    approval_id = create_approval(
        session_id="session-1",
        tool="workspace_patch",
        payload='{"path":"demo.py"}',
        summary="Patch demo.py",
        risk_level="High",
        diff="--- old\n+++ new",
        files_affected=["demo.py"],
    )

    listed = client.get("/v1/sessions/session-1/approvals")
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert items[0]["id"] == approval_id
    assert items[0]["status"] == "pending"

    resolved = client.post(f"/v1/approvals/{approval_id}/resolve", json={"action": "approve"})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "approved"


def test_cancel_session_endpoint(client):
    response = client.post("/v1/sessions/session-cancel/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
