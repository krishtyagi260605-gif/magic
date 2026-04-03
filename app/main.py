from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.conversation import append_turn, clear_session, ensure_session, format_history, get_session, list_sessions
from app.desktop import get_mouse_position, get_screen_info
from app.graph import run_magic
from app.models import (
    CommandRequest,
    CommandResponse,
    ConversationDeleteResponse,
    ConversationSessionResponse,
    ConversationSessionSummary,
    ConversationTurnModel,
    IngestRequest,
    ApprovalModel,
    ApprovalResolutionRequest,
    IngestResponse,
    MemoryQueryResponse,
    TranscribeResponse,
)
from app.profile import maybe_learn_from_message, profile_stats, profile_summary, record_feedback, remember_fact, set_preference
from app.rag import ingest_paths, query_memory
from app.status import build_runtime_status
from app.voice import transcribe_bytes
from app.workspace import workspace_root, read_workspace_file, write_workspace_file
from app.trace import get_trace

settings = get_settings()


def _collect_response_metadata(
    *,
    command: str,
    plan: list,
    outputs: list[str],
    final: str,
    task_trace: list[str],
) -> dict[str, object]:
    text_blob = "\n".join([*outputs, final])
    files_changed: list[str] = []
    created_artifacts: list[str] = []
    commands_run: list[str] = []
    run_logs: list[str] = []
    verification_results: list[str] = []
    sources: list[str] = []
    errors: list[str] = []
    preview_url: str | None = None
    opened_file: str | None = None

    for output in outputs:
        for pattern in (r"\bWrote\s+(.+)", r"\bPatched\s+(.+)"):
            for match in re.finditer(pattern, output):
                files_changed.append(match.group(1).strip())
        for match in re.finditer(r"Primary file:\s+(.+)", output):
            opened_file = match.group(1).strip()
        if "Logs:" in output:
            run_logs.append(output.split("Logs:", 1)[1].strip())
        if output.startswith("workspace_run ->") or "Started background command" in output or "Generated " in output:
            verification_results.append(output.strip())
        if "BLOCKED:" in output or "failed" in output.lower() or "error" in output.lower():
            errors.append(output.strip())
        if "Artifacts:" in output:
            artifacts_part = output.split("Artifacts:", 1)[1]
            for line in artifacts_part.splitlines():
                if line.strip().startswith("- "):
                    created_artifacts.append(line.strip()[2:])
        for src in re.findall(r"https?://[^\s`]+", output):
            if src not in sources:
                sources.append(src)
        if preview_url is None:
            url_match = re.search(r"https?://[^\s`]+", output)
            if url_match:
                preview_url = url_match.group(0)

    for tool_call in plan:
        if getattr(tool_call, "tool", "") == "workspace_run":
            payload = getattr(tool_call, "input", "")
            try:
                data = json.loads(payload) if payload.strip().startswith("{") else {}
            except Exception:  # noqa: BLE001
                data = {}
            cmd = str(data.get("command", "")).strip()
            if cmd:
                commands_run.append(cmd)

    if not preview_url:
        final_url = re.search(r"https?://[^\s`]+", final)
        if final_url:
            preview_url = final_url.group(0)
    if not opened_file and files_changed:
        opened_file = files_changed[0]
    if not verification_results and task_trace:
        verification_results = [step for step in task_trace if "complete" in step.lower() or "result" in step.lower()]
    return {
        "files_changed": list(dict.fromkeys(files_changed)),
        "created_artifacts": list(dict.fromkeys(created_artifacts)),
        "opened_file": opened_file,
        "preview_url": preview_url,
        "commands_run": list(dict.fromkeys(commands_run)),
        "run_logs": list(dict.fromkeys(run_logs)),
        "verification_results": list(dict.fromkeys(verification_results)),
        "sources": list(dict.fromkeys(sources)),
        "errors": list(dict.fromkeys(errors)),
    }


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        from app.embeddings import configure_llama_global_embeddings
        from app.rag import load_or_build_index
        import threading

        configure_llama_global_embeddings()
        # Auto-build or load RAG index in background on startup
        threading.Thread(target=load_or_build_index, daemon=True).start()
    except Exception as e:  # noqa: BLE001
        print(f"RAG initialization bypassed or failed: {e}")
    yield


app = FastAPI(
    title="Magic API",
    description="Local-first macOS assistant with chat memory, desktop actions, project workspace tools, and voice.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(127\.0\.0\.1|localhost)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATIC = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.get("/", response_class=HTMLResponse)
def ui_magic() -> HTMLResponse:
    index = _STATIC / "magic.html"
    if not index.is_file():
        index = _STATIC / "index.html" # Fallback
    if not index.is_file():
        return HTMLResponse("<p>Magic UI missing.</p>", status_code=500)
    return HTMLResponse(index.read_text(encoding="utf-8"))


@app.get("/sisi", response_class=HTMLResponse)
def ui_sisi() -> HTMLResponse:
    index = _STATIC / "sisi.html"
    if not index.is_file():
        return HTMLResponse("<p>Magic Sisi UI missing.</p>", status_code=500)
    return HTMLResponse(index.read_text(encoding="utf-8"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "name": settings.app_name, "version": app.version}


@app.get("/v1/status")
def runtime_status() -> dict[str, object]:
    return build_runtime_status()


@app.get("/v1/desktop/screen")
def desktop_screen() -> dict[str, int]:
    try:
        return get_screen_info()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"desktop unavailable: {exc}") from exc


@app.get("/v1/desktop/position")
def desktop_position() -> dict[str, int]:
    try:
        return get_mouse_position()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"desktop unavailable: {exc}") from exc


@app.get("/v1/fs/list")
def fs_list(path: str = "") -> dict:
    try:
        root = workspace_root()
        target = (root / path).resolve()
        if not str(target).startswith(str(root)):
            raise ValueError("Path outside workspace")
        if not target.exists():
            return {"files": []}
        
        # Collect recursive paths
        found = []
        for p in target.rglob("*"):
            if p.is_file() and not any(part.startswith(".") for part in p.parts):
                found.append(str(p.relative_to(root)))
                if len(found) > 1000: break
        return {"files": sorted(found)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/fs/read")
def fs_read(path: str) -> dict:
    try:
        content = read_workspace_file(path)
        return {"content": content}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


from pydantic import BaseModel
class FSWriteRequest(BaseModel):
    path: str
    content: str
    overwrite: bool = True

@app.post("/v1/fs/write")
def fs_write(req: FSWriteRequest) -> dict:
    try:
        from app.tools import _trigger_index
        res = write_workspace_file(req.path, req.content, overwrite=req.overwrite)
        _trigger_index()
        return {"status": "ok", "message": res}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/v1/fs/delete")
def fs_delete(path: str) -> dict:
    try:
        from app.workspace import resolve_workspace_path
        target = resolve_workspace_path(path)
        if not target.exists():
            raise FileNotFoundError(f"{path} not found")
        if target.is_dir():
            import shutil
            shutil.rmtree(target)
        else:
            target.unlink()
        from app.tools import _trigger_index
        _trigger_index()
        return {"status": "ok", "message": f"Deleted {path}"}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class ToolExecuteRequest(BaseModel):
    tool: str
    payload: str

@app.post("/v1/tool/execute")
def tool_execute(req: ToolExecuteRequest) -> dict:
    from app.tools import execute_tool_call
    res = execute_tool_call(req.tool, req.payload, execute=True, approval_mode="auto_apply")
    return res.to_dict()

@app.get("/v1/sessions/{session_id}/approvals", response_model=list[ApprovalModel])
def list_approvals(session_id: str) -> list[ApprovalModel]:
    from app.trace import get_pending_approvals
    return get_pending_approvals(session_id)

@app.post("/v1/approvals/{approval_id}/resolve")
def resolve_approval_route(approval_id: str, req: ApprovalResolutionRequest) -> dict:
    from app.trace import resolve_approval
    res = resolve_approval(approval_id, req.action)
    if not res: raise HTTPException(404, "Approval not found")
    return res

@app.post("/v1/sessions/{session_id}/cancel")
def cancel_session_route(session_id: str) -> dict:
    from app.graph import cancel_session
    cancel_session(session_id)
    return {"status": "cancelled"}

@app.post("/v1/command", response_model=CommandResponse)
def command(req: CommandRequest) -> CommandResponse:
    import time
    execute = req.developer_mode if req.execute is None else req.execute
    session_id = ensure_session(req.session_id, req.command)
    append_turn(session_id, "user", req.command)
    maybe_learn_from_message(req.command)
    t0 = time.monotonic()
    plan, outputs, final, task_trace, intent, tool_results = run_magic(
        req.command,
        execute=execute,
        conversation_history=format_history(session_id),
        reasoning_level=req.reasoning_level,
        developer_mode=req.developer_mode,
        app_mode=req.app_mode,
        session_id=session_id,
        approval_mode=req.approval_mode,
    )
    duration_ms = int((time.monotonic() - t0) * 1000)
    metadata = _collect_response_metadata(
        command=req.command,
        plan=plan,
        outputs=outputs,
        final=final,
        task_trace=task_trace,
    )
    
    all_sources = list(metadata["sources"])
    for tr in tool_results:
        all_sources.extend(tr.get("sources", []))
    metadata["sources"] = list(dict.fromkeys(all_sources))
        
    append_turn(session_id, "assistant", final)
    return CommandResponse(
        mode="execute" if execute else "dry_run",
        session_id=session_id,
        user_command=req.command,
        reasoning_level=req.reasoning_level,
        developer_mode=req.developer_mode,
        intent=intent,
        plan=plan,
        task_trace=task_trace,
        outputs=outputs,
        final=final,
        used_tools=bool(outputs),
        duration_ms=duration_ms,
        files_changed=metadata["files_changed"],
        created_artifacts=metadata["created_artifacts"],
        opened_file=metadata["opened_file"],
        preview_url=metadata["preview_url"],
        commands_run=metadata["commands_run"],
        run_logs=metadata["run_logs"],
        verification_results=metadata["verification_results"],
        sources=metadata["sources"],
        errors=metadata["errors"],
        tool_results=tool_results,
    )


@app.post("/v1/command/stream")
async def command_stream(req: CommandRequest) -> StreamingResponse:
    """SSE streaming version of /v1/command — sends real-time events as Magic works."""
    execute = req.developer_mode if req.execute is None else req.execute
    session_id = ensure_session(req.session_id, req.command)
    append_turn(session_id, "user", req.command)
    from app.graph import clear_cancel
    clear_cancel(session_id)
    maybe_learn_from_message(req.command)

    async def event_generator():
        loop = asyncio.get_event_loop()

        def _sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        yield _sse("trace", {"step": "Starting Magic...", "session_id": session_id})

        try:
            plan, outputs, final, task_trace, intent, tool_results = await loop.run_in_executor(
                None,
                lambda: run_magic(
                    req.command,
                    execute=execute,
                    conversation_history=format_history(session_id),
                    reasoning_level=req.reasoning_level,
                    developer_mode=req.developer_mode,
                    app_mode=req.app_mode,
                    session_id=session_id,
                    approval_mode=req.approval_mode,
                ),
            )

            for trace_item in task_trace:
                yield _sse("trace", {"step": trace_item})

            for i, output in enumerate(outputs):
                yield _sse("tool", {"index": i, "output": output[:2000]})
                if "Logs:" in output or "Started background command" in output or "workspace_run ->" in output:
                    yield _sse("terminal", {"text": output})

            append_turn(session_id, "assistant", final)
            metadata = _collect_response_metadata(
                command=req.command,
                plan=plan,
                outputs=outputs,
                final=final,
                task_trace=task_trace,
            )
            
            all_sources = list(metadata["sources"])
            for tr in tool_results:
                all_sources.extend(tr.get("sources", []))
            metadata["sources"] = list(dict.fromkeys(all_sources))
                
            append_turn(session_id, "assistant", final)
            yield _sse("final", {
                "mode": "execute" if execute else "dry_run",
                "session_id": session_id,
                "final": final,
                "used_tools": bool(outputs),
                "plan_count": len(plan),
                "task_trace": task_trace,
                "tool_results": tool_results,
                **metadata,
            })

        except Exception as exc:  # noqa: BLE001
            print(f"Stream error: {exc}")
            yield _sse("error", {
                "message": "Magic encountered an unexpected error. Please try again."
            })

        yield _sse("done", {})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/v1/sessions", response_model=list[ConversationSessionSummary])
def sessions() -> list[ConversationSessionSummary]:
    items: list[ConversationSessionSummary] = []
    for session in list_sessions():
        preview = next((turn.content for turn in reversed(session.turns) if turn.role == "assistant"), "")
        items.append(
            ConversationSessionSummary(
                id=session.id,
                title=session.title,
                created_at=session.created_at,
                updated_at=session.updated_at,
                preview=preview[:140],
            )
        )
    return items


@app.get("/v1/profile")
def profile_get() -> dict[str, object]:
    return {
        "summary": profile_summary(),
        "stats": profile_stats(),
    }


@app.post("/v1/profile/remember")
def profile_remember(body: dict) -> dict[str, object]:
    text = str(body.get("text", "")).strip()
    source = str(body.get("source", "manual")).strip() or "manual"
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    return remember_fact(text, source=source)


@app.post("/v1/profile/preference")
def profile_preference(body: dict) -> dict[str, object]:
    key = str(body.get("key", "")).strip()
    value = str(body.get("value", "")).strip()
    source = str(body.get("source", "manual")).strip() or "manual"
    if not key or not value:
        raise HTTPException(status_code=400, detail="key and value are required")
    return set_preference(key, value, source=source)


@app.post("/v1/profile/feedback")
def profile_feedback(body: dict) -> dict[str, object]:
    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    return record_feedback(text)


@app.get("/v1/sessions/{session_id}", response_model=ConversationSessionResponse)
def session_detail(session_id: str) -> ConversationSessionResponse:
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return ConversationSessionResponse(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        turns=[
            ConversationTurnModel(role=turn.role, content=turn.content, created_at=turn.created_at)
            for turn in session.turns
        ],
    )


@app.patch("/v1/sessions/{session_id}")
def session_rename(session_id: str, body: dict) -> dict:
    """Rename a session title."""
    from app.conversation import get_session as _get, _save, _lock, _ensure_loaded

    _ensure_loaded()
    with _lock:
        session = _get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        new_title = str(body.get("title", "")).strip()
        if new_title:
            session.title = new_title[:60]
            _save()
    return {"status": "renamed", "id": session_id, "title": session.title}


@app.get("/v1/trace/{session_id}")
def session_trace(session_id: str) -> dict:
    """Retrieve the execution trace events for a given session."""
    events = get_trace(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="Trace not found")
    return {"session_id": session_id, "events": events}


@app.get("/v1/sessions/{session_id}/export")
def session_export(session_id: str) -> dict:
    """Export a conversation session as markdown."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    lines = [f"# {session.title}", f"*Created: {session.created_at}*", ""]
    for turn in session.turns:
        role = "**You**" if turn.role == "user" else "**Magic**"
        lines.append(f"### {role} — {turn.created_at}")
        lines.append(turn.content)
        lines.append("")
    return {"markdown": "\n".join(lines), "title": session.title}


@app.delete("/v1/sessions/{session_id}", response_model=ConversationDeleteResponse)
def session_delete(session_id: str) -> ConversationDeleteResponse:
    clear_session(session_id)
    return ConversationDeleteResponse(status="deleted", id=session_id)


@app.post("/v1/index/ingest", response_model=IngestResponse)
def index_ingest(body: IngestRequest) -> IngestResponse:
    extra: list[Path] | None = None
    if body.path:
        extra = [Path(body.path).expanduser().resolve()]
    out = ingest_paths(extra_paths=extra, rebuild=body.rebuild)
    if out.get("status") == "no_documents":
        raise HTTPException(status_code=400, detail=out.get("message", "No documents found"))
    return IngestResponse(
        status=str(out.get("status", "")),
        count=int(out.get("count", 0)),
        message=out.get("message"),
        persist_dir=str(out["persist_dir"]) if out.get("persist_dir") else None,
    )


@app.get("/v1/memory/query", response_model=MemoryQueryResponse)
def memory_query(q: str = Query(..., min_length=1, description="Question over indexed files")) -> MemoryQueryResponse:
    answer, sources = query_memory(q)
    return MemoryQueryResponse(answer=answer, sources=sources)


@app.post("/v1/transcribe", response_model=TranscribeResponse)
async def transcribe(file: UploadFile = File(...)) -> TranscribeResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")
    try:
        text = transcribe_bytes(data, file.filename or "audio.m4a")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TranscribeResponse(text=text)


@app.post("/v1/voice/command", response_model=CommandResponse)
async def voice_command(
    file: UploadFile = File(...),
    execute: bool | None = Form(default=None),
) -> CommandResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")
    try:
        text = transcribe_bytes(data, file.filename or "audio.m4a")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    exec_flag = settings.dry_run_default is False if execute is None else execute
    session_id = ensure_session(None, text)
    append_turn(session_id, "user", text)
    plan, outputs, final, task_trace, intent = run_magic(
        text,
        execute=exec_flag,
        conversation_history=format_history(session_id),
        app_mode="magic",
        session_id=session_id,
    )
    metadata = _collect_response_metadata(
        command=text,
        plan=plan,
        outputs=outputs,
        final=final,
        task_trace=task_trace,
    )
    append_turn(session_id, "assistant", final)
    return CommandResponse(
        mode="execute" if exec_flag else "dry_run",
        session_id=session_id,
        user_command=text,
        reasoning_level="easy",
        developer_mode=exec_flag,
        plan=plan,
        task_trace=task_trace,
        outputs=outputs,
        final=final,
        used_tools=bool(outputs),
        intent=intent,
        files_changed=metadata["files_changed"],
        created_artifacts=metadata["created_artifacts"],
        opened_file=metadata["opened_file"],
        preview_url=metadata["preview_url"],
        commands_run=metadata["commands_run"],
        run_logs=metadata["run_logs"],
        verification_results=metadata["verification_results"],
        sources=metadata["sources"],
        errors=metadata["errors"],
    )
