from __future__ import annotations

from app.models import ToolCall


def test_command_returns_structured_metadata(client, monkeypatch):
    def fake_run_magic(*args, **kwargs):
        return (
            [ToolCall(tool="workspace_write", input='{"path":"demo.txt","content":"hello"}', reason="write file")],
            ["workspace_write -> Wrote demo.txt\nPrimary file: demo.txt"],
            "Done. Created the file and it is ready.",
            ["Analyzed request", "Wrote file", "Final response ready"],
            "edit_existing_project",
            [{
                "ok": True,
                "tool": "workspace_write",
                "output": "Wrote demo.txt",
                "summary": "Wrote file demo.txt",
                "files_changed": ["demo.txt"],
                "opened_file": "demo.txt",
                "preview_url": None,
                "commands_run": [],
                "run_logs": [],
                "verification_results": [],
                "sources": [],
                "errors": [],
                "requires_confirmation": False,
                "metadata": {},
            }],
        )

    monkeypatch.setattr("app.main.run_magic", fake_run_magic)
    response = client.post(
        "/v1/command",
        json={
            "command": "create demo file",
            "developer_mode": True,
            "reasoning_level": "easy",
            "approval_mode": "auto_apply",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "edit_existing_project"
    assert data["files_changed"] == ["demo.txt"]
    assert data["opened_file"] == "demo.txt"
    assert data["used_tools"] is True
    assert data["tool_results"][0]["tool"] == "workspace_write"


def test_command_stream_emits_trace_and_final_events(client, monkeypatch):
    def fake_run_magic(*args, **kwargs):
        return (
            [ToolCall(tool="final_answer", input="", reason="done")],
            [],
            "Stream finished cleanly.",
            ["Analyzed request", "Final response ready"],
            "chat",
            [],
        )

    monkeypatch.setattr("app.main.run_magic", fake_run_magic)
    with client.stream(
        "POST",
        "/v1/command/stream",
        json={"command": "say hi", "developer_mode": False, "reasoning_level": "easy"},
    ) as response:
        body = "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in response.iter_text())
    assert response.status_code == 200
    assert "event: trace" in body
    assert "event: final" in body
    assert "Stream finished cleanly." in body
