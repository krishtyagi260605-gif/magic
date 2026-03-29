from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from threading import RLock
from uuid import uuid4


@dataclass
class ConversationTurn:
    role: str
    content: str
    created_at: str


@dataclass
class ConversationSession:
    id: str
    title: str
    created_at: str
    updated_at: str
    turns: deque[ConversationTurn] = field(default_factory=lambda: deque(maxlen=_MAX_TURNS))


_lock = RLock()
_MAX_TURNS = 40
_MAX_SESSIONS = 50
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STORE_PATH = _PROJECT_ROOT / ".magic_data" / "chat_sessions.json"
_sessions: dict[str, ConversationSession] = {}
_loaded = False


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _default_title(text: str) -> str:
    clean = " ".join((text or "").split()).strip() or "New chat"
    return clean[:60]


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    with _lock:
        if _loaded:
            return
        if _STORE_PATH.is_file():
            try:
                raw = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
                for item in raw.get("sessions", []):
                    turns = deque(
                        [
                            ConversationTurn(
                                role=str(turn.get("role", "assistant")),
                                content=str(turn.get("content", "")),
                                created_at=str(turn.get("created_at", _now())),
                            )
                            for turn in item.get("turns", [])
                        ],
                        maxlen=_MAX_TURNS,
                    )
                    session = ConversationSession(
                        id=str(item.get("id")),
                        title=str(item.get("title", "New chat")),
                        created_at=str(item.get("created_at", _now())),
                        updated_at=str(item.get("updated_at", _now())),
                        turns=turns,
                    )
                    _sessions[session.id] = session
            except Exception:  # noqa: BLE001
                _sessions.clear()
        _loaded = True


def _save() -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "sessions": [
            {
                "id": session.id,
                "title": session.title,
                "created_at": session.created_at,
                "updated_at": session.updated_at,
                "turns": [asdict(turn) for turn in session.turns],
            }
            for session in sorted(_sessions.values(), key=lambda item: item.updated_at, reverse=True)
        ]
    }
    _STORE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _prune_sessions() -> None:
    if len(_sessions) <= _MAX_SESSIONS:
        return
    by_age = sorted(_sessions.values(), key=lambda s: s.updated_at, reverse=True)
    for old in by_age[_MAX_SESSIONS:]:
        _sessions.pop(old.id, None)


def ensure_session(session_id: str | None, initial_user_text: str | None = None) -> str:
    _ensure_loaded()
    resolved = (session_id or "").strip() or str(uuid4())
    with _lock:
        session = _sessions.get(resolved)
        if session is None:
            now = _now()
            session = ConversationSession(
                id=resolved,
                title=_default_title(initial_user_text or ""),
                created_at=now,
                updated_at=now,
            )
            _sessions[resolved] = session
            _prune_sessions()
            _save()
    return resolved


def append_turn(session_id: str, role: str, content: str) -> None:
    _ensure_loaded()
    text = (content or "").strip()
    if not text:
        return
    with _lock:
        session = _sessions.setdefault(
            session_id,
            ConversationSession(id=session_id, title=_default_title(text), created_at=_now(), updated_at=_now()),
        )
        if not session.turns and role == "user":
            session.title = _default_title(text)
        session.turns.append(ConversationTurn(role=role, content=text, created_at=_now()))
        session.updated_at = _now()
        _save()


def get_turns(session_id: str) -> list[ConversationTurn]:
    _ensure_loaded()
    with _lock:
        session = _sessions.get(session_id)
        return list(session.turns) if session else []


def get_session(session_id: str) -> ConversationSession | None:
    _ensure_loaded()
    with _lock:
        return _sessions.get(session_id)


def list_sessions() -> list[ConversationSession]:
    _ensure_loaded()
    with _lock:
        return sorted(_sessions.values(), key=lambda item: item.updated_at, reverse=True)


def clear_session(session_id: str) -> None:
    _ensure_loaded()
    with _lock:
        if session_id in _sessions:
            _sessions.pop(session_id, None)
            _save()


def format_history(session_id: str) -> str:
    turns = get_turns(session_id)
    if not turns:
        return "(no previous conversation)"
    return "\n".join(f"{turn.role}: {turn.content}" for turn in turns)
