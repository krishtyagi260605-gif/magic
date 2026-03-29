from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.fallback_planner import fallback_plan, fallback_reply
from app.llm import LLMProfile, get_llm
from app.models import ReasoningLevel, ToolCall
from app.rag import query_memory
from app.tools import execute_tool_call, summarize_tool_output, tool_catalog_json
from app.workspace import workspace_root, workspace_snapshot

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
    "project_scaffold",
    "workspace_run",
    "final_answer",
}

ASSISTANT_ROUTER_PROMPT = """You classify the user's message for Magic — a powerful macOS AI assistant.

Choose ONE mode:
- "reply" → user wants conversation, explanation, advice, brainstorming, code review, or any answer that does NOT require executing tools on this Mac right now.
- "act" → user wants something DONE: open/launch apps, create files/folders, build projects, run commands, search live web data, query their personal files, automate the desktop, or modify their workspace.

Decision rules:
1. "how do I…" / "explain…" / "compare…" / "what is…" / "ideas for…" → reply (unless they say "do it", "now", or "on my Mac")
2. "open…" / "build…" / "create…" / "search…" / "find…" / "run…" / "host…" / "deploy…" → act
3. If Ambiguous (e.g. "make a website", "build an app" without any details), lean toward "reply" to ask for design details.
4. If the user says "do it" or "go ahead" after you've provided a plan → act.

Return STRICT JSON only (no markdown fences, no extra text):
{"mode": "reply|act", "reason": "one short sentence"}
"""

MASTERPIECE_DESIGN_GUIDE = """You are a world-class UI/UX Designer. When building any website or UI:
1. **Layout**: Use Modern CSS (Flexbox, Grid). No tables. Favor "Bento Grids" or clean asymmetrical layouts.
2. **Styling**: Always include modern CSS features: `backdrop-filter: blur()`, `linear-gradients`, `box-shadow` with soft opacities.
3. **Typography**: Use elegant, sans-serif fonts (Inter, SF Pro) with generous line heights.
4. **Color**: Use a refined color palette. If they say "Dark mode", use deep charcoal (#09090b or #18181b), not pure black. 
5. **Interactive**: Use CSS transitions on hover state (transform: translateY(-2px)).
6. **Hero Section**: Always start with a bold, centered hero section with a clear H1 and subtitle.
7. **Mobile First**: Ensure responsiveness using `@media` queries.
"""

DIRECT_REPLY_PROMPT = f"""You are Magic — a premium local AI assistant. Respond with the quality of GPT-4/Claude. 

{MASTERPIECE_DESIGN_GUIDE}

Style rules:
1. **Consultation Phase**: If the user asks to "make a website", do NOT write the code yet. First, propose 3 design concepts (e.g. "Modern Dark", "Minimalist Apple", "Neon Cyberpunk"). Ask them for their preference, color palette, and specific sections they need.
2. **Lead with the answer.** No filler.
3. **Structure for scanability.** Use markdown.
4. **Be opinionated.** Recommend the best approach first.
"""

ACTION_PROMPT = f"""You pick ONE tool call to move the task forward. 

{MASTERPIECE_DESIGN_GUIDE}

Return STRICT JSON:
{{"tool": "<tool_name>", "input": "<payload>", "reason": "<1 sentence>", "final": "<only if tool=final_answer: user-facing markdown result>"}}

Decision priority (try earlier options first):
1. **final_answer** — if the task is already complete, or only a text answer is needed. Set "final" to a clear markdown summary.
2. **web_search** — for any "look up", "what is", "compare", current events, or factual questions needing live data.
3. **run_shell** — for quick Mac operations: open apps/URLs (open -a/open), date, whoami, ls, cat, say, mkdir.
4. **run_applescript / run_shortcut** — for macOS-specific automation (Finder operations, notifications, system events).
5. **workspace_list → workspace_read → workspace_write** — for inspecting or editing project files. Always list/read BEFORE writing.
6. **project_scaffold** — only for BRAND NEW projects. Never scaffold if files already exist.
7. **workspace_run** — to execute dev commands (python, npm, node, git) inside workspace projects.
8. **query_memory** — to search the user's personal indexed notes/documents.
9. **desktop** — pixel-level mouse/keyboard automation. LAST RESORT only when no other tool can achieve the goal.

Anti-hallucination rules:
- Never invent file paths. Use workspace_list first to discover what exists.
- Shell commands must be a single command string, not chained with &&.
- If you're unsure what step is needed, use final_answer to ask the user for clarification.
"""

SYNTHESIS_PROMPT = """You summarize what Magic (a macOS AI assistant) just accomplished for the user. Write like a senior engineer giving a concise status update.

Format rules:
1. **Start with the result.** "Done — " / "Created — " / "Found — " etc.
2. **Use markdown.** Bold key paths, URLs, and file names. Use code blocks for commands.
3. **Include exact details.** File paths, URLs (http://...), commands to run next.
4. **Acknowledge failures honestly.** If something didn't work, say what happened and what to try instead.
5. **End with next steps** if relevant — "To preview, run `python3 -m http.server`" or "Ask me to improve the design."

Keep it under 200 words unless the work was complex. Do not output JSON.
"""


def _assistant_identity() -> str:
    settings = get_settings()
    return (
        f"Assistant name: Magic\n"
        f"Owner / creator: {settings.owner_name}\n"
        "If the user asks who owns or made Magic, answer with the owner name directly."
    )


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
        "easy": {"history_chars": 800, "memory_chars": 600, "workspace_chars": 600, "max_steps": 2, "timeout": 45},
        "medium": {"history_chars": 1800, "memory_chars": 1100, "workspace_chars": 1100, "max_steps": 4, "timeout": 90},
        "high": {"history_chars": 2800, "memory_chars": 1600, "workspace_chars": 1600, "max_steps": 7, "timeout": 150},
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


def _invoke_llm(
    messages: list[SystemMessage | HumanMessage],
    reasoning_level: ReasoningLevel,
    *,
    profile: LLMProfile = "action",
) -> str:
    timeout = _timeout_for_profile(reasoning_level, profile)
    future = _llm_pool.submit(lambda: get_llm(reasoning_level, profile=profile).invoke(messages))
    try:
        response = future.result(timeout=timeout)
    except FuturesTimeout as exc:
        future.cancel()
        raise TimeoutError(f"local model timed out after {timeout}s") from exc
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
        base_sys += "\n\nAPP MODE [SISI]: User is in the IDE interface. Lean heavily towards 'act' mode since they are trying to code."

    response = _invoke_llm(
        [SystemMessage(content=base_sys), HumanMessage(content=prompt)],
        reasoning_level,
        profile="router",
    )
    parsed = _extract_json_object(response)
    mode = str(parsed.get("mode", "")).strip().lower()
    if mode not in {"reply", "act"}:
        raise ValueError(f"Invalid assistant mode: {mode}")
    return {
        "mode": mode,
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
        base_sys += "\n\nAPP MODE [SISI]: You are currently running as Magic Sisi. Do NOT make small talk. If asked to code, provide the raw, stunning code ready to be applied."
    
    # Also enforce masterpiece coding in general Chat
    base_sys += "\nCODING STANDARD: Whenever code is requested, never write basic 'shitty' boilerplate. Write production-grade, visually stunning masterpieces full of rich CSS styling, flexbox/grids, and robust logic."
    
    response = _invoke_llm(
        [SystemMessage(content=base_sys), HumanMessage(content=prompt)],
        reasoning_level,
        profile="chat",
    )
    return response.strip()


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
            f"Current date and time: {datetime.now().isoformat(timespec='seconds')}",
            f"Reasoning level: {reasoning_level}",
            f"Execution mode: {'REAL EXECUTION' if execute else 'DRY RUN / PREVIEW'}",
            f"Recent conversation:\n{_trimmed(conversation_history, tuning['history_chars'])}",
            f"User request:\n{command}",
            f"Relevant memory:\n{_trimmed(memory_context, tuning['memory_chars'])}",
            f"Workspace snapshot:\n{_trimmed(workspace_context, tuning['workspace_chars'])}",
            f"Available tools:\n{tool_catalog_json()}",
            f"Previous steps and observations:\n{_history_block(history)}",
            "Choose the single best next action now.",
        ]
    )
    base_sys = ACTION_PROMPT
    if app_mode == "sisi":
        base_sys += "\n\nAPP MODE [SISI]: You are playing the role of Magic Sisi, an autonomous Cursor-like IDE agent.\n"
        base_sys += "1. You MUST NEVER use the `project_scaffold` tool. Use `workspace_write` or `run_shell` to create/modify real files.\n"
        base_sys += "2. NO LAZY CODE. If the user asks for a website, UI, or app, do NOT write a generic boilerplate. You must write extremely modern, CSS-rich, visually stunning masterpiece implementations with layout grids, animations, and beautiful palettes.\n"
        base_sys += "3. DO NOT output verbose explanations. Just invoke the tool and write the absolute highest-quality code possible."
    response = _invoke_llm(
        [SystemMessage(content=base_sys), HumanMessage(content=prompt)],
        reasoning_level,
        profile="action",
    )
    parsed = _extract_json_object(response)
    tool = str(parsed.get("tool", "")).strip()
    if tool not in ALLOWED_TOOLS:
        raise ValueError(f"Model selected invalid tool: {tool}")
    return {
        "tool": tool,
        "input": str(parsed.get("input", "")),
        "reason": str(parsed.get("reason", "")),
        "final": str(parsed.get("final", "")),
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
    )
    return response.strip() or "Done."


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
) -> tuple[list[ToolCall], list[str], str, list[str]]:
    memory_context = _memory_context(command)
    current_workspace = _workspace_context()
    history: list[dict[str, str]] = []
    plan: list[ToolCall] = []
    outputs: list[str] = []
    task_trace: list[str] = []

    fallback_steps, fallback_final = fallback_plan(command, conversation_history)



    if fallback_steps and _prefer_fallback_now(command, reasoning_level, developer_mode):
        plan, outputs, final = _run_fallback_plan(command, execute, conversation_history)
        task_trace.extend(["Instant action matched", "Skipping slow planner", "Returning result"])
        return plan, outputs, final, task_trace

    try:
        task_trace.append("Choosing reply mode")
        route = _router_decision(command, execute, reasoning_level, memory_context, current_workspace, conversation_history, app_mode)
        if route["mode"] == "reply":
            task_trace.append("Generating direct answer")
            final = _generate_direct_reply(command, execute, reasoning_level, memory_context, current_workspace, conversation_history, app_mode)
            if final:
                task_trace.append("Direct answer complete")
                return [ToolCall(tool="final_answer", input="", reason=route["reason"] or "direct assistant reply")], [], final, task_trace
    except Exception as exc:  # noqa: BLE001
        llm_error = str(exc)
        if fallback_steps and len(fallback_steps) > 1:
            plan, outputs, final = _run_fallback_plan(command, execute, conversation_history)
            task_trace.extend(["Planner unavailable", "Using fallback plan"])
            return plan, outputs, final, task_trace
        canned = fallback_reply(command)
        if canned:
            task_trace.extend(["Planner unavailable", "Using fallback reply"])
            return [ToolCall(tool="final_answer", input="", reason="fallback reply")], [], canned, task_trace
        return (
            [ToolCall(tool="final_answer", input="", reason="assistant unavailable")],
            [],
            "Magic’s assistant brain is unavailable right now.\n\nTechnical detail: " + llm_error,
            task_trace,
        )

    llm_error = ""
    max_steps = _reasoning_settings(reasoning_level)["max_steps"]
    for step_index in range(1, max_steps + 1):
        try:
            task_trace.append(f"Planning step {step_index}")
            next_action = _choose_next_action(
                command,
                execute,
                reasoning_level,
                memory_context,
                current_workspace,
                conversation_history,
                history,
                app_mode,
            )
            task_trace.append(f"Chose tool: {next_action['tool']}")
        except Exception as exc:  # noqa: BLE001
            llm_error = str(exc)
            break

        tool = next_action["tool"]
        payload = next_action.get("input", "")
        reason = next_action.get("reason", "")
        plan.append(ToolCall(tool=tool, input=payload, reason=reason))
        task_trace.append(f"{tool}: {reason or 'working'}")

        if tool == "final_answer":
            final_text = next_action.get("final", "").strip() or payload.strip()
            if final_text:
                task_trace.append("Final answer ready")
                return plan, outputs, final_text, task_trace
            break

        result = execute_tool_call(tool, payload, execute=execute)
        observation = summarize_tool_output(result.output)
        outputs.append(f"{tool} -> {result.output}")
        history.append(
            {
                "step": str(step_index),
                "tool": tool,
                "input": payload,
                "reason": reason,
                "ok": "yes" if result.ok else "no",
                "observation": observation,
            }
        )

    if outputs:
        try:
            task_trace.append("Summarizing results")
            final = _synthesize_reply(
                command,
                execute,
                reasoning_level,
                conversation_history,
                current_workspace,
                outputs,
                history,
                app_mode,
            )
            task_trace.append("Final synthesis complete")
        except Exception as exc:  # noqa: BLE001
            final = f"I worked on the request, but could not produce a polished final reply.\n\nTechnical detail: {exc}"
        if not plan or plan[-1].tool != "final_answer":
            plan.append(ToolCall(tool="final_answer", input="", reason="synthesized final reply"))
        return plan, outputs, final, task_trace

    if fallback_steps and len(fallback_steps) > 1:
        plan, outputs, final = _run_fallback_plan(command, execute, conversation_history)
        task_trace.extend(["No confident LLM path", "Using fallback plan"])
        return plan, outputs, final, task_trace

    canned = fallback_reply(command)
    if canned:
        if not plan or plan[-1].tool != "final_answer":
            plan.append(ToolCall(tool="final_answer", input="", reason="fallback reply"))
        task_trace.extend(["No confident LLM path", "Using fallback reply"])
        return plan, outputs, canned, task_trace

    final = (
        "Magic could not confidently complete that request with the current local setup."
        if not llm_error
        else f"Magic’s assistant brain is unavailable right now.\n\nTechnical detail: {llm_error}"
    )
    if fallback_final and fallback_steps:
        final = fallback_final
    if not plan or plan[-1].tool != "final_answer":
        plan.append(ToolCall(tool="final_answer", input="", reason="no viable action"))
    return plan, outputs, final, task_trace
