from __future__ import annotations

from collections import deque
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.conversation import _sessions
from app.main import app
from app.trace import _APPROVALS


@pytest.fixture(autouse=True)
def isolate_project_state(tmp_path, monkeypatch):
    settings = get_settings()
    data_dir = tmp_path / "magic-data"
    workspace_dir = tmp_path / "workspace"
    notes_dir = tmp_path / "notes"
    data_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    notes_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "magic_data_dir", data_dir, raising=False)
    monkeypatch.setattr(settings, "magic_workspace_root", workspace_dir, raising=False)
    monkeypatch.setattr(settings, "magic_index_paths", str(notes_dir), raising=False)
    monkeypatch.setattr(settings, "google_api_key", "test-google-key", raising=False)
    monkeypatch.setattr(settings, "llm_provider", "google", raising=False)
    monkeypatch.setattr(settings, "embedding_provider", "google", raising=False)
    monkeypatch.setattr(settings, "llm_fallback_providers", "google,openai,anthropic", raising=False)
    monkeypatch.setattr(settings, "openai_api_key", "test-openai-key", raising=False)
    monkeypatch.setattr(settings, "anthropic_api_key", "", raising=False)
    monkeypatch.setattr(settings, "groq_api_key", "", raising=False)
    monkeypatch.setattr(settings, "dry_run_default", True, raising=False)
    monkeypatch.setattr(settings, "sandbox_docker_image", "python:3.11-slim", raising=False)

    import app.main as main_mod
    import app.conversation as convo_mod
    import app.rag as rag_mod
    import app.trace as trace_mod
    import app.llm as llm_mod

    monkeypatch.setattr(main_mod, "settings", settings, raising=False)
    monkeypatch.setattr(convo_mod, "_STORE_PATH", data_dir / "chat_sessions.json", raising=False)
    monkeypatch.setattr(convo_mod, "_loaded", True, raising=False)
    _sessions.clear()
    _APPROVALS.clear()
    rag_mod._index = None
    llm_mod._last_provider_used = None
    llm_mod._last_fallback_used = None

    yield {
        "settings": settings,
        "data_dir": data_dir,
        "workspace_dir": workspace_dir,
        "notes_dir": notes_dir,
    }

    _sessions.clear()
    _APPROVALS.clear()
    rag_mod._index = None


@pytest.fixture
def client():
    return TestClient(app)
