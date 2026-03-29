from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from app.config import get_settings


def _fetch_json(url: str, timeout: float = 1.5) -> tuple[bool, dict[str, object] | None, str | None]:
    try:
        with urlopen(url, timeout=timeout) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict):
                return True, payload, None
            return True, {"value": payload}, None
    except URLError as exc:
        return False, None, str(exc.reason or exc)
    except Exception as exc:  # noqa: BLE001
        return False, None, str(exc)


def _ollama_model_present(payload: dict[str, object] | None, model_name: str) -> bool:
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return False
    lowered = model_name.lower()
    for model in models:
        if not isinstance(model, dict):
            continue
        name = str(model.get("name", "")).lower()
        if name == lowered or name.startswith(lowered + ":") or lowered.startswith(name + ":"):
            return True
    return False


def build_runtime_status() -> dict[str, object]:
    settings = get_settings()
    provider = settings.llm_provider.lower()
    embedding_provider = settings.embedding_provider.lower()
    ollama_installed = shutil.which("ollama") is not None

    ollama_ok, ollama_payload, ollama_error = _fetch_json(f"{settings.ollama_base_url.rstrip('/')}/api/tags") if ollama_installed else (False, None, "Ollama is not installed")

    llm_reachable = None
    llm_error = None
    llm_model_available = None
    if provider == "ollama":
        llm_reachable = ollama_ok
        llm_model_available = _ollama_model_present(ollama_payload, settings.ollama_model) if ollama_ok else False
        if not ollama_ok:
            llm_error = ollama_error
        elif not llm_model_available:
            llm_error = f"Model {settings.ollama_model} is not pulled yet"
    elif provider == "openai":
        llm_reachable = bool(settings.openai_api_key)
        llm_model_available = llm_reachable
        if not llm_reachable:
            llm_error = "OPENAI_API_KEY is not set"

    embedding_reachable = None
    embedding_error = None
    embedding_model_available = None
    if embedding_provider == "ollama":
        embedding_reachable = ollama_ok
        embedding_model_available = _ollama_model_present(ollama_payload, settings.ollama_embedding_model) if ollama_ok else False
        if not ollama_ok:
            embedding_error = ollama_error
        elif not embedding_model_available:
            embedding_error = f"Embedding model {settings.ollama_embedding_model} is not pulled yet"
    elif embedding_provider == "openai":
        embedding_reachable = bool(settings.openai_api_key)
        embedding_model_available = embedding_reachable
        if not embedding_reachable:
            embedding_error = "OPENAI_API_KEY is not set"

    index_paths = [str(path) for path in settings.parsed_index_paths()]
    persist_dir = settings.magic_data_dir / "vector_index"
    fallback_dir = Path(__file__).resolve().parents[1] / ".magic_data" / "vector_index"
    active_persist_dir = persist_dir if persist_dir.exists() else fallback_dir
    workspace_root = settings.magic_workspace_root
    workspace_root.mkdir(parents=True, exist_ok=True)

    return {
        "app_name": settings.app_name,
        "dry_run_default": settings.dry_run_default,
        "llm": {
            "provider": provider,
            "model": settings.openai_model if provider == "openai" else settings.ollama_model,
            "reachable": llm_reachable,
            "error": llm_error,
            "model_available": llm_model_available,
            "ollama_installed": ollama_installed,
        },
        "embeddings": {
            "provider": embedding_provider,
            "model": settings.openai_embedding_model if embedding_provider == "openai" else settings.ollama_embedding_model,
            "reachable": embedding_reachable,
            "error": embedding_error,
            "model_available": embedding_model_available,
        },
        "memory": {
            "paths": index_paths,
            "persist_dir": str(active_persist_dir),
            "has_index": active_persist_dir.exists() and any(active_persist_dir.iterdir()),
        },
        "desktop": {
            "enabled": settings.desktop_automation_enabled,
            "failsafe": settings.desktop_failsafe,
            "max_ops_per_plan": settings.desktop_max_ops_per_plan,
        },
        "workspace": {
            "root": str(workspace_root),
            "exists": workspace_root.exists(),
            "projects": len([item for item in workspace_root.iterdir() if item.is_dir()]) if workspace_root.exists() else 0,
        },
    }
