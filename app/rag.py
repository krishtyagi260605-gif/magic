from __future__ import annotations

import shutil
import threading
from pathlib import Path

from llama_index.core import (
    Document,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)

from app.config import get_settings
from app.embeddings import configure_llama_global_embeddings

_lock = threading.RLock()
_index: VectorStoreIndex | None = None
_PROJECT_FALLBACK = Path(__file__).resolve().parents[1] / ".magic_data" / "vector_index"


def _persist_dir() -> Path:
    settings = get_settings()
    d = settings.magic_data_dir / "vector_index"
    try:
        d.mkdir(parents=True, exist_ok=True)
        return d
    except OSError:
        _PROJECT_FALLBACK.mkdir(parents=True, exist_ok=True)
        return _PROJECT_FALLBACK


def _index_exists_on_disk() -> bool:
    p = _persist_dir()
    return p.exists() and any(p.iterdir())


def _load_documents_from_paths(paths: list[Path]) -> list[Document]:
    docs: list[Document] = []
    for base in paths:
        if not base.exists():
            continue
        if base.is_file():
            docs.extend(SimpleDirectoryReader(input_files=[str(base)]).load_data())
        else:
            docs.extend(
                SimpleDirectoryReader(
                    input_dir=str(base),
                    recursive=True,
                    exclude_hidden=True,
                ).load_data()
            )
    return docs


def _build_index_from_documents(documents: list[Document]) -> VectorStoreIndex:
    configure_llama_global_embeddings()
    if not documents:
        raise ValueError("No documents to index")
    return VectorStoreIndex.from_documents(documents)


def load_or_build_index() -> VectorStoreIndex | None:
    global _index
    configure_llama_global_embeddings()
    settings = get_settings()
    persist = _persist_dir()

    with _lock:
        if _index is not None:
            return _index

        if _index_exists_on_disk():
            try:
                storage_context = StorageContext.from_defaults(persist_dir=str(persist))
                _index = load_index_from_storage(storage_context)
                return _index
            except Exception:  # noqa: BLE001
                _index = None

        paths = settings.parsed_index_paths()
        for p in paths:
            if p.is_dir():
                try:
                    p.mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass

        documents = _load_documents_from_paths(paths)
        if not documents:
            return None

        _index = _build_index_from_documents(documents)
        _index.storage_context.persist(persist_dir=str(persist))
        return _index


def get_index() -> VectorStoreIndex | None:
    return load_or_build_index()


def query_memory(user_query: str) -> tuple[str, list[str]]:
    """Retrieve context from the local index. Returns (answer_text, source_paths)."""
    settings = get_settings()
    index = get_index()
    if index is None:
        return (
            "(No indexed memory yet. POST /v1/index/ingest or set MAGIC_INDEX_PATHS and restart.)",
            [],
        )

    configure_llama_global_embeddings()
    engine = index.as_query_engine(
        similarity_top_k=settings.rag_top_k,
        response_mode=settings.rag_response_mode,
    )
    response = engine.query(user_query)
    text = str(getattr(response, "response", response) or "").strip() or "(empty response)"
    sources: list[str] = []
    for node in getattr(response, "source_nodes", None) or []:
        meta = getattr(node, "node", node)
        md = getattr(meta, "metadata", {}) or {}
        fp = md.get("file_path") or md.get("file_name") or ""
        if fp and fp not in sources:
            sources.append(str(fp))
    return text, sources


def ingest_paths(extra_paths: list[Path] | None = None, rebuild: bool = False) -> dict[str, int | str]:
    """Add documents from paths into the index and persist."""
    global _index
    settings = get_settings()
    paths = [Path(p).expanduser().resolve() for p in extra_paths] if extra_paths else settings.parsed_index_paths()

    with _lock:
        _index = None
        persist = _persist_dir()
        if rebuild and persist.exists():
            shutil.rmtree(persist)
            persist.mkdir(parents=True, exist_ok=True)

        configure_llama_global_embeddings()
        documents = _load_documents_from_paths(paths)
        if not documents:
            return {"status": "no_documents", "count": 0, "message": "No files found under given paths."}

        if rebuild or not _index_exists_on_disk():
            idx = _build_index_from_documents(documents)
            idx.storage_context.persist(persist_dir=str(persist))
            _index = idx
            return {"status": "built", "count": len(documents), "persist_dir": str(persist)}

        storage_context = StorageContext.from_defaults(persist_dir=str(persist))
        idx = load_index_from_storage(storage_context)
        for doc in documents:
            idx.insert(doc)
        idx.storage_context.persist(persist_dir=str(persist))
        _index = idx
        return {"status": "merged", "count": len(documents), "persist_dir": str(persist)}
