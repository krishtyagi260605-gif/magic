from __future__ import annotations

from functools import lru_cache

from llama_index.core import Settings as LlamaSettings

from app.config import get_settings


@lru_cache(maxsize=1)
def configure_llama_global_embeddings() -> None:
    settings = get_settings()
    provider = settings.embedding_provider.lower()
    if provider == "none":
        return
    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai")
        from llama_index.embeddings.openai import OpenAIEmbedding

        LlamaSettings.embed_model = OpenAIEmbedding(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
        )
        return
    if provider == "ollama":
        from llama_index.embeddings.ollama import OllamaEmbedding

        LlamaSettings.embed_model = OllamaEmbedding(
            model_name=settings.ollama_embedding_model,
            base_url=settings.ollama_base_url,
        )
        return
    if provider == "google":
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required when EMBEDDING_PROVIDER=google")
        from llama_index.embeddings.google import GeminiEmbedding

        LlamaSettings.embed_model = GeminiEmbedding(
            model_name=settings.google_embedding_model,
            api_key=settings.google_api_key,
        )
        return
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {settings.embedding_provider}")
