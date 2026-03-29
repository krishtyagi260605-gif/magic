from __future__ import annotations

import re
import shlex
import subprocess
import os
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings


@dataclass
class WorkspaceRunResult:
    ok: bool
    output: str


def workspace_root() -> Path:
    root = get_settings().magic_workspace_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_slug(text: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return lowered[:48] or "magic-project"


def resolve_workspace_path(raw_path: str | None = None) -> Path:
    root = workspace_root()
    text = (raw_path or ".").strip()
    candidate = Path(text).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"path must stay inside {root}") from exc
    return resolved


def describe_workspace_tree(raw_path: str | None = None, recursive: bool = True, limit: int = 160) -> str:
    target = resolve_workspace_path(raw_path)
    if not target.exists():
        return f"{target} does not exist yet."
    if target.is_file():
        return f"FILE {target.relative_to(workspace_root())}"

    lines = [f"Workspace root: {workspace_root()}", f"Listing: {target.relative_to(workspace_root()) or '.'}"]
    if recursive:
        items = sorted(target.rglob("*"))
    else:
        items = sorted(target.iterdir())
    shown = 0
    for item in items:
        if shown >= limit:
            lines.append(f"...and {len(items) - shown} more")
            break
        rel = item.relative_to(workspace_root())
        marker = "/" if item.is_dir() else ""
        lines.append(f"- {rel}{marker}")
        shown += 1
    if shown == 0:
        lines.append("(empty)")
    return "\n".join(lines)


def workspace_snapshot(limit: int = 40) -> str:
    root = workspace_root()
    if not root.exists():
        return "(workspace unavailable)"
    items = sorted(root.rglob("*"))
    if not items:
        return f"Workspace root: {root}\n(empty)"

    lines = [f"Workspace root: {root}"]
    for item in items[:limit]:
        rel = item.relative_to(root)
        suffix = "/" if item.is_dir() else ""
        lines.append(f"- {rel}{suffix}")
    if len(items) > limit:
        lines.append(f"...and {len(items) - limit} more")
    return "\n".join(lines)


def read_workspace_file(raw_path: str) -> str:
    target = resolve_workspace_path(raw_path)
    if not target.exists():
        raise ValueError(f"{target.name} does not exist")
    if not target.is_file():
        raise ValueError(f"{target.name} is not a file")
    text = target.read_text(encoding="utf-8")
    if len(text) > 14000:
        text = text[:13900].rstrip() + "\n...[truncated]"
    return text


def write_workspace_file(raw_path: str, content: str, overwrite: bool = True) -> str:
    target = resolve_workspace_path(raw_path)
    if target.exists() and target.is_dir():
        raise ValueError(f"{target.name} is a directory")
    if target.exists() and not overwrite:
        raise ValueError(f"{target.name} already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {target.relative_to(workspace_root())}"


def _next_available_project_dir(name: str) -> Path:
    root = workspace_root()
    base = root / _safe_slug(name)
    if not base.exists():
        return base
    for idx in range(2, 100):
        candidate = root / f"{base.name}-{idx}"
        if not candidate.exists():
            return candidate
    raise ValueError("could not find an available project folder name")


def scaffold_project(name: str, kind: str = "website", prompt: str = "") -> str:
    project_dir = _next_available_project_dir(name)
    project_dir.mkdir(parents=True, exist_ok=False)
    
    (project_dir / "README.md").write_text(
        f"# {name}\n\nType: {kind}\n\nGoal:\n{prompt}\n\nThis project folder is ready. Ask Magic to write the code for it.",
        encoding="utf-8",
    )
    return (
        f"Created an empty {kind} project folder at {project_dir}.\n"
        "Now you MUST write the actual high-quality implementation files (index.html, styles.css, etc.) into this folder."
    )
    return (
        f"Created {kind_key} project at {project_dir}.\n"
        f"To preview a static site there, run: python3 -m http.server 4173"
    )


def run_workspace_command(command: str, cwd: str | None = None, detach: bool = False) -> WorkspaceRunResult:
    settings = get_settings()
    text = (command or "").strip()
    if not text:
        return WorkspaceRunResult(ok=False, output="workspace command is empty")

    try:
        argv = shlex.split(text)
    except Exception as exc:  # noqa: BLE001
        return WorkspaceRunResult(ok=False, output=f"could not parse workspace command: {exc}")

    first = argv[0] if argv else ""
    if first not in settings.workspace_run_allowed_commands:
        return WorkspaceRunResult(ok=False, output=f"'{first}' is not allowed in workspace runner")

    workdir = resolve_workspace_path(cwd or ".")
    if not workdir.exists():
        workdir.mkdir(parents=True, exist_ok=True)
    if not workdir.is_dir():
        return WorkspaceRunResult(ok=False, output=f"{workdir} is not a folder")

    env = os.environ.copy()
    env["PATH"] = ":".join(
        [
            str(Path("/usr/bin")),
            str(Path("/bin")),
            str(Path("/usr/local/bin")),
            str(Path("/opt/homebrew/bin")),
            env.get("PATH", ""),
        ]
    )
    try:
        if detach:
            logs_dir = workspace_root() / ".runs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            slug = _safe_slug(workdir.name or "run")
            log_path = logs_dir / f"{slug}.log"
            handle = log_path.open("a", encoding="utf-8")
            process = subprocess.Popen(  # noqa: S603
                argv,
                cwd=str(workdir),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )
            return WorkspaceRunResult(
                ok=True,
                output=f"Started background command in {workdir} with PID {process.pid}. Logs: {log_path}",
            )

        completed = subprocess.run(  # noqa: S603
            argv,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        output = ((completed.stdout or "") + (completed.stderr or "")).strip() or "ok"
        return WorkspaceRunResult(ok=completed.returncode == 0, output=output)
    except Exception as exc:  # noqa: BLE001
        return WorkspaceRunResult(ok=False, output=str(exc))
