from __future__ import annotations

from types import SimpleNamespace

from app.graph import _run_with_retries
from app.sandbox import execute_python_sandbox


def test_sandbox_uses_docker_when_available(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output=True, text=True, timeout=None):
        calls.append(cmd)
        if cmd[:2] == ["docker", "info"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="2\n", stderr="")

    monkeypatch.setattr("app.sandbox.subprocess.run", fake_run)
    result = execute_python_sandbox("print(1+1)")
    assert result["ok"] is True
    assert result["commands_run"]
    assert "docker run" in result["commands_run"][0]


def test_sandbox_falls_back_without_docker(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output=True, text=True, timeout=None):
        calls.append(cmd)
        if cmd[:2] == ["docker", "info"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="no docker")
        return SimpleNamespace(returncode=0, stdout="fallback-ok\n", stderr="")

    monkeypatch.setattr("app.sandbox.subprocess.run", fake_run)
    result = execute_python_sandbox("print('ok')")
    assert result["ok"] is True
    assert result["commands_run"] == ["python3 script.py"]


def test_run_with_retries_sets_fallback_provider(monkeypatch):
    attempts = {"google": 0, "openai": 0}

    def fake_func(provider):
        attempts[provider] += 1
        if provider == "google":
            raise RuntimeError("google down")
        return f"success:{provider}"

    monkeypatch.setattr("app.graph.append_trace", lambda *args, **kwargs: None)
    result = _run_with_retries(fake_func, session_id="trace-session", timeout=1)
    assert result == "success:openai"
