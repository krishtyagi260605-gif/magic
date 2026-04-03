from unittest import mock

@mock.patch("app.graph._invoke_llm")
@mock.patch("app.graph._choose_next_action")
def test_approval_flow_accept_and_reject(mock_choose, mock_invoke, client):
    """Test that destructive tools get paused, queued for approval, and can be resolved."""
    mock_invoke.side_effect = [
        '{"intent": "edit_project", "mode": "act", "reason": "edit file"}',
        "Analyzed"
    ]
    # Force a destructive tool call
    mock_choose.side_effect = [
        {"tool": "workspace_write", "input": '{"path": "test.txt", "content": "hi"}', "reason": "write file"},
        {"tool": "final_answer", "input": "Done writing", "reason": "done"}
    ]
    
    # 1. Test it gets queued in Ask Before Apply mode
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