from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ReasoningLevel = Literal["easy", "medium", "high", "extra_high"]

ToolName = Literal[
    "run_shortcut",
    "run_applescript",
    "run_shell",
    "web_search",
    "query_memory",
    "desktop",
    "workspace_list",
    "workspace_read",
    "workspace_write",
    "project_scaffold",
    "workspace_run",
    "final_answer",
]


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, description="Natural language command for Magic.")
    execute: bool | None = Field(
        default=None,
        description="If true, tools execute. If false, dry-run only. If null, use server default.",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional conversation session id so Magic can remember prior context.",
    )
    reasoning_level: ReasoningLevel = Field(
        default="medium",
        description="easy=fastest · medium=balanced · high/extra_high=deeper multi-step (slower).",
    )
    developer_mode: bool = Field(
        default=True,
        description="Bypasses conservative restrictions if True. Recommended.",
    )
    app_mode: Literal["magic", "sisi"] = Field(
        default="magic",
        description="Indicates which app sent the request (chat vs IDE) to optimize system prompts.",
    )


class ToolCall(BaseModel):
    tool: ToolName
    input: str = ""
    reason: str = ""


class CommandResponse(BaseModel):
    mode: Literal["execute", "dry_run"]
    session_id: str
    user_command: str
    reasoning_level: ReasoningLevel = "easy"
    developer_mode: bool = True
    plan: list[ToolCall]
    task_trace: list[str] = []
    outputs: list[str]
    final: str
    used_tools: bool = False


class ConversationTurnModel(BaseModel):
    role: Literal["user", "assistant"]
    content: str
    created_at: str


class ConversationSessionSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    preview: str = ""


class ConversationSessionResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    turns: list[ConversationTurnModel]


class ConversationDeleteResponse(BaseModel):
    status: Literal["deleted"]
    id: str


class IngestRequest(BaseModel):
    path: str | None = Field(
        default=None,
        description="Optional folder or file to ingest; default uses MAGIC_INDEX_PATHS.",
    )
    rebuild: bool = Field(default=False, description="If true, wipe persisted index and rebuild.")


class IngestResponse(BaseModel):
    status: str
    count: int = 0
    message: str | None = None
    persist_dir: str | None = None


class MemoryQueryResponse(BaseModel):
    answer: str
    sources: list[str] = []


class TranscribeResponse(BaseModel):
    text: str
