from __future__ import annotations

import shutil
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import get_settings
from app.models import ReasoningLevel

LLMProfile = Literal["router", "chat", "action", "synthesis"]


def get_llm(
    reasoning_level: ReasoningLevel = "medium",
    *,
    profile: LLMProfile = "action",
) -> BaseChatModel:
    """Return an LLM tuned for the task. Router is optimized for latency; chat/synthesis for answer quality."""
    settings = get_settings()
    if settings.llm_provider.lower() == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        if profile == "router":
            return ChatOpenAI(
                model=settings.openai_model,
                api_key=settings.openai_api_key,
                temperature=0,
                model_kwargs={"max_tokens": settings.openai_router_max_tokens},
            )
        max_out = {
            "easy": 1200,
            "medium": 2200,
            "high": 3500,
            "extra_high": 5000,
        }[reasoning_level]
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.15 if profile == "chat" else 0,
            model_kwargs={"max_tokens": max_out},
        )

    if settings.llm_provider.lower() == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        if profile == "router":
            return ChatAnthropic(
                model=settings.anthropic_model,
                api_key=settings.anthropic_api_key,
                temperature=0,
                max_tokens=settings.openai_router_max_tokens,
            )
        max_out = {
            "easy": 1200,
            "medium": 2200,
            "high": 3500,
            "extra_high": 5000,
        }[reasoning_level]
        return ChatAnthropic(
            model=settings.anthropic_model,
            api_key=settings.anthropic_api_key,
            temperature=0.15 if profile == "chat" else 0,
            max_tokens=max_out,
        )

    if settings.llm_provider.lower() == "groq":
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        if profile == "router":
            return ChatGroq(
                model_name=settings.groq_model,
                api_key=settings.groq_api_key,
                temperature=0,
                max_tokens=settings.openai_router_max_tokens,
            )
        max_out = {
            "easy": 1200, "medium": 2200, "high": 3500, "extra_high": 5000,
        }[reasoning_level]
        return ChatGroq(
            model_name=settings.groq_model,
            api_key=settings.groq_api_key,
            temperature=0.15 if profile == "chat" else 0,
            max_tokens=max_out,
        )

    if settings.llm_provider.lower() == "google":
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required when LLM_PROVIDER=google")
        if profile == "router":
            return ChatGoogleGenerativeAI(
                model=settings.google_model,
                google_api_key=settings.google_api_key,
                temperature=0,
                max_output_tokens=settings.openai_router_max_tokens,
            )
        max_out = {
            "easy": 1200, "medium": 2200, "high": 3500, "extra_high": 5000,
        }[reasoning_level]
        return ChatGoogleGenerativeAI(
            model=settings.google_model,
            google_api_key=settings.google_api_key,
            temperature=0.15 if profile == "chat" else 0,
            max_output_tokens=max_out,
        )

    if shutil.which("ollama") is None:
        raise ValueError(
            "Ollama is not installed. Install it from https://ollama.com/download and then run "
            f"`ollama pull {settings.ollama_model}`."
        )

    base = {
        "easy": {"num_ctx": 6144, "num_predict": 420},
        "medium": {"num_ctx": 10240, "num_predict": 680},
        "high": {"num_ctx": 16384, "num_predict": 1000},
        "extra_high": {"num_ctx": 20480, "num_predict": 1600},
    }[reasoning_level]

    keep = settings.ollama_keep_alive

    if profile == "router":
        return ChatOllama(
            model=settings.ollama_model,
            temperature=0,
            base_url=settings.ollama_base_url,
            keep_alive=keep,
            num_ctx=min(4096, base["num_ctx"]),
            num_predict=96,
            top_p=0.92,
            repeat_penalty=1.08,
        )

    if profile == "chat":
        return ChatOllama(
            model=settings.ollama_model,
            temperature=0.12,
            base_url=settings.ollama_base_url,
            keep_alive=keep,
            num_ctx=base["num_ctx"],
            num_predict=min(int(base["num_predict"] * 1.15), 1400),
            top_p=0.95,
            repeat_penalty=1.05,
        )

    if profile == "synthesis":
        return ChatOllama(
            model=settings.ollama_model,
            temperature=0.08,
            base_url=settings.ollama_base_url,
            keep_alive=keep,
            num_ctx=base["num_ctx"],
            num_predict=min(int(base["num_predict"] * 1.12), 1400),
            top_p=0.92,
            repeat_penalty=1.06,
        )

    # action
    return ChatOllama(
        model=settings.ollama_model,
        temperature=0,
        base_url=settings.ollama_base_url,
        keep_alive=keep,
        num_ctx=base["num_ctx"],
        num_predict=base["num_predict"],
        top_p=0.9,
        repeat_penalty=1.1,
    )
