from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.config import get_settings


def _pg():
    import pyautogui as pg

    return pg


def _screen_bounds() -> tuple[int, int]:
    pg = _pg()
    w, h = pg.size()
    return int(w), int(h)


def get_screen_info() -> dict[str, int]:
    configure_desktop()
    w, h = _screen_bounds()
    return {"width": w, "height": h}


def get_mouse_position() -> dict[str, int]:
    configure_desktop()
    pg = _pg()
    x, y = pg.position()
    return {"x": int(x), "y": int(y)}


def _clamp_coord(x: int | None, y: int | None) -> tuple[int, int]:
    w, h = _screen_bounds()
    if x is None or y is None:
        pg = _pg()
        cx, cy = pg.position()
        x = int(cx) if x is None else x
        y = int(cy) if y is None else y
    x = max(0, min(int(x), w - 1))
    y = max(0, min(int(y), h - 1))
    return x, y


def configure_desktop() -> None:
    settings = get_settings()
    pg = _pg()
    pg.FAILSAFE = settings.desktop_failsafe
    pg.PAUSE = settings.desktop_pause_seconds


def run_desktop_op(data: dict[str, Any]) -> str:
    """Execute one desktop op dict. Raises ValueError on bad input."""
    configure_desktop()
    pg = _pg()
    op = str(data.get("op", "")).strip().lower()
    if not op:
        raise ValueError("missing op")

    if op == "position":
        x, y = pg.position()
        return json.dumps({"x": int(x), "y": int(y)})

    if op == "screen":
        w, h = _screen_bounds()
        return json.dumps({"width": w, "height": h})

    if op == "move":
        x, y = _clamp_coord(data.get("x"), data.get("y"))
        dur = float(data.get("duration", 0.2))
        pg.moveTo(x, y, duration=max(0.0, dur))
        return f"moved to {x},{y}"

    if op == "click":
        x = data.get("x")
        y = data.get("y")
        if x is not None and y is not None:
            cx, cy = _clamp_coord(int(x), int(y))
            pg.moveTo(cx, cy, duration=float(data.get("duration", 0.1)))
        btn = str(data.get("button", "left")).lower()
        clicks = max(1, int(data.get("clicks", 1)))
        interval = float(data.get("interval", 0.1))
        pg.click(button=btn, clicks=clicks, interval=interval)
        px, py = pg.position()
        return f"click {btn} x{clicks} at ~{int(px)},{int(py)}"

    if op == "drag":
        if "to_x" not in data or "to_y" not in data:
            raise ValueError("drag requires to_x and to_y")
        x1, y1 = _clamp_coord(data.get("from_x"), data.get("from_y"))
        x2, y2 = _clamp_coord(int(data["to_x"]), int(data["to_y"]))
        pg.moveTo(x1, y1, duration=float(data.get("duration", 0.1)))
        pg.dragTo(x2, y2, duration=float(data.get("drag_duration", 0.3)), button=str(data.get("button", "left")).lower())
        return f"dragged {x1},{y1} -> {x2},{y2}"

    if op == "type":
        text = str(data.get("text", ""))
        use_cb = bool(data.get("use_clipboard")) or any(ord(c) > 127 for c in text)
        interval = float(data.get("interval", 0.02))
        if use_cb:
            import pyperclip

            pyperclip.copy(text)
            time.sleep(0.05)
            pg.hotkey("command", "v")
            return f"typed {len(text)} chars via clipboard"
        pg.write(text, interval=interval)
        return f"typed {len(text)} chars"

    if op == "hotkey":
        keys = data.get("keys")
        if not isinstance(keys, list) or not keys:
            raise ValueError("hotkey requires keys: [str, ...]")
        parts = [str(k).lower() for k in keys]
        pg.hotkey(*parts)
        return f"hotkey {'+'.join(parts)}"

    if op == "press":
        key = str(data.get("key", "")).strip()
        if not key:
            raise ValueError("press requires key")
        presses = max(1, int(data.get("presses", 1)))
        interval = float(data.get("interval", 0.1))
        pg.press(key, presses=presses, interval=interval)
        return f"press {key} x{presses}"

    if op == "scroll":
        clicks = int(data.get("clicks", 3))
        x = data.get("x")
        y = data.get("y")
        if x is not None and y is not None:
            cx, cy = _clamp_coord(int(x), int(y))
            pg.moveTo(cx, cy, duration=0.1)
        pg.scroll(clicks)
        return f"scroll {clicks}"

    if op == "screenshot":
        path = data.get("path")
        if path:
            out = Path(str(path)).expanduser().resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
        else:
            out = Path.home() / "Desktop" / f"magic_screenshot_{int(time.time())}.png"
            out.parent.mkdir(parents=True, exist_ok=True)
        img = pg.screenshot()
        img.save(str(out))
        return f"screenshot saved {out}"

    raise ValueError(f"unknown op: {op}")


def describe_desktop_op(data: dict[str, Any]) -> str:
    try:
        return f"DESKTOP: {json.dumps(data, ensure_ascii=False)}"
    except Exception:  # noqa: BLE001
        return f"DESKTOP: {data!r}"


def parse_desktop_payload(payload: str) -> dict[str, Any]:
    payload = payload.strip()
    if not payload:
        raise ValueError("empty desktop payload")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("desktop payload must be a JSON object")
    return data
