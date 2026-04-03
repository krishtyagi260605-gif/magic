from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime
from pathlib import Path
from typing import Any
import time
from typing import TypedDict, Annotated
import operator

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END

from app.config import get_settings
from app.fallback_planner import fallback_plan, fallback_reply
from app.llm import LLMProfile, get_llm, set_last_providers
from app.models import ReasoningLevel, ToolCall
from app.profile import profile_summary
from app.rag import query_memory
from app.tools import execute_tool_call, summarize_tool_output, tool_catalog_json
from app.workspace import workspace_root, workspace_snapshot
try:
    from app.trace import append_trace
except ImportError:
    append_trace = lambda s, e, d: None

_llm_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="magic-llm")

ALLOWED_TOOLS = {
    "run_shortcut",
    "run_applescript",
    "run_shell",
    "web_search",
    "query_memory",
    "desktop",
    "workspace_list",
    "workspace_read",
    "workspace_write",
    "workspace_patch",
    "workspace_git",
    "workspace_archive",
    "project_scaffold",
    "workspace_run",
    "fetch_url",
    "execute_python",
    "browser_action",
    "final_answer",
    "send_whatsapp_messages",
    "linkedin_auto_apply",
}

ASSISTANT_ROUTER_PROMPT = """You classify the user's message for Magic — a powerful macOS AI assistant.

First, identify the INTENT: chat, code_generation, edit_project, debug_fix, build_new_app, web_research, browser_action, desktop_action, document_gen, spreadsheet_gen.

Then choose ONE mode:
- "reply" → For chat, explanation, brainstorming, or code review.
- "act" → For anything else (build_new_app, edit_project, desktop_action, web_research, document_gen, spreadsheet_gen, debug_fix).

Decision rules:
1. "how do I…" / "explain…" / "compare…" → reply (unless they say "do it", "now", or "on my Mac")
2. "build…" / "create…" / "fix this app" / "search…" / "run…" → act
3. "make an excel/CSV/report/PPT" → act
4. Ambiguous "make an app" → reply (to extract design spec).

Return STRICT JSON only (no markdown fences, no extra text):
{"intent": "<identified intent>", "mode": "reply|act", "reason": "one short sentence"}
"""

MASTERPIECE_DESIGN_GUIDE = """You are a world-class UI/UX Designer and Senior Software Engineer. When building any software or UI:
1. **Layout**: Use Modern CSS (Flexbox, Grid). No tables. Favor "Bento Grids" or clean asymmetrical layouts.
2. **Styling**: Always include modern CSS features: `backdrop-filter: blur()`, `linear-gradients`, `box-shadow` with soft opacities.
3. **Code Quality**: Write robust, modular, and error-handled code. NEVER use placeholders like 'TODO: implement this'.
4. **Color**: Use a refined color palette. If they say "Dark mode", use deep charcoal (#09090b or #18181b), not pure black. 
5. **Interactive**: Use CSS transitions on hover state (transform: translateY(-2px)).
6. **Completeness**: Provide the FULL working code. Incomplete files are unacceptable.
7. **Mobile First**: Ensure responsiveness using `@media` queries.
"""

DIRECT_REPLY_PROMPT = f"""You are Magic — a premium local AI assistant. Respond with the quality of GPT-4/Claude. 

{MASTERPIECE_DESIGN_GUIDE}

Style rules:
1. **Be Direct**: Lead with the answer or the solution. Minimize conversational filler.
2. **Spec Extraction Layer**: If the user asks to "make a website" or "build an app", extract the spec. Propose 3 distinct design concepts (e.g. "Glassmorphic Dark", "Clean Apple-esque"). Ask for their preference.
3. **Masterpiece Coding**: When you do write code, it must be breathtaking. Use advanced CSS, flexbox/grid layouts, smooth gradients, and micro-interactions.
4. **Scanability**: Use markdown, headers, and bullet points to make your response easy to digest.
"""

ACTION_PROMPT = f"""You are an autonomous agent identifying the single best next step.

{MASTERPIECE_DESIGN_GUIDE}

Tool priority:
1. **final_answer** — Use this when the task is done, or you have a complete plan to present.
2. **web_search** — Use this for any external facts, comparisons, or live data.
3. **workspace_list → workspace_read → workspace_write/workspace_patch** — Check existing files before writing. Use `workspace_patch` for surgical code edits instead of rewriting everything.
4. **run_shell** — For system commands (open apps, shell scripts, etc).
5. **workspace_run** — For dev tools (npm, python, etc) inside projects.
6. **workspace_git / workspace_archive** — For version control or zipping.
7. **query_memory / project_scaffold / desktop** — Use these as needed for personal files, new projects, or UI automation.
8. **fetch_url / browser_action / execute_python** — Scrape sites, automate the browser, or run sandboxed python.

Anti-hallucination:
- Do NOT guess file names; use workspace_list.
- If you need clarification to proceed, use final_answer to ask the user.

You MUST call exactly one tool from the functions provided to you.
"""

SYNTHESIS_PROMPT = """You summarize what Magic (a macOS AI assistant) just accomplished for the user. Write like a senior engineer giving a concise status update.

Format rules:
1. **Start with the result.** "Done — " / "Created — " / "Found — " etc.
2. **Use markdown.** Bold key names. Use code blocks for commands.
3. **Acknowledge failures gracefully.** If a tool failed, summarize it in a human way and suggest the next best action.
4. **No Sources:** Do NOT output URL lists. The UI will render source pills automatically based on tool metadata.
5. **End with next steps** if relevant.

Keep it brief and professional. Do not output JSON.
"""


def _assistant_identity() -> str:
    settings = get_settings()
    return (
        f"Assistant name: Magic\n"
        f"Owner / creator: {settings.owner_name}\n"
        "Runtime routing:\n"
        "- easy/medium: Fast models for speed\n"
        "- high/extra_high: Deep models for complex reasoning\n"
        "If the user asks who owns or made Magic, answer with the owner name directly."
    )


def _provider_timeout_message(timeout: int) -> str:
    settings = get_settings()
    provider = settings.llm_provider.capitalize()
    return f"{provider} API timed out after {timeout}s"


def _assistant_error_message(detail: str) -> str:
    clean = (detail or "").strip()
    if "timed out" in clean.lower():
        return "Magic took too long on that request. Try `easy` or `medium` mode, or make the request more specific."
    return "Magic encountered an issue processing that request. Please try again or rephrase."


def _profile_context() -> str:
    try:
        return profile_summary()
    except Exception as exc:  # noqa: BLE001
        return f"(Personal memory unavailable right now: {exc})"


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip().strip("`")
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:  # noqa: BLE001
        pass

    start = cleaned.find("{")
    while start != -1:
        depth = 0
        for idx in range(start, len(cleaned)):
            char = cleaned[idx]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start : idx + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict):
                            return parsed
                    except Exception:  # noqa: BLE001
                        break
        start = cleaned.find("{", start + 1)
    raise ValueError("No valid JSON object found in model response")


def _needs_memory_context(command: str) -> bool:
    lower = command.lower()
    return any(
        term in lower
        for term in (
            "memory",
            "remember",
            "notes",
            "documents",
            "my files",
            "my docs",
            "indexed",
            "search my",
            "summarize my",
        )
    )


def _memory_context(command: str) -> str:
    if not _needs_memory_context(command):
        return "(memory lookup skipped)"
    try:
        text, _ = query_memory(command)
        return text
    except Exception as exc:  # noqa: BLE001
        return f"(Memory unavailable right now: {exc})"


def _workspace_context() -> str:
    try:
        return workspace_snapshot()
    except Exception as exc:  # noqa: BLE001
        return f"(Workspace unavailable right now: {exc})"


def _trimmed(text: str, limit: int) -> str:
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean or "(empty)"
    return clean[: limit - 24].rstrip() + "\n...[truncated]"


def _history_block(history: list[dict[str, str]]) -> str:
    if not history:
        return "(no tool steps yet)"
    lines: list[str] = []
    for item in history[-8:]:
        lines.append(
            "\n".join(
                [
                    f"Step {item['step']}",
                    f"tool: {item['tool']}",
                    f"input: {item['input']}",
                    f"reason: {item['reason']}",
                    f"ok: {item['ok']}",
                    f"observation: {item['observation']}",
                ]
            )
        )
    return "\n\n".join(lines)


def _reasoning_settings(level: ReasoningLevel) -> dict[str, int]:
    settings = get_settings()
    return {
        "easy": {"history_chars": 600, "memory_chars": 400, "workspace_chars": 500, "max_steps": 2, "timeout": 30},
        "medium": {"history_chars": 1200, "memory_chars": 800, "workspace_chars": 800, "max_steps": 4, "timeout": 60},
        "high": {"history_chars": 2000, "memory_chars": 1200, "workspace_chars": 1200, "max_steps": 6, "timeout": 120},
        "extra_high": {
            "history_chars": settings.agent_history_max_chars,
            "memory_chars": 2200,
            "workspace_chars": 2200,
            "max_steps": settings.agent_max_steps,
            "timeout": 300,
        },
    }[level]


def _timeout_for_profile(reasoning_level: ReasoningLevel, profile: LLMProfile) -> int:
    base = _reasoning_settings(reasoning_level)["timeout"]
    if profile == "router":
        return min(45, max(15, base // 3))
    if profile == "synthesis":
        return min(180, int(base * 1.5))
    return base


def _run_with_retries(func, session_id: str | None, timeout: int) -> Any:
    settings = get_settings()
    max_attempts = settings.llm_max_retries
    providers = [settings.llm_provider]
    if settings.llm_fallback_providers:
        fallbacks = [p.strip() for p in settings.llm_fallback_providers.split(",") if p.strip()]
        for p in fallbacks:
            if p and p not in providers:
                providers.append(p)

    last_exc = None
    if session_id:
        append_trace(session_id, "llm_initial_provider", {"provider": providers[0]})
        
    for i, provider in enumerate(providers):
        is_fallback = i > 0
        if is_fallback and session_id:
            append_trace(session_id, "llm_fallback_transition", {"from": providers[i-1], "to": provider})
            append_trace(session_id, "llm_fallback_selected", {"provider": provider})
        for attempt in range(max_attempts):
            try:
                future = _llm_pool.submit(lambda p=provider: func(p))
                res = future.result(timeout=timeout)
                if session_id:
                    append_trace(session_id, "llm_success", {"provider": provider, "attempt": attempt + 1})
                    append_trace(session_id, "llm_final_provider", {"provider": provider})
                set_last_providers(provider, is_fallback)
                return res
            except FuturesTimeout as exc:
                last_exc = exc
                if session_id:
                    append_trace(session_id, "llm_retry", {"attempt": attempt + 1, "provider": provider, "error": "timeout"})
            except Exception as exc:
                last_exc = exc
                if session_id:
                    append_trace(session_id, "llm_retry", {"attempt": attempt + 1, "provider": provider, "error": str(exc)})
            time.sleep(1.5 ** attempt)
            
    if session_id:
        append_trace(session_id, "llm_fatal_error", {"error": "All providers and retries failed.", "last_exc": str(last_exc)})
    raise last_exc or TimeoutError("All providers and retries failed.")


def _invoke_llm(
    messages: list[SystemMessage | HumanMessage],
    reasoning_level: ReasoningLevel,
    *,
    profile: LLMProfile = "action",
    session_id: str | None = None,
) -> str:
    timeout = _timeout_for_profile(reasoning_level, profile)
    
    def _call(provider: str) -> Any:
        return get_llm(reasoning_level, profile=profile, provider_override=provider).invoke(messages)
        
    response = _run_with_retries(_call, session_id, timeout)
    return str(response.content)

def _prefer_fallback_now(command: str, reasoning_level: ReasoningLevel, developer_mode: bool) -> bool:
    lower = command.lower().strip()
    instant_starts = (
        "what time",
        "who am i",
        "whoami",
        "where am i",
        "pwd",
    )
    if lower.startswith(instant_starts):
        return True
    if any(phrase in lower for phrase in ("who owns you", "who made you", "who created you")):
        return True
    return False


def _router_decision(
    command: str,
    execute: bool,
    reasoning_level: ReasoningLevel,
    memory_context: str,
    workspace_context: str,
    conversation_history: str,
    app_mode: str = "magic",
) -> dict[str, str]:
    tuning = _reasoning_settings(reasoning_level)
    prompt = "\n\n".join(
        [
            _assistant_identity(),
            f"Personal memory:\n{_profile_context()}",
            f"Current date and time: {datetime.now().isoformat(timespec='seconds')}",
            f"Reasoning level: {reasoning_level}",
            f"Execution mode: {'REAL EXECUTION' if execute else 'DRY RUN / PREVIEW'}",
            f"Recent conversation:\n{_trimmed(conversation_history, tuning['history_chars'])}",
            f"User request:\n{command}",
            f"Relevant memory:\n{_trimmed(memory_context, tuning['memory_chars'])}",
            f"Workspace snapshot:\n{_trimmed(workspace_context, tuning['workspace_chars'])}",
        ]
    )
    base_sys = ASSISTANT_ROUTER_PROMPT
    if app_mode == "sisi":
        base_sys += "\n\nAPP MODE [SISI]: User is in the IDE interface. You MUST choose 'act' for almost everything, especially if they are asking to write code, build a feature, or fix a bug. ONLY choose 'reply' for pure conceptual questions."

    response = _invoke_llm(
        [SystemMessage(content=base_sys), HumanMessage(content=prompt)],
        reasoning_level,
        profile="router",
        session_id=None,
    )
    parsed = _extract_json_object(response)
    mode = str(parsed.get("mode", "")).strip().lower()
    if mode not in {"reply", "act"}:
        raise ValueError(f"Invalid assistant mode: {mode}")
    return {
        "mode": mode,
        "intent": str(parsed.get("intent", "")),
        "reason": str(parsed.get("reason", "")),
    }


def _generate_direct_reply(
    command: str,
    execute: bool,
    reasoning_level: ReasoningLevel,
    memory_context: str,
    workspace_context: str,
    conversation_history: str,
    app_mode: str = "magic",
) -> str:
    tuning = _reasoning_settings(reasoning_level)
    prompt = "\n\n".join(
        [
            _assistant_identity(),
            f"Personal memory:\n{_profile_context()}",
            f"Current date and time: {datetime.now().isoformat(timespec='seconds')}",
            f"Reasoning level: {reasoning_level}",
            f"Execution mode: {'REAL EXECUTION' if execute else 'DRY RUN / PREVIEW'}",
            f"Recent conversation:\n{_trimmed(conversation_history, tuning['history_chars'])}",
            f"Relevant memory:\n{_trimmed(memory_context, tuning['memory_chars'])}",
            f"Workspace snapshot:\n{_trimmed(workspace_context, tuning['workspace_chars'])}",
            f"User request:\n{command}",
        ]
    )
    base_sys = DIRECT_REPLY_PROMPT
    if app_mode == "sisi":
        base_sys += "\n\nAPP MODE [SISI]: You are Magic Sisi, an expert IDE assistant. Provide raw, breathtaking, complete code. ZERO conversational filler. Be incredibly concise to save time."
    
    # Also enforce masterpiece coding in general Chat
    base_sys += "\nCODING STANDARD: Whenever code is requested, never write basic boilerplate. Write complete, production-grade, visually stunning masterpieces full of rich CSS styling, flexbox/grids, and robust logic. DO NOT use placeholders like '...code here...'."
    
    response = _invoke_llm(
        [SystemMessage(content=base_sys), HumanMessage(content=prompt)],
        reasoning_level,
        profile="chat",
        session_id=None,
    )
    return response.strip()

def _get_langchain_tools() -> list[dict[str, Any]]:
    catalog = json.loads(tool_catalog_json())
    tools = []
    for t in catalog["tools"]:
        tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": {
                    "type": "object",
                    "properties": {
                        "payload": {
                            "type": "string",
                            "description": "The exact string or JSON payload required for this tool. E.g. " + t["input"]
                        },
                        "reason": {
                            "type": "string",
                            "description": "One sentence explaining why you are using this tool."
                        }
                    },
                    "required": ["payload", "reason"]
                }
            }
        })
    return tools

def _choose_next_action(
    command: str,
    execute: bool,
    reasoning_level: ReasoningLevel,
    memory_context: str,
    workspace_context: str,
    conversation_history: str,
    history: list[dict[str, str]],
    app_mode: str = "magic",
) -> dict[str, str]:
    tuning = _reasoning_settings(reasoning_level)
    prompt = "\n\n".join(
        [
            _assistant_identity(),
            f"Personal memory:\n{_profile_context()}",
            f"Current date and time: {datetime.now().isoformat(timespec='seconds')}",
            f"Reasoning level: {reasoning_level}",
            f"Execution mode: {'REAL EXECUTION' if execute else 'DRY RUN / PREVIEW'}",
            f"Recent conversation:\n{_trimmed(conversation_history, tuning['history_chars'])}",
            f"User request:\n{command}",
            f"Relevant memory:\n{_trimmed(memory_context, tuning['memory_chars'])}",
            f"Workspace snapshot:\n{_trimmed(workspace_context, tuning['workspace_chars'])}",
            f"Previous steps and observations:\n{_history_block(history)}",
            "Choose the single best next action now by calling a tool function.",
        ]
    )
    base_sys = ACTION_PROMPT
    if app_mode == "sisi":
        base_sys += "\n\nAPP MODE [SISI]: You are playing the role of Magic Sisi, an expert autonomous IDE agent (like Cursor/Devin).\n"
        base_sys += "1. NEVER OUTPUT CODE IN CHAT: Always use the `workspace_write` tool to create or update files directly in the workspace. Avoid using `final_answer` to provide code.\n"
        base_sys += "2. NO LAZY MODULES: Deliver comprehensive, fully implemented code without placeholders. Ensure proper JSON escaping for content strings.\n"
        base_sys += "3. DO NOT ASK FOR PERMISSION: If the user describes a feature, write the files immediately."
    
    timeout = _timeout_for_profile(reasoning_level, "action")
    def _call(provider: str) -> Any:
        llm = get_llm(reasoning_level, profile="action", provider_override=provider)
        llm_with_tools = llm.bind_tools(_get_langchain_tools())
        return llm_with_tools.invoke([SystemMessage(content=base_sys), HumanMessage(content=prompt)])
        
    response = _run_with_retries(_call, None, timeout)

    if hasattr(response, "tool_calls") and response.tool_calls:
        tc = response.tool_calls[0]
        tool_name = tc["name"]
        args = tc.get("args", {})
        
        payload_val = args.get("payload")
        if payload_val is None:
            # Model may have flattened the payload
            flattened = {k: v for k, v in args.items() if k != "reason"}
            if flattened:
                import json
                payload_str = json.dumps(flattened)
            else:
                payload_str = ""
        elif isinstance(payload_val, dict):
            import json
            payload_str = json.dumps(payload_val)
        else:
            payload_str = str(payload_val)

        return {
            "tool": tool_name,
            "input": payload_str,
            "reason": str(args.get("reason", "")),
            "final": payload_str if tool_name == "final_answer" else ""
        }
    
    content = str(response.content).strip()
    try:
        parsed = _extract_json_object(content)
        tool = str(parsed.get("tool", "final_answer")).strip()
        return {
            "tool": tool,
            "input": str(parsed.get("input", "")),
            "reason": str(parsed.get("reason", "")),
            "final": str(parsed.get("final", parsed.get("input", ""))) if tool == "final_answer" else ""
        }
    except Exception:
        return {
            "tool": "final_answer",
            "input": content,
            "reason": "model replied with plain text",
            "final": content
        }


def _synthesize_reply(
    command: str,
    execute: bool,
    reasoning_level: ReasoningLevel,
    conversation_history: str,
    workspace_context: str,
    outputs: list[str],
    history: list[dict[str, str]],
    app_mode: str = "magic",
) -> str:
    tuning = _reasoning_settings(reasoning_level)
    transcript = "\n\n".join(outputs[-8:]) or _history_block(history)
    prompt = "\n\n".join(
        [
            _assistant_identity(),
            f"Personal memory:\n{_profile_context()}",
            f"Reasoning level: {reasoning_level}",
            f"Execution mode: {'REAL EXECUTION' if execute else 'DRY RUN / PREVIEW'}",
            f"Recent conversation:\n{_trimmed(conversation_history, tuning['history_chars'])}",
            f"Original request:\n{command}",
            f"Workspace snapshot:\n{_trimmed(workspace_context, tuning['workspace_chars'])}",
            f"Tool transcript:\n{_trimmed(transcript, 2600)}",
        ]
    )
    base_sys = SYNTHESIS_PROMPT
    if app_mode == "sisi":
        base_sys += "\n\nAPP MODE [SISI]: Provide zero chit-chat. The user is in an IDE. Conclude silently or simply state that the files were created/modified. Print the exact final code changes if requested."
    response = _invoke_llm(
        [SystemMessage(content=base_sys), HumanMessage(content=prompt)],
        reasoning_level,
        profile="synthesis",
        session_id=None,
    )
    return response.strip() or "Done."


_CANCEL_FLAGS: set[str] = set()

def cancel_session(session_id: str) -> None:
    if session_id:
        _CANCEL_FLAGS.add(session_id)

def clear_cancel(session_id: str) -> None:
    _CANCEL_FLAGS.discard(session_id)

def is_cancelled(session_id: str) -> bool:
    return session_id in _CANCEL_FLAGS

class AgentState(TypedDict):
    command: str
    session_id: str
    execute: bool
    reasoning_level: ReasoningLevel
    developer_mode: bool
    approval_mode: str
    app_mode: str
    memory_context: str
    workspace_context: str
    conversation_history: str
    
    intent: str
    awaiting_response: bool
    pending_question: str
    collected_info: dict
    analysis: str
    plan: Annotated[list[ToolCall], operator.add]
    outputs: Annotated[list[str], operator.add]
    tool_results: Annotated[list[dict], operator.add]
    task_trace: Annotated[list[str], operator.add]
    history: Annotated[list[dict[str, str]], operator.add]
    final: str
    iteration: int
    llm_error: str

def clarifier_node(state: AgentState) -> dict:
    if is_cancelled(state["session_id"]): return {"llm_error": "Cancelled by user"}
    intent = state.get("intent", "")
    command_lower = state["command"].lower()
    
    history = state.get("conversation_history", "").lower() + " " + command_lower
    
    is_backend = "backend" in history or "api" in history or "database" in history or "fastapi" in history
    
    if ("scaffold" in intent or "build a" in history or "make a" in history) and is_backend:
        try:
            from app.project_questions import get_missing_project_info
        except ImportError:
            return {}
            
        collected_info = state.get("collected_info", {}).copy()
        
        if "postgresql" in history or "postgres" in history: collected_info["database"] = "postgresql"
        elif "sqlite" in history: collected_info["database"] = "sqlite"
        elif "mongodb" in history: collected_info["database"] = "mongodb"
        
        if "jwt" in history: collected_info["auth_type"] = "jwt"; collected_info["auth"] = "yes"
        elif "oauth" in history: collected_info["auth_type"] = "oauth"; collected_info["auth"] = "yes"
        elif "session" in history: collected_info["auth_type"] = "session"; collected_info["auth"] = "yes"
        elif "no auth" in history or "without auth" in history: collected_info["auth"] = "no"
        
        missing = get_missing_project_info(command_lower, collected_info)
        if missing:
            question = missing[0]["question"]
            return {"awaiting_response": True, "pending_question": question, "collected_info": collected_info, "plan": [ToolCall(tool="final_answer", input=question, reason="clarify backend requirements")], "final": question}
            
    if "make a website" in command_lower or "build a website" in command_lower:
        if "react" not in command_lower and "backend" not in command_lower:
            question = "I'll generate a React frontend for your website. Do you also need a backend (API/database)?"
            return {"awaiting_response": True, "pending_question": question, "plan": [ToolCall(tool="final_answer", input=question, reason="clarify frontend/backend")], "final": question}

    return {}


def analyze_node(state: AgentState) -> dict:
    if is_cancelled(state["session_id"]): return {"llm_error": "Cancelled by user"}
    append_trace(state["session_id"], "analyze", {"command": state["command"]})
    
    intent = state.get("intent", "")
    if intent in {"code_generation", "edit_project", "debug_fix", "build_new_app"}:
        prompt = f"Task: {state['command']}\nWorkspace: {_trimmed(state['workspace_context'], 2000)}"
        sys = "Analyze the workspace. Output a concise 3-sentence technical approach including target files, risks, and entrypoints."
        try:
            analysis = _invoke_llm([SystemMessage(content=sys), HumanMessage(content=prompt)], state["reasoning_level"], profile="router")
        except Exception as e:
            analysis = f"Analysis failed: {e}"
        return {"analysis": analysis, "task_trace": ["Workspace analysis complete"]}
        
    return {"analysis": "No deep analysis needed for this intent.", "task_trace": ["Workspace analysis skipped"]}


def plan_node(state: AgentState) -> dict:
    if is_cancelled(state["session_id"]): return {"llm_error": "Cancelled by user"}
    iteration = state.get("iteration", 0)
    append_trace(state["session_id"], "plan", {"iteration": iteration})
    try:
        next_action = _choose_next_action(
            state["command"], state["execute"], state["reasoning_level"],
            state["memory_context"], state["workspace_context"], 
            state["conversation_history"], state.get("history", []), state["app_mode"]
        )
        tc = ToolCall(tool=next_action["tool"], input=next_action.get("input", ""), reason=next_action.get("reason", ""))
        if tc.tool == "final_answer":
            return {"plan": [tc], "task_trace": ["Final answer ready"], "final": next_action.get("final", "")}
        return {"plan": [tc], "task_trace": [f"Chose tool: {tc.tool}"]}
    except Exception as exc:
        return {"llm_error": str(exc)}


def execute_node(state: AgentState) -> dict:
    if is_cancelled(state["session_id"]): return {"llm_error": "Cancelled by user"}
    tc = state["plan"][-1]
    append_trace(state["session_id"], "execute", {"tool": tc.tool, "input": tc.input})
    if tc.tool == "final_answer":
        return {}
    
    result = execute_tool_call(tc.tool, tc.input, execute=state["execute"], approval_mode=state["approval_mode"])
    obs = summarize_tool_output(result.output)
    hist_item = {
        "step": str(state.get("iteration", 0) + 1),
        "tool": tc.tool,
        "input": tc.input,
        "reason": tc.reason,
        "ok": "yes" if result.ok else "no",
        "observation": obs,
    }
    append_trace(state["session_id"], "tool_result", {"tool": tc.tool, "ok": result.ok, "output": result.output})
    
    tr_dict = result.to_dict()
    tr_dict["payload"] = tc.input
    return {
        "outputs": [f"{tc.tool} -> {result.output}"],
        "tool_results": [tr_dict],
        "history": [hist_item],
        "task_trace": [f"{tc.tool}: {tc.reason or 'working'}"]
    }


def reflect_node(state: AgentState) -> dict:
    if is_cancelled(state["session_id"]): return {"llm_error": "Cancelled by user"}
    append_trace(state["session_id"], "reflect", {"iteration": state["iteration"]})
    return {"iteration": state.get("iteration", 0) + 1}


def finalize_node(state: AgentState) -> dict:
    if is_cancelled(state["session_id"]): return {"llm_error": "Cancelled by user"}
    if state.get("final"):
        append_trace(state["session_id"], "finalize", {"final": state["final"]})
        return {}
    try:
        final = _synthesize_reply(
            state["command"], state["execute"], state["reasoning_level"],
            state["conversation_history"], state["workspace_context"], 
            state["outputs"], state["history"], state["app_mode"]
        )
        append_trace(state["session_id"], "finalize", {"final": final})
        return {"final": final, "task_trace": ["Final synthesis complete"], "plan": [ToolCall(tool="final_answer", input="", reason="synthesized")]}
    except Exception as exc:
        return {"llm_error": str(exc)}


def should_continue(state: AgentState) -> str:
    if is_cancelled(state["session_id"]): return END
    if state.get("llm_error"): return END
    if state.get("plan") and state["plan"][-1].tool == "final_answer": return "finalize"
    # Prevent infinite loop recursively; dynamic cap instead of fixed step limit
    return "plan" if state["iteration"] < 25 else "finalize"

def should_continue_from_clarifier(state: AgentState) -> str:
    if state.get("awaiting_response"): return "finalize"
    return "plan"

_workflow = StateGraph(AgentState)
_workflow.add_node("analyze", analyze_node)
_workflow.add_node("clarify", clarifier_node)
_workflow.add_node("plan", plan_node)
_workflow.add_node("execute", execute_node)
_workflow.add_node("reflect", reflect_node)
_workflow.add_node("finalize", finalize_node)

_workflow.set_entry_point("analyze")
_workflow.add_edge("analyze", "clarify")
_workflow.add_conditional_edges("clarify", should_continue_from_clarifier, {"plan": "plan", "finalize": "finalize"})
_workflow.add_edge("plan", "execute")
_workflow.add_edge("execute", "reflect")
_workflow.add_conditional_edges("reflect", should_continue, {"plan": "plan", "finalize": "finalize", END: END})
_workflow.add_edge("finalize", END)

agent_graph = _workflow.compile()


def _run_fallback_plan(command: str, execute: bool, conversation_history: str = "") -> tuple[list[ToolCall], list[str], str]:
    steps, final = fallback_plan(command, conversation_history)
    if not steps:
        return [ToolCall(tool="final_answer", input="", reason="fallback unavailable")], [], final or "Done."

    plan = [ToolCall(tool=item["tool"], input=item.get("input", ""), reason=item.get("reason", "")) for item in steps]
    outputs: list[str] = []
    first_result_output = ""
    first_tool = ""
    last_project_cwd = ""
    started_url = ""
    created_path = ""
    for step in steps:
        if step["tool"] == "final_answer":
            continue
        payload = step.get("input", "")
        if "__LAST_PROJECT__" in payload and last_project_cwd:
            payload = payload.replace("__LAST_PROJECT__", last_project_cwd)
        result = execute_tool_call(step["tool"], payload, execute=execute)
        outputs.append(f"{step['tool']} -> {result.output}")
        if not first_result_output:
            first_result_output = result.output
            first_tool = step["tool"]
        if step["tool"] == "project_scaffold":
            match = Path(str(result.output).split(" at ", 1)[1].splitlines()[0].strip()) if " at " in str(result.output) else None
            try:
                if match is not None:
                    created_path = str(match.resolve())
                    last_project_cwd = str(match.resolve().relative_to(workspace_root()))
            except Exception:  # noqa: BLE001
                last_project_cwd = match.name if match is not None else ""
                created_path = str(match) if match is not None else ""
        if step["tool"] == "workspace_run":
            if "4173" in payload:
                started_url = "http://127.0.0.1:4173"
            elif "8010" in payload:
                started_url = "http://127.0.0.1:8010"

    if first_tool in {"web_search", "query_memory"} and first_result_output.strip():
        return plan, outputs, first_result_output.strip()
    if created_path and started_url:
        return plan, outputs, f"Created the project at {created_path} and started it at {started_url}."
    if created_path:
        return plan, outputs, f"Created the project at {created_path}."
    return plan, outputs, final or "Done."


def run_magic(
    command: str,
    execute: bool,
    conversation_history: str = "",
    reasoning_level: ReasoningLevel = "medium",
    developer_mode: bool = False,
    app_mode: str = "magic",
    session_id: str = "",
    approval_mode: str = "ask_before_apply",
) -> tuple[list[ToolCall], list[str], str, list[str], str, list[dict]]:
    """Returns (plan, outputs, final_text, task_trace, intent)."""
    memory_context = _memory_context(command)
    current_workspace = _workspace_context()
    history: list[dict[str, str]] = []
    plan: list[ToolCall] = []
    outputs: list[str] = []
    task_trace: list[str] = []
    intent = ""

    fallback_steps, fallback_final = fallback_plan(command, conversation_history)

    if fallback_steps and _prefer_fallback_now(command, reasoning_level, developer_mode):
        plan, outputs, final = _run_fallback_plan(command, execute, conversation_history)
        task_trace.extend(["Instant action matched", "Skipping slow planner", "Returning result"])
        return plan, outputs, final, task_trace, "desktop_action", []

    try:
        task_trace.append("Choosing reply mode")
        route = _router_decision(command, execute, reasoning_level, memory_context, current_workspace, conversation_history, app_mode)
        intent = route.get("intent", "")
        if route["mode"] == "reply":
            task_trace.append("Generating direct answer")
            final = _generate_direct_reply(command, execute, reasoning_level, memory_context, current_workspace, conversation_history, app_mode)
            if final:
                task_trace.append("Direct answer complete")
                return [ToolCall(tool="final_answer", input="", reason=route["reason"] or "direct assistant reply")], [], final, task_trace, intent or "chat", []
    except Exception as exc:  # noqa: BLE001
        llm_error = str(exc)
        if fallback_steps and len(fallback_steps) > 1:
            plan, outputs, final = _run_fallback_plan(command, execute, conversation_history)
            task_trace.extend(["Planner unavailable", "Using fallback plan"])
            return plan, outputs, final, task_trace, intent, []
        canned = fallback_reply(command)
        if canned:
            task_trace.extend(["Planner unavailable", "Using fallback reply"])
            return [ToolCall(tool="final_answer", input="", reason="fallback reply")], [], canned, task_trace, intent, []
        return (
            [ToolCall(tool="final_answer", input="", reason="assistant unavailable")],
            [],
            _assistant_error_message(llm_error),
            task_trace,
            intent,
            []
        )

    initial_state = {
        "command": command,
        "session_id": session_id,
        "execute": execute,
        "reasoning_level": reasoning_level,
        "developer_mode": developer_mode,
        "approval_mode": approval_mode,
        "app_mode": app_mode,
        "memory_context": memory_context,
        "workspace_context": current_workspace,
        "conversation_history": conversation_history,
        "intent": intent,
        "awaiting_response": False,
        "pending_question": "",
        "collected_info": {},
        "analysis": "",
        "plan": [],
        "outputs": [],
        "tool_results": [],
        "task_trace": task_trace,
        "history": [],
        "final": "",
        "iteration": 0,
        "llm_error": ""
    }

    try:
        final_state = agent_graph.invoke(initial_state)
        if final_state.get("llm_error"):
            llm_error = final_state["llm_error"]
        else:
            return final_state["plan"], final_state["outputs"], final_state["final"], final_state["task_trace"], final_state["intent"], final_state.get("tool_results", [])
    except Exception as exc:
        llm_error = str(exc)

    if fallback_steps and len(fallback_steps) > 1:
        plan, outputs, final = _run_fallback_plan(command, execute, conversation_history)
        task_trace.extend(["No confident LLM path", "Using fallback plan"])
        return plan, outputs, final, task_trace, intent, []

    canned = fallback_reply(command)
    if canned:
        if not plan or plan[-1].tool != "final_answer":
            plan.append(ToolCall(tool="final_answer", input="", reason="fallback reply"))
        task_trace.extend(["No confident LLM path", "Using fallback reply"])
        return plan, outputs, canned, task_trace, intent, []

    final = (
        "Magic could not confidently complete that request."
        if not llm_error
        else _assistant_error_message(llm_error)
    )
    if fallback_final and fallback_steps:
        final = fallback_final
    if not plan or plan[-1].tool != "final_answer":
        plan.append(ToolCall(tool="final_answer", input="", reason="no viable action"))
    return plan, outputs, final, task_trace, intent, []
