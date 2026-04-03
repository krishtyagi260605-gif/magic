from __future__ import annotations

from pathlib import Path

from app.tools import run_workspace_patch, run_workspace_write


def test_workspace_write_triggers_index(monkeypatch, isolate_project_state):
    triggered = {"count": 0}

    def fake_trigger():
        triggered["count"] += 1

    monkeypatch.setattr("app.tools._trigger_index", fake_trigger)
    result = run_workspace_write('{"path":"notes.txt","content":"hello world","overwrite":true}', execute=True)
    assert result.ok is True
    assert result.files_changed == ["notes.txt"]
    assert result.opened_file == "notes.txt"
    assert triggered["count"] == 1


def test_workspace_patch_returns_diff_and_triggers_index(monkeypatch, isolate_project_state):
    workspace_dir = isolate_project_state["workspace_dir"]
    target = workspace_dir / "demo.py"
    target.write_text("print('old')\n", encoding="utf-8")

    triggered = {"count": 0}

    def fake_trigger():
        triggered["count"] += 1

    monkeypatch.setattr("app.tools._trigger_index", fake_trigger)
    result = run_workspace_patch(
        '{"path":"demo.py","op":"search_replace","search":"old","replace":"new"}',
        execute=True,
    )
    assert result.ok is True
    assert result.files_changed == ["demo.py"]
    assert result.metadata["diff"]
    assert triggered["count"] == 1
    assert "new" in target.read_text(encoding="utf-8")


def test_memory_query_endpoint(client, monkeypatch):
    monkeypatch.setattr("app.main.query_memory", lambda q: ("Found answer", ["/tmp/source.md"]))
    response = client.get("/v1/memory/query", params={"q": "what is stored"})
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Found answer"
    assert data["sources"] == ["/tmp/source.md"]
