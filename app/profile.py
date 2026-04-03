from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import RLock


@dataclass
class MemoryFact:
    text: str
    source: str
    created_at: str


_lock = RLock()
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STORE_PATH = _PROJECT_ROOT / ".magic_data" / "profile_memory.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load() -> dict[str, object]:
    if not _STORE_PATH.is_file():
        return {"preferences": {}, "facts": [], "feedback": []}
    try:
        raw = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            raw.setdefault("preferences", {})
            raw.setdefault("facts", [])
            raw.setdefault("feedback", [])
            return raw
    except Exception:  # noqa: BLE001
        pass
    return {"preferences": {}, "facts": [], "feedback": []}


def _save(data: dict[str, object]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _normalize_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "preference"


def remember_fact(text: str, source: str = "manual") -> dict[str, object]:
    clean = " ".join((text or "").split()).strip()
    if not clean:
        raise ValueError("memory text is empty")
    with _lock:
        data = _load()
        facts = list(data.get("facts", []))
        facts.insert(0, {"text": clean, "source": source, "created_at": _now()})
        data["facts"] = facts[:120]
        _save(data)
        return {"status": "remembered", "text": clean}


def set_preference(key: str, value: str, source: str = "manual") -> dict[str, object]:
    clean_key = _normalize_key(key)
    clean_value = " ".join((value or "").split()).strip()
    if not clean_value:
        raise ValueError("preference value is empty")
    with _lock:
        data = _load()
        prefs = dict(data.get("preferences", {}))
        prefs[clean_key] = {"value": clean_value, "source": source, "updated_at": _now()}
        data["preferences"] = prefs
        _save(data)
        return {"status": "saved", "key": clean_key, "value": clean_value}


def record_feedback(text: str) -> dict[str, object]:
    clean = " ".join((text or "").split()).strip()
    if not clean:
        raise ValueError("feedback text is empty")
    with _lock:
        data = _load()
        feedback = list(data.get("feedback", []))
        feedback.insert(0, {"text": clean, "created_at": _now()})
        data["feedback"] = feedback[:120]
        _save(data)
        return {"status": "logged", "text": clean}


def profile_summary() -> str:
    with _lock:
        data = _load()
    prefs = data.get("preferences", {})
    facts = data.get("facts", [])
    feedback = data.get("feedback", [])
    lines: list[str] = []
    if isinstance(prefs, dict) and prefs:
        lines.append("Preferences:")
        for key, item in list(prefs.items())[:12]:
            if isinstance(item, dict):
                lines.append(f"- {key}: {item.get('value', '')}")
    if isinstance(facts, list) and facts:
        lines.append("Remembered facts:")
        for item in facts[:12]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('text', '')}")
    if isinstance(feedback, list) and feedback:
        lines.append("Recent feedback:")
        for item in feedback[:8]:
            if isinstance(item, dict):
                lines.append(f"- {item.get('text', '')}")
    return "\n".join(lines) if lines else "(no personal memory saved yet)"


def profile_stats() -> dict[str, int]:
    with _lock:
        data = _load()
    prefs = data.get("preferences", {})
    facts = data.get("facts", [])
    feedback = data.get("feedback", [])
    return {
        "preferences": len(prefs) if isinstance(prefs, dict) else 0,
        "facts": len(facts) if isinstance(facts, list) else 0,
        "feedback": len(feedback) if isinstance(feedback, list) else 0,
    }


def maybe_learn_from_message(text: str) -> None:
    lower = (text or "").lower().strip()
    if not lower:
        return

    remember_patterns = (
        r"remember that\s+(.+)$",
        r"note that\s+(.+)$",
    )
    for pattern in remember_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            remember_fact(match.group(1).strip(), source="chat")
            return

    pref_patterns = [
        (r"my name is\s+(.+)$", "name"),
        (r"call me\s+(.+)$", "name"),
        (r"i prefer\s+(.+)$", "general_preference"),
        (r"my favorite color is\s+(.+)$", "favorite_color"),
        (r"i like\s+(.+)$", "likes"),
        (r"i don[’']?t like\s+(.+)$", "dislikes"),
        (r"always use\s+(.+)$", "always_use"),
        (r"use\s+(.+)\s+style$", "style_preference"),
        (r"my company is\s+(.+)$", "company"),
        (r"my startup is\s+(.+)$", "startup"),
    ]
    for pattern, key in pref_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            set_preference(key, match.group(1).strip(), source="chat")
            return
