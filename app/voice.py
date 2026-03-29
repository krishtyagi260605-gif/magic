from __future__ import annotations

import io

from app.config import get_settings


def transcribe_bytes(data: bytes, filename: str = "audio.m4a") -> str:
    """Transcribe audio using OpenAI Whisper API (requires OPENAI_API_KEY)."""
    settings = get_settings()
    if not settings.openai_api_key:
        msg = (
            "Voice transcription needs OPENAI_API_KEY (Whisper API). "
            "Or use macOS Dictation and send text to POST /v1/command."
        )
        raise ValueError(msg)

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    buf = io.BytesIO(data)
    buf.name = filename or "audio.m4a"
    result = client.audio.transcriptions.create(model="whisper-1", file=buf)
    return (result.text or "").strip()
