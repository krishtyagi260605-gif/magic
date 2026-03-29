from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.desktop import describe_desktop_op, parse_desktop_payload, run_desktop_op
from app.rag import query_memory as rag_query_memory
from app.search import search_web
from app.workspace import (
    describe_workspace_tree,
    read_workspace_file,
    run_workspace_command,
    scaffold_project,
    workspace_root,
    write_workspace_file,
)


@dataclass
class ToolResult:
    ok: bool
    output: str


def summarize_tool_output(text: str) -> str:
    limit = get_settings().agent_observation_max_chars
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean or "(empty)"
    return clean[: limit - 15].rstrip() + "\n...[truncated]"


def _blocked(message: str) -> ToolResult:
    return ToolResult(ok=False, output=f"BLOCKED: {message}")


def _run_process(args: list[str]) -> ToolResult:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=60)
        out = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode != 0:
            return ToolResult(ok=False, output=out.strip() or f"failed with code {completed.returncode}")
        return ToolResult(ok=True, output=out.strip() or "ok")
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, output=str(exc))


def run_shortcut(shortcut_name: str, execute: bool) -> ToolResult:
    if not shortcut_name.strip():
        return _blocked("shortcut name is empty")
    if not execute:
        return ToolResult(ok=True, output=f"DRY-RUN: shortcuts run {shortcut_name}")
    return _run_process(["shortcuts", "run", shortcut_name.strip()])


def run_applescript(script: str, execute: bool) -> ToolResult:
    if not script.strip():
        return _blocked("applescript is empty")
    if not execute:
        return ToolResult(ok=True, output=f"DRY-RUN: osascript -e {script[:80]}...")
    return _run_process(["osascript", "-e", script])


def run_query_memory(query: str, execute: bool) -> ToolResult:
    """Semantic search over your indexed notes (read-only; always runs)."""
    _ = execute
    text, sources = rag_query_memory(query.strip() or ".")
    if sources:
        src = "\n".join(f"- {s}" for s in sources[:8])
        return ToolResult(ok=True, output=f"{text}\n\nSources:\n{src}")
    return ToolResult(ok=True, output=text)


def run_web_search(query: str, execute: bool) -> ToolResult:
    _ = execute
    text, sources = search_web(query.strip() or ".")
    if sources:
        src = "\n".join(f"- {s}" for s in sources[:8])
        return ToolResult(ok=True, output=f"{text}\n\nSources:\n{src}")
    return ToolResult(ok=True, output=text)


def run_desktop(payload: str, execute: bool) -> ToolResult:
    """Pixel-level mouse/keyboard (PyAutoGUI). Input is JSON: {\"op\":\"click\",\"x\":100,\"y\":200} etc."""
    settings = get_settings()
    if not settings.desktop_automation_enabled:
        return _blocked("Desktop automation disabled (set DESKTOP_AUTOMATION_ENABLED=true)")
    try:
        data = parse_desktop_payload(payload)
    except Exception as exc:  # noqa: BLE001
        return _blocked(f"desktop JSON: {exc}")
    if not execute:
        return ToolResult(ok=True, output=describe_desktop_op(data))
    try:
        out = run_desktop_op(data)
        return ToolResult(ok=True, output=out)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, output=str(exc))


def _parse_json_payload(payload: str) -> dict[str, object]:
    try:
        data = json.loads(payload)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid JSON payload: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    return data


def run_workspace_list(payload: str, execute: bool) -> ToolResult:
    _ = execute
    path = "."
    recursive = True
    if payload.strip():
        if payload.lstrip().startswith("{"):
            data = _parse_json_payload(payload)
            path = str(data.get("path", "."))
            recursive = bool(data.get("recursive", True))
        else:
            path = payload.strip()
    try:
        return ToolResult(ok=True, output=describe_workspace_tree(path, recursive=recursive))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, output=str(exc))


def run_workspace_read(payload: str, execute: bool) -> ToolResult:
    _ = execute
    path = payload.strip()
    if payload.lstrip().startswith("{"):
        try:
            path = str(_parse_json_payload(payload).get("path", "")).strip()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, output=str(exc))
    if not path:
        return _blocked("workspace_read requires a file path")
    try:
        return ToolResult(ok=True, output=read_workspace_file(path))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, output=str(exc))


def run_workspace_write(payload: str, execute: bool) -> ToolResult:
    if not payload.strip():
        return _blocked("workspace_write requires JSON with path and content")
    try:
        data = _parse_json_payload(payload)
        path = str(data.get("path", "")).strip()
        content = str(data.get("content", ""))
        overwrite = bool(data.get("overwrite", True))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, output=str(exc))
    if not path:
        return _blocked("workspace_write requires a path")
    if not execute:
        preview = content[:180].replace("\n", "\\n")
        return ToolResult(ok=True, output=f"DRY-RUN: write {path} in {workspace_root()} with content preview: {preview}")
    try:
        return ToolResult(ok=True, output=write_workspace_file(path, content, overwrite=overwrite))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, output=str(exc))


def run_project_scaffold(payload: str, execute: bool) -> ToolResult:
    if not payload.strip():
        return _blocked("project_scaffold requires JSON")
    try:
        data = _parse_json_payload(payload)
        name = str(data.get("name", "")).strip() or "magic-project"
        kind = str(data.get("kind", "website")).strip() or "website"
        prompt = str(data.get("prompt", "")).strip()
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, output=str(exc))
    if not execute:
        return ToolResult(
            ok=True,
            output=f"DRY-RUN: scaffold a {kind} project named {name} inside {workspace_root()}",
        )
    try:
        return ToolResult(ok=True, output=scaffold_project(name=name, kind=kind, prompt=prompt))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, output=str(exc))


def run_workspace_run(payload: str, execute: bool) -> ToolResult:
    if not payload.strip():
        return _blocked("workspace_run requires JSON")
    try:
        data = _parse_json_payload(payload)
        command = str(data.get("command", "")).strip()
        cwd = str(data.get("cwd", ".")).strip() or "."
        detach = bool(data.get("detach", False))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, output=str(exc))
    if not command:
        return _blocked("workspace_run requires a command")
    if not execute:
        return ToolResult(ok=True, output=f"DRY-RUN: run `{command}` in workspace folder `{cwd}`")
    result = run_workspace_command(command=command, cwd=cwd, detach=detach)
    return ToolResult(ok=result.ok, output=result.output)


def run_shell(command: str, execute: bool) -> ToolResult:
    settings = get_settings()
    text = command.strip()
    if not text:
        return _blocked("shell command is empty")

    try:
        argv = shlex.split(text)
    except Exception as exc:  # noqa: BLE001
        return _blocked(f"could not parse command: {exc}")

    first = argv[0] if argv else ""
    if first not in settings.shell_allowed_commands:
        return _blocked(f"'{first}' is not in allowlist")

    # Basic path guard: deny absolute paths outside allowed root.
    allowed_root = settings.shell_allowed_root.resolve()
    for token in argv[1:]:
        if token.startswith("-"):
            continue
        candidate = Path(token).expanduser()
        if candidate.is_absolute():
            try:
                candidate.resolve().relative_to(allowed_root)
            except Exception:  # noqa: BLE001
                return _blocked(f"path outside allowed root: {candidate}")

    if not execute:
        return ToolResult(ok=True, output=f"DRY-RUN: {text}")
    return _run_process(argv)


_TOOL_DISPATCH: dict[str, object] = {
    "run_shortcut": lambda p, e: run_shortcut(p, execute=e),
    "run_applescript": lambda p, e: run_applescript(p, execute=e),
    "run_shell": lambda p, e: run_shell(p, execute=e),
    "web_search": lambda p, e: run_web_search(p, execute=e),
    "query_memory": lambda p, e: run_query_memory(p, execute=e),
    "desktop": lambda p, e: run_desktop(p, execute=e),
    "workspace_list": lambda p, e: run_workspace_list(p, execute=e),
    "workspace_read": lambda p, e: run_workspace_read(p, execute=e),
    "workspace_write": lambda p, e: run_workspace_write(p, execute=e),
    "project_scaffold": lambda p, e: run_project_scaffold(p, execute=e),
    "workspace_run": lambda p, e: run_workspace_run(p, execute=e),
    "final_answer": lambda p, _: ToolResult(ok=True, output=p or "Done."),
}


def execute_tool_call(tool: str, payload: str, execute: bool) -> ToolResult:
    handler = _TOOL_DISPATCH.get(tool)
    if handler is None:
        return _blocked(f"unknown tool: {tool}")
    return handler(payload, execute)


from functools import lru_cache as _lru_cache


@_lru_cache(maxsize=1)
def _cached_tool_catalog() -> str:
    payload = {
        "tools": [
            {
                "name": "run_shortcut",
                "input": "Shortcut name as plain text",
                "description": "Run a macOS Shortcut by name",
            },
            {
                "name": "run_applescript",
                "input": "AppleScript code as string",
                "description": "Execute AppleScript via osascript",
            },
            {
                "name": "run_shell",
                "input": "Single shell command string (ls, cat, open, say, date, mkdir, etc.)",
                "description": "Execute an allowlisted shell command on macOS",
            },
            {
                "name": "web_search",
                "input": "Natural language web search query",
                "description": "Search the live web (DuckDuckGo + Wikipedia) for fast factual answers and sources",
            },
            {
                "name": "query_memory",
                "input": "Natural language question about your indexed files/notes",
                "description": "Search personal indexed documents using RAG (LlamaIndex)",
            },
            {
                "name": "desktop",
                "input": 'JSON object, one op. Examples: {"op":"screen"} | {"op":"click","x":400,"y":300} | {"op":"type","text":"hi"} | {"op":"hotkey","keys":["command","space"]} | {"op":"scroll","clicks":-5} | {"op":"screenshot"}',
                "description": "Full desktop robot: mouse, keyboard, scroll, drag, screenshot (needs macOS Accessibility permission)",
            },
            {
                "name": "workspace_list",
                "input": 'Relative path string or JSON like {"path":"my-site","recursive":true}',
                "description": "Inspect files inside Magic's desktop workspace",
            },
            {
                "name": "workspace_read",
                "input": 'Relative file path or JSON like {"path":"my-site/index.html"}',
                "description": "Read a text file from the Magic workspace",
            },
            {
                "name": "workspace_write",
                "input": '{"path":"my-site/index.html","content":"...","overwrite":true}',
                "description": "Create or replace a text file inside the Magic workspace",
            },
            {
                "name": "project_scaffold",
                "input": '{"name":"portfolio-site","kind":"website","prompt":"Clean landing page for a design studio"}',
                "description": "Create a starter project (website, fastapi, slides, document, image) on the Desktop workspace",
            },
            {
                "name": "workspace_run",
                "input": '{"cwd":"portfolio-site","command":"python3 -m http.server 4173","detach":true}',
                "description": "Run a development command inside the Magic workspace",
            },
            {
                "name": "final_answer",
                "input": "Human readable final response",
                "description": "Finish the plan — give the user a clear answer. Use this when the task is done or you only need to reply with text.",
            },
        ]
    }
    return json.dumps(payload, indent=2)


def tool_catalog_json() -> str:
    return _cached_tool_catalog()

