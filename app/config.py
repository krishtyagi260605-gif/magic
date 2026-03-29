from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "magic"
    owner_name: str = "Krish Tyagi"
    dry_run_default: bool = True

    llm_provider: str = Field(default="ollama", description="ollama | openai | anthropic | groq | google")
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    google_api_key: str | None = None
    google_model: str = "gemini-1.5-flash"
    ollama_model: str = "qwen2.5:7b"
    ollama_base_url: str = "http://127.0.0.1:11434"
    # Keep model loaded in Ollama between calls (faster follow-up turns)
    ollama_keep_alive: str = "15m"
    # Tiny JSON classification when using OpenAI/Anthropic (router only)
    openai_router_max_tokens: int = 380

    # LlamaIndex RAG — embeddings must match your setup (OpenAI key or local Ollama embed model)
    embedding_provider: str = Field(default="ollama", description="ollama | openai")
    openai_embedding_model: str = "text-embedding-3-small"
    ollama_embedding_model: str = "nomic-embed-text"
    magic_data_dir: Path = Field(default_factory=lambda: Path.home() / ".magic")
    magic_workspace_root: Path = Field(default_factory=lambda: Path.home() / "Desktop" / "MagicProjects")
    # Comma-separated absolute or ~ paths to folders/files to index (created on first ingest if missing)
    magic_index_paths: str = ""
    rag_top_k: int = 5
    rag_response_mode: str = Field(default="compact", description="compact | tree_summarize")

    @field_validator("magic_data_dir", mode="before")
    @classmethod
    def expand_magic_data(cls, v: object) -> Path:
        if v is None:
            return Path.home() / ".magic"
        if isinstance(v, Path):
            return v.expanduser().resolve()
        s = str(v).strip()
        if not s:
            return Path.home() / ".magic"
        return Path(s).expanduser().resolve()

    def parsed_index_paths(self) -> list[Path]:
        if not self.magic_index_paths.strip():
            default = Path.home() / "Documents" / "MagicNotes"
            return [default]
        parts = [p.strip() for p in self.magic_index_paths.split(",") if p.strip()]
        return [Path(p).expanduser().resolve() for p in parts]

    @field_validator("magic_workspace_root", mode="before")
    @classmethod
    def expand_workspace_root(cls, v: object) -> Path:
        if v is None:
            return Path.home() / "Desktop" / "MagicProjects"
        if isinstance(v, Path):
            return v.expanduser().resolve()
        s = str(v).strip()
        if not s:
            return Path.home() / "Desktop" / "MagicProjects"
        return Path(s).expanduser().resolve()

    # Guardrails for shell tool
    shell_allowed_commands: tuple[str, ...] = (
        "ls",
        "pwd",
        "whoami",
        "date",
        "mkdir",
        "cp",
        "mv",
        "cat",
        "touch",
        "find",
        "mdfind",
        "stat",
        "uname",
        "open",
        "say",
        "defaults",
        "osascript",
        "shortcuts",
        "pmset",
        "ipconfig",
        "df",
        "system_profiler",
        "screencapture",
        "diskutil",
    )
    workspace_run_allowed_commands: tuple[str, ...] = (
        "python3",
        "python",
        "node",
        "npm",
        "npx",
        "pip3",
        "pip",
        "git",
        "uv",
        "bash",
        "sh",
        "open",
    )
    shell_allowed_root: Path = Path.home()

    # Full desktop control (mouse/keyboard) — requires macOS Accessibility for the Python/terminal app
    desktop_automation_enabled: bool = True
    desktop_failsafe: bool = True  # move mouse to top-left corner aborts automation
    desktop_pause_seconds: float = 0.08
    desktop_max_ops_per_plan: int = 120
    agent_max_steps: int = 10
    agent_observation_max_chars: int = 1400
    agent_history_max_chars: int = 3500
    status_poll_interval_ms: int = 30000


class SafetyReport(BaseModel):
    dry_run: bool
    notes: list[str] = []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
