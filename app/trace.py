import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from pydantic import BaseModel

from app.config import get_settings

def _trace_dir() -> Path:
    d = get_settings().magic_data_dir / "traces"
    d.mkdir(parents=True, exist_ok=True)
    return d

def append_trace(session_id: str, event_type: str, data: dict[str, Any]) -> None:
    if not session_id:
        return
    p = _trace_dir() / f"{session_id}.jsonl"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": datetime.now().isoformat(), "type": event_type, "data": data}) + "\n")

def get_trace(session_id: str) -> list[dict[str, Any]]:
    p = _trace_dir() / f"{session_id}.jsonl"
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

_APPROVALS: dict[str, dict[str, Any]] = {}

def create_approval(session_id: str, tool: str, payload: str, summary: str, risk_level: str, diff: str | None = None, files_affected: list[str] | None = None) -> str:
    app_id = f"appr_{uuid.uuid4().hex[:8]}"
    _APPROVALS[app_id] = {
        "id": app_id,
        "session_id": session_id,
        "tool": tool,
        "payload": payload,
        "summary": summary,
        "risk_level": risk_level,
        "diff": diff,
        "files_affected": files_affected or [],
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    return app_id

def get_pending_approvals(session_id: str) -> list[dict[str, Any]]:
    return [a for a in _APPROVALS.values() if a["session_id"] == session_id and a["status"] == "pending"]

def resolve_approval(approval_id: str, action: str) -> dict[str, Any] | None:
    if approval_id in _APPROVALS:
        _APPROVALS[approval_id]["status"] = "approved" if action == "approve" else "rejected"
        append_trace(_APPROVALS[approval_id]["session_id"], "approval_resolved", {"approval_id": approval_id, "action": action, "tool": _APPROVALS[approval_id]["tool"]})
        return _APPROVALS[approval_id]
    return None