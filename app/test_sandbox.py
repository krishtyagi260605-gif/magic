from unittest import mock

@mock.patch("app.sandbox.subprocess.run")
def test_sandbox_docker_fallback(mock_run, client):
    """Test that the sandbox gracefully falls back to a standard subprocess if Docker is missing."""
    mock_run.return_value.returncode = 1 # Force docker check to fail
    mock_run.return_value.stdout = "Python 3.11"
    mock_run.return_value.stderr = ""
    
    res = client.post("/v1/tool/execute", json={"tool": "execute_python_sandbox", "payload": '{"code":"print(1)"}'})
    assert res.status_code == 200
    assert res.json()["commands_run"][0] == "python3 script.py"  # Verifies it hit the fallback branch

def test_sandbox_docker_success(client):
    """Test actual Docker sandbox if available, or just verify execution structure if not."""
    res = client.post("/v1/tool/execute", json={"tool": "execute_python_sandbox", "payload": '{"code":"print(42)"}'})
    assert res.status_code == 200
    assert "42" in res.json()["output"]