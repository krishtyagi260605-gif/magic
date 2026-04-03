from unittest import mock

@mock.patch("app.tools._trigger_index")
def test_write_auto_index(mock_trigger_index, client):
    """Test that writing to a workspace file successfully triggers RAG auto-indexing silently."""
    res = client.post("/v1/fs/write", json={"path": "test_index_trigger.txt", "content": "hello world"})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    mock_trigger_index.assert_called_once()

def test_workspace_patch_diff(client):
    """Test that workspace patch generates unified diff metadata correctly."""
    client.post("/v1/fs/write", json={"path": "patch_test.txt", "content": "hello world"})
    res = client.post("/v1/tool/execute", json={
        "tool": "workspace_patch", 
        "payload": '{"path": "patch_test.txt", "op": "search_replace", "search": "world", "replace": "magic"}'
    })
    assert res.status_code == 200
    assert "diff" in res.json().get("metadata", {})

def test_scaffold_project_artifacts(client):
    """Test scaffold logic returns proper artifacts and files_changed arrays."""
    res = client.post("/v1/tool/execute", json={"tool": "project_scaffold", "payload": '{"name": "test-scaffold", "kind": "website"}'})
    assert res.status_code == 200
    data = res.json()
    assert "test-scaffold" in data["artifacts"]