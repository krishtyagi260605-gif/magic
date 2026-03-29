from __future__ import annotations

import re
import shlex
from pathlib import Path

from app.config import get_settings


def _final_step(reason: str = "finish response") -> dict[str, str]:
    return {"tool": "final_answer", "input": "", "reason": reason}


def _home_path(*parts: str) -> Path:
    return Path.home().joinpath(*parts)


def _quote_path(path: Path) -> str:
    return shlex.quote(str(path))


def _folder_location(command: str) -> Path | None:
    lower = command.lower()
    if "desktop" in lower:
        return _home_path("Desktop")
    if "documents" in lower or "document" in lower:
        return _home_path("Documents")
    if "downloads" in lower or "download" in lower:
        return _home_path("Downloads")
    if "home" in lower or "folder" in lower:
        return Path.home()
    return None


def _extract_folder_name(command: str) -> str | None:
    patterns = [
        r"(?:folder|directory)\s+(?:named|called)\s+['\"]?([^'\"\n]+?)['\"]?(?:\s+(?:on|in)\s+.+)?$",
        r"(?:create|make)\s+(?:a\s+)?(?:new\s+)?(?:folder|directory)\s+['\"]?([^'\"\n]+?)['\"]?(?:\s+(?:on|in)\s+.+)?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, command, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip().strip(".")
            candidate = re.split(r"\s+(?:and|nd|then|thn|that|with|for)\b", candidate, maxsplit=1, flags=re.IGNORECASE)[0]
            return candidate.strip().strip(".")
    return None


def _extract_spoken_text(command: str) -> str | None:
    match = re.search(r"^(?:say|speak)\s+(.+)$", command.strip(), re.IGNORECASE)
    if match:
        return match.group(1).strip().strip("\"'")
    return None


def _extract_shortcut(command: str) -> str | None:
    match = re.search(r"(?:run|open|start)\s+(?:the\s+)?shortcut\s+['\"]?([^'\"\n]+?)['\"]?$", command.strip(), re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _extract_url(command: str) -> str | None:
    url_match = re.search(r"(https?://[^\s]+)", command, re.IGNORECASE)
    if url_match:
        return url_match.group(1)

    site_match = re.search(r"open\s+([a-z0-9-]+)\s+(?:website|site)$", command.strip(), re.IGNORECASE)
    if site_match:
        return f"https://{site_match.group(1)}.com"
    return None


def _extract_app(command: str) -> str | None:
    text = command.strip().rstrip(".!?")
    patterns = [
        r"^(?:open|launch|start)\s+(?:the\s+)?(.+?)(?:\s+app(?:lication)?)?$",
        r"^(?:open up)\s+(?:the\s+)?(.+?)(?:\s+app(?:lication)?)?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            app_name = match.group(1).strip()
            if app_name and app_name.lower() not in {"website", "site", "url"}:
                return app_name
    return None


def _recent_user_commands(conversation_history: str) -> list[str]:
    commands: list[str] = []
    for line in (conversation_history or "").splitlines():
        if line.lower().startswith("user:"):
            text = line.split(":", 1)[1].strip()
            if text:
                commands.append(text)
    return commands


def _extract_project_name(command: str) -> str | None:
    patterns = [
        r"(?:called|named)\s+['\"]?([^'\"\n]+?)['\"]?(?:\s+(?:on|in|for)\s+.+)?$",
        r"(?:website|site|app|project)\s+(?:called|named)\s+['\"]?([^'\"\n]+?)['\"]?",
        r"create\s+(?:a\s+)?(?:website|site|app|project)\s+['\"]?([^'\"\n]+?)['\"]?(?:\s+(?:for|about)\s+.+)?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, command, re.IGNORECASE)
        if match:
            return match.group(1).strip().strip(".")
    return None


def _extract_folder_target(command: str) -> str | None:
    match = re.search(
        r"folder\s+(?:on\s+desktop\s+)?named\s+['\"]?([^'\"\n]+?)['\"]?(?=\s+(?:and|nd|then|thn|that|with|for)\b|\s*$)",
        command,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().strip(".")
    return None


def _is_coding_request(lower: str) -> bool:
    coding_terms = (
        "code",
        "website",
        "web app",
        "landing page",
        "portfolio",
        "presentation",
        "slides",
        "slide deck",
        "ppt",
        "document",
        "report",
        "image",
        "poster",
        "logo",
        "app",
        "project",
        "react",
        "html",
        "css",
        "javascript",
        "python script",
        "host it",
        "build ",
    )
    return any(term in lower for term in coding_terms)


def _is_build_request(lower: str) -> bool:
    return any(
        term in lower
        for term in (
            "build ",
            "create ",
            "make ",
            "generate ",
            "scaffold ",
            "code ",
            "write code",
            "make me ",
            "create me ",
        )
    )


def _is_search_request(lower: str) -> bool:
    prefixes = (
        "search ",
        "look up ",
        "lookup ",
        "google ",
        "what is ",
        "who is ",
        "when is ",
        "where is ",
        "how to ",
        "tell me about ",
    )
    return lower.startswith(prefixes) or "difference between" in lower or lower.startswith("compare ") or lower.startswith("explain ")


def _should_host_request(lower: str) -> bool:
    return any(term in lower for term in ("host", "run it", "start it", "serve it", "open it locally", "preview it", "launch it"))


def _project_kind_for_request(lower: str) -> str:
    if "fast api" in lower or "fastapi" in lower or ("login" in lower and "user" in lower):
        return "fastapi-auth"
    if any(term in lower for term in ("presentation", "slides", "slide deck", "ppt", "pitch deck")):
        return "slides"
    if any(term in lower for term in ("document", "report", "notes", "summary doc", "writeup")):
        return "document"
    if any(term in lower for term in ("image", "poster", "graphic", "logo", "banner", "illustration")):
        return "image"
    return "website"


def _default_project_name(lower: str, kind: str) -> str:
    if kind == "fastapi-auth":
        return "magic-fastapi-app"
    if kind == "slides":
        return "magic-slide-deck"
    if kind == "document":
        return "magic-document"
    if kind == "image":
        return "magic-artwork"
    return "magic-project"


def fallback_reply(command: str) -> str | None:
    lower = command.strip().lower()
    settings = get_settings()

    if any(greet in lower for greet in ("hello", "hi", "hey", "what can you do", "who are you")):
        return (
            "I’m Magic, your local Mac assistant. Right now I can chat a bit, open apps and sites, create folders, "
            "read and write project files in your Desktop Magic workspace, scaffold starter websites, "
            "speak text aloud, query indexed notes, and automate desktop actions when needed. "
            f"For stronger reasoning, I need the local model `{settings.ollama_model}` available in Ollama."
        )

    if any(phrase in lower for phrase in ("who made you", "who owns you", "who is your owner", "owner details", "who created you")):
        return f"Magic is owned and created by {settings.owner_name}."

    if "explain what you can do" in lower or "what can you do right now" in lower:
        return (
            "Right now I can handle direct local tasks like opening apps, creating folders, scaffolding starter projects in your Desktop Magic workspace, "
            "speaking text, and searching your indexed notes. I also have a multi-step assistant loop ready for deeper reasoning, "
            "but it depends on the local Ollama model being available."
        )

    if lower.startswith("why are you") or lower.startswith("what are you doing"):
        return (
            "I can explain what I’m doing, but for deeper reasoning-heavy replies I still depend on the local Ollama model. "
            "Once that model is ready, I’ll be much closer to a full chat assistant."
        )

    if _is_build_request(lower) and _is_coding_request(lower):
        return (
            "I can already scaffold and edit local projects on your Desktop, and once the Ollama model is ready I can reason through bigger coding tasks "
            "much more like a real build assistant."
        )

    return None


def fallback_plan(command: str, conversation_history: str = "") -> tuple[list[dict[str, str]] | None, str | None]:
    text = command.strip()
    lower = text.lower()
    settings = get_settings()

    if not text:
        return [_final_step("empty command")], "Type a command first."

    if lower in {"again", "do that again", "repeat that", "same again", "try that again"}:
        prior_commands = _recent_user_commands(conversation_history)
        while prior_commands:
            previous = prior_commands.pop()
            if previous.strip().lower() != lower:
                return fallback_plan(previous, "")

    if any(phrase in lower for phrase in ("what time", "current time", "tell me the time", "what's the time")):
        return (
            [
                {"tool": "run_shell", "input": "date", "reason": "show current local date and time"},
                _final_step(),
            ],
            "I can show the current time directly even without the model.",
        )

    if lower in {"who am i", "whoami"}:
        return (
            [
                {"tool": "run_shell", "input": "whoami", "reason": "show current macOS user"},
                _final_step(),
            ],
            "I can identify the current macOS user directly.",
        )

    if lower in {"where am i", "pwd", "current folder"}:
        return (
            [
                {"tool": "run_shell", "input": "pwd", "reason": "show current working directory"},
                _final_step(),
            ],
            "I can show the current working directory directly.",
        )

    if any(phrase in lower for phrase in ("battery", "power status", "charge level")):
        return (
            [
                {"tool": "run_shell", "input": "pmset -g batt", "reason": "show battery status"},
                _final_step(),
            ],
            "Checking battery status.",
        )

    if any(phrase in lower for phrase in ("my ip", "ip address", "what is my ip")):
        return (
            [
                {"tool": "run_shell", "input": "ipconfig getifaddr en0", "reason": "show local WiFi IP address"},
                _final_step(),
            ],
            "Getting your local IP address.",
        )

    if any(phrase in lower for phrase in ("disk space", "storage", "free space", "disk usage")):
        return (
            [
                {"tool": "run_shell", "input": "df -h /", "reason": "show disk usage for main volume"},
                _final_step(),
            ],
            "Checking disk space.",
        )

    if any(phrase in lower for phrase in ("system info", "about this mac", "hardware info")):
        return (
            [
                {"tool": "run_shell", "input": "system_profiler SPHardwareDataType SPSoftwareDataType", "reason": "show system information"},
                _final_step(),
            ],
            "Fetching system information.",
        )

    if any(phrase in lower for phrase in ("take a screenshot", "screenshot", "capture screen")):
        return (
            [
                {"tool": "run_shell", "input": "screencapture -x ~/Desktop/screenshot.png", "reason": "take a screenshot to Desktop"},
                _final_step(),
            ],
            "Taking a screenshot and saving to Desktop.",
        )

    if any(phrase in lower for phrase in ("lock screen", "lock my mac", "lock the screen")):
        return (
            [
                {"tool": "run_shell", "input": "pmset displaysleepnow", "reason": "lock/sleep the display"},
                _final_step(),
            ],
            "Locking the screen now.",
        )

    if any(phrase in lower for phrase in ("spotlight", "search for file", "find file")):
        query = lower.replace("spotlight", "").replace("search for file", "").replace("find file", "").strip() or "magic"
        return (
            [
                {"tool": "run_shell", "input": f"mdfind -name {shlex.quote(query)}", "reason": "search with Spotlight"},
                _final_step(),
            ],
            "Searching with Spotlight.",
        )

    if any(phrase in lower for phrase in ("who made you", "who owns you", "who is your owner", "owner details", "who created you")):
        return (
            [_final_step("owner details")],
            f"Magic is owned and created by {settings.owner_name}.",
        )

    spoken_text = _extract_spoken_text(text)
    if spoken_text:
        return (
            [
                {"tool": "run_shell", "input": f"say {shlex.quote(spoken_text)}", "reason": "speak text aloud"},
                _final_step(),
            ],
            "I can speak short messages without needing the model.",
        )

    shortcut_name = _extract_shortcut(text)
    if shortcut_name:
        return (
            [
                {"tool": "run_shortcut", "input": shortcut_name, "reason": "run the named macOS Shortcut"},
                _final_step(),
            ],
            "I can run that Shortcut directly.",
        )

    if _is_search_request(lower):
        return (
            [
                {"tool": "web_search", "input": text, "reason": "search the live web for a fast factual answer"},
                _final_step(),
            ],
            "I can search the web directly for that.",
        )

    if "fast api" in lower or "fastapi" in lower:
        project_name = _extract_folder_target(text) or _extract_project_name(text) or "magic-fastapi-app"
        fastapi_prompt = text.replace('"', '\\"')
        steps = [
            {
                "tool": "project_scaffold",
                "input": (
                    '{"name": "%s", "kind": "fastapi-auth", "prompt": "%s"}'
                    % (project_name.replace('"', ""), fastapi_prompt)
                ),
                "reason": "create a FastAPI starter with create-user and login flow in the Desktop workspace",
            },
        ]
        if _should_host_request(lower):
            steps.append(
                {
                    "tool": "workspace_run",
                    "input": (
                        '{"cwd":"__LAST_PROJECT__","command":"python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8010","detach":true}'
                    ),
                    "reason": "start the FastAPI app locally in the background",
                }
            )
        steps.append(
            {
                "tool": "final_answer",
                "input": "",
                "reason": "fast FastAPI build shortcut complete",
            }
        )
        final_text = "I can create that FastAPI auth starter directly in your Desktop workspace without waiting for a long planning cycle."
        if _should_host_request(lower):
            final_text += " I will also start it locally."
        return (steps, final_text)

    if any(word in lower for word in ("create", "make")) and any(word in lower for word in ("folder", "directory")):
        folder_name = _extract_folder_name(text)
        folder_base = _folder_location(text)
        if folder_name and folder_base:
            target = folder_base / folder_name
            return (
                [
                    {"tool": "run_shell", "input": f"mkdir {_quote_path(target)}", "reason": "create the requested folder"},
                    _final_step(),
                ],
                f"I can create that folder directly under {folder_base}.",
            )

    url = _extract_url(text)
    if url:
        return (
            [
                {"tool": "run_shell", "input": f"open {shlex.quote(url)}", "reason": "open the requested website"},
                _final_step(),
            ],
            "I can open websites directly.",
        )

    app_name = _extract_app(text)
    if app_name:
        return (
            [
                {"tool": "run_shell", "input": f"open -a {shlex.quote(app_name)}", "reason": "open the requested macOS app"},
                _final_step(),
            ],
            f"I can open {app_name} directly.",
        )

    if "memory" in lower or "notes" in lower or "my files" in lower:
        return (
            [
                {"tool": "query_memory", "input": text, "reason": "search indexed files and notes"},
                _final_step(),
            ],
            "I’ll answer from your indexed memory if it’s available.",
        )

    if _is_build_request(lower) and _is_coding_request(lower):
        project_kind = _project_kind_for_request(lower)
        project_name = _extract_project_name(text) or _default_project_name(lower, project_kind)
        steps = [
            {
                "tool": "project_scaffold",
                "input": (
                    '{"name": "%s", "kind": "%s", "prompt": "%s"}'
                    % (
                        project_name.replace('"', ""),
                        project_kind,
                        text.replace('"', '\\"'),
                    )
                ),
                "reason": "create a starter project in the Desktop Magic workspace",
            },
        ]
        if _should_host_request(lower):
            run_payload = (
                '{"cwd":"__LAST_PROJECT__","command":"python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8010","detach":true}'
                if project_kind == "fastapi-auth"
                else '{"cwd":"__LAST_PROJECT__","command":"python3 -m http.server 4173","detach":true}'
            )
            steps.append(
                {
                    "tool": "workspace_run",
                    "input": run_payload,
                    "reason": "start the new project locally in the background",
                }
            )
        steps.append(_final_step())
        final_text = "I can at least scaffold a starter local project right away, even before the full model is ready."
        if _should_host_request(lower):
            final_text += " I will also start it locally."
        return (steps, final_text)

    provider = settings.llm_provider.lower()
    if provider == "ollama":
        model_hint = "The local AI engine is unavailable for deeper planning right now, so Magic can still do fast direct actions and shortcuts but not full deep automation."
    else:
        model_hint = "The API model is unavailable right now, so Magic can still do fast direct actions and shortcuts but not full deep automation."

    return (
        [_final_step("llm needed")],
        "Magic could not use its deep planner for that request right now. " + model_hint,
    )
