from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
import threading
from typing import Any

from app.config import get_settings
from app.desktop import describe_desktop_op, parse_desktop_payload, run_desktop_op
from app.rag import query_memory as rag_query_memory
from app.search import search_web
from app.workspace import (
    describe_workspace_tree,
    read_workspace_file,
    run_workspace_command,
    scaffold_project,
    patch_workspace_file,
    workspace_root,
    write_workspace_file,
)


@dataclass
class ToolResult:
    ok: bool
    output: str
    tool: str = ""
    summary: str = ""
    artifacts: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    opened_file: str | None = None
    preview_url: str | None = None
    commands_run: list[str] = field(default_factory=list)
    run_logs: list[str] = field(default_factory=list)
    verification_results: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    requires_confirmation: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok, "output": self.output, "tool": self.tool, "summary": self.summary,
            "artifacts": self.artifacts, "files_changed": self.files_changed,
            "opened_file": self.opened_file, "preview_url": self.preview_url,
            "commands_run": self.commands_run, "run_logs": self.run_logs,
            "verification_results": self.verification_results, "sources": self.sources,
            "errors": self.errors, "requires_confirmation": self.requires_confirmation, "metadata": self.metadata
        }

def tool_ok(output: str, summary: str = "", **kwargs) -> ToolResult:
    return ToolResult(ok=True, output=output, summary=summary, **kwargs)

def tool_error(output: str, summary: str = "", **kwargs) -> ToolResult:
    return ToolResult(ok=False, output=output, summary=summary, **kwargs)

def _trigger_index() -> None:
    from app.rag import ingest_paths
    threading.Thread(target=ingest_paths, kwargs={"rebuild": False}, daemon=True).start()


def summarize_tool_output(text: str) -> str:
    limit = get_settings().agent_observation_max_chars
    clean = (text or "").strip()
    if len(clean) <= limit:
        return clean or "(empty)"
    return clean[: limit - 15].rstrip() + "\n...[truncated]"


def _blocked(message: str) -> ToolResult:
    return tool_error(f"BLOCKED: {message}", summary="Action blocked")


def _run_process(args: list[str]) -> ToolResult:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=60)
        out = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode != 0:
            return tool_error(out.strip() or f"Command failed (exit code {completed.returncode}).", summary="Command failed", commands_run=args, errors=[f"exit code {completed.returncode}"])
        return tool_ok(out.strip() or "Command completed successfully.", summary=f"Executed {' '.join(args[:2])}", commands_run=args)
    except Exception as exc:  # noqa: BLE001
        return tool_error(f"Could not execute command: {exc}", summary="Command execution error", commands_run=args, errors=[str(exc)])


def run_shortcut(shortcut_name: str, execute: bool) -> ToolResult:
    if not shortcut_name.strip():
        return _blocked("shortcut name is empty")
    if not execute:
        return tool_ok(f"DRY-RUN: shortcuts run {shortcut_name}", summary=f"Dry run shortcut: {shortcut_name}")
    return _run_process(["shortcuts", "run", shortcut_name.strip()])


def run_applescript(script: str, execute: bool) -> ToolResult:
    if not script.strip():
        return _blocked("applescript is empty")
    if not execute:
        return tool_ok(f"DRY-RUN: osascript -e {script[:80]}...", summary="Dry run AppleScript")
    return _run_process(["osascript", "-e", script])


def run_query_memory(query: str, execute: bool) -> ToolResult:
    """Semantic search over your indexed notes (read-only; always runs)."""
    _ = execute
    text, sources = rag_query_memory(query.strip() or ".")
    return tool_ok(text, summary=f"Queried memory for '{query}'", sources=sources[:8])


def run_web_search(query: str, execute: bool) -> ToolResult:
    _ = execute
    text, sources = search_web(query.strip() or ".")
    return tool_ok(text, summary=f"Web search for '{query}'", sources=sources[:8])


def run_desktop(payload: str, execute: bool) -> ToolResult:
    """Pixel-level mouse/keyboard (PyAutoGUI). Input is JSON: {\"op\":\"click\",\"x\":100,\"y\":200} etc."""
    settings = get_settings()
    if not settings.desktop_automation_enabled:
        return _blocked("Desktop automation disabled (set DESKTOP_AUTOMATION_ENABLED=true)")
    try:
        data = parse_desktop_payload(payload)
    except Exception as exc:  # noqa: BLE001
        return _blocked(f"desktop JSON: {exc}")
    if not execute:
        return tool_ok(describe_desktop_op(data), summary=f"Dry run desktop op: {data.get('op')}")
    try:
        out = run_desktop_op(data)
        return tool_ok(out, summary=f"Desktop op: {data.get('op')}")
    except Exception as exc:  # noqa: BLE001
        return tool_error(f"Desktop action failed: {exc}", summary="Desktop action failed", errors=[str(exc)])


def _parse_json_payload(payload: str) -> dict[str, object]:
    try:
        data = json.loads(payload)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid JSON payload: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("payload must be a JSON object")
    return data


def run_workspace_list(payload: str, execute: bool) -> ToolResult:
    _ = execute
    path = "."
    recursive = True
    if payload.strip():
        if payload.lstrip().startswith("{"):
            data = _parse_json_payload(payload)
            path = str(data.get("path", "."))
            recursive = bool(data.get("recursive", True))
        else:
            path = payload.strip()
    try:
        return tool_ok(describe_workspace_tree(path, recursive=recursive), summary=f"Listed workspace: {path}")
    except Exception as exc:  # noqa: BLE001
        return tool_error(f"Could not list workspace: {exc}", summary="List workspace failed", errors=[str(exc)])


def run_workspace_read(payload: str, execute: bool) -> ToolResult:
    _ = execute
    path = payload.strip()
    if payload.lstrip().startswith("{"):
        try:
            path = str(_parse_json_payload(payload).get("path", "")).strip()
        except Exception as exc:  # noqa: BLE001
            return tool_error(str(exc), summary="Read file failed")
    if not path:
        return _blocked("workspace_read requires a file path")
    try:
        return tool_ok(read_workspace_file(path), summary=f"Read file {path}", opened_file=path)
    except Exception as exc:  # noqa: BLE001
        return tool_error(f"Could not read file: {exc}", summary="Read file failed", errors=[str(exc)])


def run_workspace_write(payload: str, execute: bool) -> ToolResult:
    if not payload.strip():
        return _blocked("workspace_write requires JSON with path and content")
    try:
        data = _parse_json_payload(payload)
        path = str(data.get("path", "")).strip()
        content = str(data.get("content", ""))
        overwrite = bool(data.get("overwrite", True))
    except Exception as exc:  # noqa: BLE001
        return tool_error(str(exc), summary="Invalid write payload")
    if not path:
        return _blocked("workspace_write requires a path")
    if not execute:
        preview = content[:180].replace("\n", "\\n")
        return tool_ok(f"DRY-RUN: write {path} in {workspace_root()} with content preview: {preview}", summary=f"Dry run write: {path}")
    try:
        _trigger_index()
        return tool_ok(write_workspace_file(path, content, overwrite=overwrite), summary=f"Wrote file {path}", files_changed=[path], opened_file=path)
    except Exception as exc:  # noqa: BLE001
        return tool_error(f"Could not write file: {exc}", summary="Write file failed", errors=[str(exc)])

def run_workspace_patch(payload: str, execute: bool) -> ToolResult:
    if not payload.strip():
        return _blocked("workspace_patch requires JSON")
    try:
        data = _parse_json_payload(payload)
        path = str(data.get("path", "")).strip()
        op = str(data.get("op", "search_replace")).strip()
        search = str(data.get("search", ""))
        replace = str(data.get("replace", ""))
    except Exception as exc:  # noqa: BLE001
        return tool_error(str(exc), summary="Invalid patch payload")
    if not path or not search:
        return _blocked("workspace_patch requires path and search text")
    if not execute:
        preview = replace[:80].replace("\n", "\\n")
        return tool_ok(f"DRY-RUN (requires approval): patch {path} using {op}. Replacing `{search}` with `{preview}`", summary=f"Dry run patch: {path}")
    try:
        msg, diff_str = patch_workspace_file(path, op, search, replace)
        _trigger_index()
        return tool_ok(msg, summary=f"Patched {path}", files_changed=[path], metadata={"diff": diff_str}, opened_file=path)
    except Exception as exc:  # noqa: BLE001
        return tool_error(f"Could not patch file: {exc}", summary="Patch file failed", errors=[str(exc)])

def run_search_code(payload: str, execute: bool) -> ToolResult:
    try:
        data = _parse_json_payload(payload) if payload.strip().startswith("{") else {"query": payload}
        query = str(data.get("query", "")).strip()
        import subprocess
        cmd = ["grep", "-rnI", query, str(workspace_root())]
        res = subprocess.run(cmd, capture_output=True, text=True)
        out = res.stdout[:3000] if res.stdout else "No matches found."
        return tool_ok(out, summary=f"Searched code for '{query}'")
    except Exception as exc:
        return tool_error(f"search_code failed: {exc}", summary="Search code failed", errors=[str(exc)])

def run_project_scaffold(payload: str, execute: bool) -> ToolResult:
    if not payload.strip():
        return _blocked("project_scaffold requires JSON")
    try:
        data = _parse_json_payload(payload)
        name = str(data.get("name", "")).strip() or "magic-project"
        kind = str(data.get("kind", "website")).strip() or "website"
        prompt = str(data.get("prompt", "")).strip()
        spec = data.get("spec", {})
    except Exception as exc:  # noqa: BLE001
        return tool_error(str(exc), summary="Invalid scaffold payload")
    if kind in ("fastapi-auth", "backend"):
        if not spec or not spec.get("database") or not spec.get("auth"):
            return tool_error("I need more details. Please provide a spec with database type and authentication preference.", summary="Scaffold needs details", metadata={"missing_fields": ["database", "auth"]})
    if not execute:
        return tool_ok(f"DRY-RUN: scaffold a {kind} project named {name} inside {workspace_root()}", summary=f"Dry run scaffold: {name}")
    try:
        _trigger_index()
        return tool_ok(scaffold_project(name=name, kind=kind, prompt=prompt, spec=spec), summary=f"Scaffolded {kind} project {name}", artifacts=[name])
    except Exception as exc:  # noqa: BLE001
        return tool_error(f"Project scaffold failed: {exc}", summary="Project scaffold failed", errors=[str(exc)])


def run_workspace_run(payload: str, execute: bool) -> ToolResult:
    if not payload.strip():
        return _blocked("workspace_run requires JSON")
    try:
        data = _parse_json_payload(payload)
        command = str(data.get("command", "")).strip()
        cwd = str(data.get("cwd", ".")).strip() or "."
        detach = bool(data.get("detach", False))
    except Exception as exc:  # noqa: BLE001
        return tool_error(str(exc), summary="Invalid run payload")
    if not command:
        return _blocked("workspace_run requires a command")
    if not execute:
        return tool_ok(f"DRY-RUN: run `{command}` in workspace folder `{cwd}`", summary=f"Dry run workspace_run: {command}")
    result = run_workspace_command(command=command, cwd=cwd, detach=detach)
    return ToolResult(ok=result.ok, output=result.output, commands_run=[command], summary=f"Ran command: {command}", errors=[] if result.ok else [result.output])

def run_fetch_url(url: str, execute: bool) -> ToolResult:
    if not url.strip():
        return _blocked("url is empty")
    if not execute:
        return tool_ok(f"DRY-RUN: fetch {url}", summary=f"Dry run fetch: {url}")
    try:
        from app.search import fetch_url
        return tool_ok(fetch_url(url.strip()), summary=f"Fetched URL: {url}", sources=[url])
    except Exception as exc:
        return tool_error(f"Could not fetch URL: {exc}", summary="Fetch URL failed", errors=[str(exc)])

def run_execute_python(payload: str, execute: bool) -> ToolResult:
    if not payload.strip():
        return _blocked("code payload is empty")
    if not execute:
        return tool_ok("DRY-RUN: execute python code", summary="Dry run execute_python")
    try:
        code = _parse_json_payload(payload).get("code", "") if payload.lstrip().startswith("{") else payload
        from app.sandbox import execute_python_sandbox
        res = execute_python_sandbox(code)
        errors = [] if res["ok"] else [res["output"]]
        return ToolResult(ok=res["ok"], output=res["output"], commands_run=res.get("commands_run", []), summary="Executed Python sandbox", errors=errors)
    except Exception as exc:
        return tool_error(f"Python execution failed: {exc}", summary="Python execution failed", errors=[str(exc)])

def run_browser_action(payload: str, execute: bool) -> ToolResult:
    if not payload.strip():
        return _blocked("browser_action requires JSON")
    if not execute:
        return tool_ok(f"DRY-RUN: browser action {payload}", summary="Dry run browser action")
    try:
        data = _parse_json_payload(payload)
        action = data.get("action", "goto")
        url = data.get("url", "")
        selector = data.get("selector", "")

        if action in ("goto", "read", "search") and url:
            from urllib.request import Request, urlopen
            from html.parser import HTMLParser
            import re as _re
            import json as _json

            if action == "search" and not url.startswith("http"):
                from urllib.parse import quote as _quote
                url = f"https://html.duckduckgo.com/html/?q={_quote(url)}"

            req = Request(url, headers={"User-Agent": "Magic Browser Agent/1.0 Mozilla/5.0"})
            with urlopen(req, timeout=12.0) as response:
                html = response.read().decode("utf-8", errors="ignore")

            # Extract structured metadata
            title_match = _re.search(r"<title[^>]*>(.*?)</title>", html, _re.IGNORECASE | _re.DOTALL)
            page_title = _re.sub(r"<[^>]+>", "", title_match.group(1)).strip() if title_match else ""

            meta_desc = ""
            meta_match = _re.search(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)', html, _re.IGNORECASE)
            if meta_match:
                meta_desc = meta_match.group(1).strip()

            headings = []
            for h_match in _re.finditer(r"<(h[1-3])[^>]*>(.*?)</\1>", html, _re.IGNORECASE | _re.DOTALL):
                text = _re.sub(r"<[^>]+>", "", h_match.group(2)).strip()
                if text and len(text) < 200:
                    headings.append({"level": h_match.group(1), "text": text})
                if len(headings) >= 15:
                    break

            links = []
            for a_match in _re.finditer(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, _re.IGNORECASE | _re.DOTALL):
                href = a_match.group(1).strip()
                link_text = _re.sub(r"<[^>]+>", "", a_match.group(2)).strip()
                if href.startswith("http") and link_text and len(link_text) < 150:
                    links.append({"text": link_text[:100], "href": href[:200]})
                if len(links) >= 20:
                    break

            forms = []
            for form_match in _re.finditer(r"<form[^>]*>(.*?)</form>", html, _re.IGNORECASE | _re.DOTALL):
                inputs = _re.findall(r'<input[^>]*name=["\']([^"\']+)', form_match.group(1), _re.IGNORECASE)
                if inputs:
                    forms.append({"fields": inputs[:10]})
                if len(forms) >= 5:
                    break

            # Clean text preview
            text = _re.sub(r"<style[^>]*>.*?</style>", "", html, flags=_re.IGNORECASE | _re.DOTALL)
            text = _re.sub(r"<script[^>]*>.*?</script>", "", text, flags=_re.IGNORECASE | _re.DOTALL)
            text = _re.sub(r"<[^>]+>", " ", text)
            text_preview = " ".join(text.split())[:2000]

            result = {
                "url": url,
                "title": page_title,
                "meta_description": meta_desc,
                "headings": headings[:10],
                "links": links[:15],
                "forms": forms[:3],
                "text_preview": text_preview,
            }
            return tool_ok(_json.dumps(result, indent=2, ensure_ascii=False), summary=f"Browsed {url}", sources=[url])

        if action == "extract" and url and selector:
            from urllib.request import Request, urlopen
            import re as _re
            req = Request(url, headers={"User-Agent": "Magic Browser Agent/1.0"})
            with urlopen(req, timeout=12.0) as response:
                html = response.read().decode("utf-8", errors="ignore")
            pattern = _re.compile(selector, _re.IGNORECASE | _re.DOTALL)
            matches = pattern.findall(html)
            clean = [_re.sub(r"<[^>]+>", "", m).strip() for m in matches[:20]]
            return tool_ok(json.dumps({"matches": clean}, indent=2), summary=f"Extracted data from {url}", sources=[url])

        return tool_ok(f"Browser action '{action}' acknowledged. Advanced DOM interactions require Playwright.", summary="Browser action executed")
    except Exception as exc:
        return tool_error(f"Browser action failed: {exc}", summary="Browser action failed", errors=[str(exc)])

def run_shell(command: str, execute: bool) -> ToolResult:
    settings = get_settings()
    text = command.strip()
    if not text:
        return _blocked("shell command is empty")

    try:
        argv = shlex.split(text)
    except Exception as exc:  # noqa: BLE001
        return _blocked(f"could not parse command: {exc}")

    first = argv[0] if argv else ""
    if first not in settings.shell_allowed_commands:
        return _blocked(f"'{first}' is not in allowlist")

    # Basic path guard: deny absolute paths outside allowed root.
    allowed_root = settings.shell_allowed_root.resolve()
    for token in argv[1:]:
        if token.startswith("-"):
            continue
        candidate = Path(token).expanduser()
        if candidate.is_absolute():
            try:
                candidate.resolve().relative_to(allowed_root)
            except Exception:  # noqa: BLE001
                return _blocked(f"path outside allowed root: {candidate}")

    if not execute:
        return tool_ok(f"DRY-RUN: {text}", summary=f"Dry run shell: {first}")
    res = _run_process(argv)
    res.commands_run = [text]
    res.summary = f"Ran shell: {first}"
    return res


def send_whatsapp_messages(payload: str, execute: bool) -> ToolResult:
    if not payload.strip():
        return _blocked("whatsapp payload is empty")
    try:
        data = _parse_json_payload(payload)
        contacts = data.get("contacts", [])
        message = data.get("message", "")
    except Exception as exc:
        return tool_error(str(exc), summary="Invalid whatsapp payload")
    
    if not contacts or not message:
        return _blocked("contacts and message are required")
        
    if not execute:
        return tool_ok(f"DRY-RUN: Send '{message}' to {', '.join(contacts)} via WhatsApp.", summary="Dry run WhatsApp")
        
    import subprocess
    script_template = '''
    tell application "WhatsApp"
        activate
        delay 0.5
    end tell
    set failedContacts to {{}}
    set successCount to 0
    {contact_actions}
    if (count of failedContacts) > 0 then
        set AppleScript's text item delimiters to ", "
        set failedStr to failedContacts as string
        if successCount > 0 then
            return "Sent '{message}' to " & successCount & " contact(s). Failed to find: " & failedStr
        else
            error "Failed to find any of the contacts: " & failedStr
        end if
    else
        return "Sent '{message}' to " & successCount & " contact(s)."
    end if
    '''
    contact_actions = []
    for contact in contacts:
        safe_contact = contact.replace('\\', '\\\\').replace('"', '\\"')
        safe_message = message.replace('\\', '\\\\').replace('"', '\\"')
        actions = f'''
        set the clipboard to ""
        tell application "System Events"
            keystroke "f" using command down
            delay 0.5
            keystroke "{safe_contact}"
            delay 1.0
            keystroke return
            delay 0.5
            keystroke "a" using command down
            delay 0.2
            keystroke "c" using command down
            delay 0.2
        end tell
        delay 0.2
        set copiedText to the clipboard
        if copiedText as string is "{safe_contact}" then
            set end of failedContacts to "{safe_contact}"
        else
            tell application "System Events"
                keystroke "{safe_message}"
                delay 0.3
                keystroke return using command down
            end tell
            set successCount to successCount + 1
        end if
        '''
        contact_actions.append(actions)
        
    safe_template_msg = message.replace('\\', '\\\\').replace('"', '\\"')
    full_script = script_template.format(contact_actions="\n".join(contact_actions), message=safe_template_msg)
    try:
        res = subprocess.run(["osascript", "-e", full_script], check=True, capture_output=True, text=True)
        out_msg = res.stdout.strip()
        return tool_ok(out_msg, summary="Sent WhatsApp messages", files_changed=[])
    except subprocess.CalledProcessError as e:
        return tool_error(f"WhatsApp failed: {e.stderr.strip()}", summary="WhatsApp failed", errors=[f"AppleScript failed: {e.stderr.strip()}"])

def linkedin_auto_apply(payload: str, execute: bool) -> ToolResult:
    if not payload.strip():
        return _blocked("linkedin payload is empty")
    try:
        data = _parse_json_payload(payload)
        resume_path = data.get("resume_path", "")
        job_title = data.get("job_title", "")
        location = data.get("location", "")
        max_apps = data.get("max_applications", 5)
    except Exception as exc:
        return tool_error(str(exc), summary="Invalid linkedin payload")
        
    if not resume_path or not job_title:
        return _blocked("resume_path and job_title are required")

    if not execute:
        preview_jobs = [{"title": f"{job_title} at Tech Corp", "location": location or "Remote"}]
        return tool_ok(f"DRY-RUN (requires approval): Found jobs. Would apply to {max_apps} {job_title} jobs using {resume_path}.", summary="Dry run LinkedIn", metadata={"jobs": preview_jobs})

    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        return tool_error("Playwright not installed. Run: pip install playwright && playwright install chromium", summary="Playwright missing")

    from app.config import get_settings
    session_dir = get_settings().magic_data_dir / "linkedin_session"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                user_data_dir=str(session_dir),
                headless=False,
            )
            page = browser.new_page()
            page.goto("https://www.linkedin.com/jobs")
            try:
                page.wait_for_selector(".global-nav__me", timeout=5000)
            except PlaywrightTimeout:
                browser.close()
                return tool_error("Not logged into LinkedIn. Please log in manually once and save the session.", summary="LinkedIn Login Required")

            import time
            page.goto(f"https://www.linkedin.com/jobs/search/?keywords={job_title}&location={location}")
            time.sleep(2)
            
            jobs = page.query_selector_all('.job-card-container')[:max_apps]
            applied = 0
            for job in jobs:
                job.click()
                time.sleep(1)
                easy_apply_btn = page.query_selector('button.jobs-apply-button')
                if easy_apply_btn:
                    easy_apply_btn.click()
                    time.sleep(1)
                    file_input = page.query_selector('input[type="file"]')
                    if file_input:
                        from app.workspace import resolve_workspace_path
                        try:
                            abs_resume = resolve_workspace_path(resume_path)
                            if abs_resume.exists():
                                file_input.set_input_files(str(abs_resume))
                        except Exception:
                            pass
                    submit = page.query_selector('button[aria-label="Submit application"]')
                    if submit:
                        submit.click()
                        applied += 1
                        time.sleep(2)

            browser.close()
            return tool_ok(f"Applied to {applied} jobs.", summary="LinkedIn Auto Apply")
    except Exception as e:
        return tool_error(f"LinkedIn automation failed: {e}", summary="LinkedIn Auto Apply Failed")

_TOOL_DISPATCH: dict[str, object] = {
    "run_shortcut": lambda p, e: run_shortcut(p, execute=e),
    "run_applescript": lambda p, e: run_applescript(p, execute=e),
    "run_shell": lambda p, e: run_shell(p, execute=e),
    "web_search": lambda p, e: run_web_search(p, execute=e),
    "query_memory": lambda p, e: run_query_memory(p, execute=e),
    "desktop": lambda p, e: run_desktop(p, execute=e),
    "workspace_list": lambda p, e: run_workspace_list(p, execute=e),
    "workspace_read": lambda p, e: run_workspace_read(p, execute=e),
    "workspace_write": lambda p, e: run_workspace_write(p, execute=e),
    "workspace_patch": lambda p, e: run_workspace_patch(p, execute=e),
    "workspace_git": lambda p, e: run_workspace_git(p, execute=e),
    "workspace_archive": lambda p, e: run_workspace_archive(p, execute=e),
    "project_scaffold": lambda p, e: run_project_scaffold(p, execute=e),
    "workspace_run": lambda p, e: run_workspace_run(p, execute=e),
    "fetch_url": lambda p, e: run_fetch_url(p, execute=e),
    "execute_python": lambda p, e: run_execute_python(p, execute=e),
    "execute_python_sandbox": lambda p, e: run_execute_python(p, execute=e),
    "search_code": lambda p, e: run_search_code(p, execute=e),
    "browser_action": lambda p, e: run_browser_action(p, execute=e),
    "final_answer": lambda p, _: ToolResult(ok=True, output=p or "Done."),
    "send_whatsapp_messages": lambda p, e: send_whatsapp_messages(p, execute=e),
    "linkedin_auto_apply": lambda p, e: linkedin_auto_apply(p, execute=e),
}


def is_destructive(t: str, p: str) -> bool:
    if t in {"workspace_write", "workspace_patch", "project_scaffold", "desktop", "workspace_archive", "send_whatsapp_messages", "linkedin_auto_apply"}:
        return True
    if t == "run_shell":
        return not any(p.strip().startswith(safe) for safe in ("ls", "pwd", "whoami", "date", "cat", "find", "mdfind", "stat", "uname", "system_profiler", "df", "echo"))
    if t == "workspace_git":
        return not any(safe in p for safe in ("status", "diff", "show", "log", "branch"))
    if t == "browser_action":
        return "submit" in p or "click" in p or "fill" in p
    return False

def execute_tool_call(tool: str, payload: str, execute: bool, approval_mode: str = "auto_apply") -> ToolResult:
    handler = _TOOL_DISPATCH.get(tool)
    if handler is None:
        return _blocked(f"unknown tool: {tool}")

    actually_execute = execute
    requires_confirmation = False

    if is_destructive(tool, payload):
        if approval_mode in ("preview_only", "ask_before_apply"):
            actually_execute = False
            requires_confirmation = True

    res = handler(payload, actually_execute)
    res.tool = tool
    if not actually_execute and requires_confirmation:
        from app.trace import create_approval
        diff = res.metadata.get("diff") if "diff" in res.metadata else None
        files_affected = res.files_changed if res.files_changed else []
        appr_id = create_approval("pending", tool, payload, f"Requires confirmation for {tool}", "High", diff, files_affected)
        res.approval_id = appr_id
        if diff: res.diff = diff
        res.requires_confirmation = True
        res.output = f"ACTION PAUSED (Needs Approval). Awaiting user confirmation for {tool}."
        res.ok = True # It didn't fail, it paused
        res.summary = f"Paused for approval: {tool}"
        
    return res


from functools import lru_cache as _lru_cache


@_lru_cache(maxsize=1)
def _cached_tool_catalog() -> str:
    payload = {
        "tools": [
            {
                "name": "run_shortcut",
                "input": "Shortcut name as plain text",
                "description": "Run a macOS Shortcut by name",
            },
            {
                "name": "run_applescript",
                "input": "AppleScript code as string",
                "description": "Execute AppleScript via osascript",
            },
            {
                "name": "run_shell",
                "input": "Single shell command string (ls, cat, open, say, date, mkdir, etc.)",
                "description": "Execute an allowlisted shell command on macOS",
            },
            {
                "name": "web_search",
                "input": "Natural language web search query",
                "description": "Search the live web (DuckDuckGo + Wikipedia) for fast factual answers and sources",
            },
            {
                "name": "query_memory",
                "input": "Natural language question about your indexed files/notes",
                "description": "Search personal indexed documents using RAG (LlamaIndex)",
            },
            {
                "name": "desktop",
                "input": 'JSON object, one op. Examples: {"op":"screen"} | {"op":"click","x":400,"y":300} | {"op":"type","text":"hi"} | {"op":"hotkey","keys":["command","space"]} | {"op":"scroll","clicks":-5} | {"op":"screenshot"}',
                "description": "Full desktop robot: mouse, keyboard, scroll, drag, screenshot (needs macOS Accessibility permission)",
            },
            {
                "name": "workspace_list",
                "input": 'Relative path string or JSON like {"path":"my-site","recursive":true}',
                "description": "Inspect files inside Magic's desktop workspace",
            },
            {
                "name": "workspace_read",
                "input": 'Relative file path or JSON like {"path":"my-site/index.html"}',
                "description": "Read a text file from the Magic workspace",
            },
            {
                "name": "workspace_write",
                "input": '{"path":"my-site/index.html","content":"...","overwrite":true}',
                "description": "Create or replace a text file inside the Magic workspace",
            },
            {
                "name": "workspace_patch",
                "input": '{"path":"my-site/index.html","op":"replace_block","search":"old text","replace":"new text"}',
                "description": "Surgically edit code. Supported ops: search_replace, replace_block, insert_before, insert_after.",
            },
            {
                "name": "search_code",
                "input": '{"query":"function_name"}',
                "description": "Grep and search across the workspace for code snippets or references.",
            },
            {
                "name": "workspace_git",
                "input": '{"cwd":"portfolio-site","command":"git status"}',
                "description": "Run git commands (init, status, add, commit, branch) inside a workspace project.",
            },
            {
                "name": "workspace_archive",
                "input": '{"target":"portfolio-site"}',
                "description": "Zip and archive a project folder for export or sharing.",
            },
            {
                "name": "project_scaffold",
                "input": '{"name":"portfolio","kind":"fastapi-auth","prompt":"A blog","spec":{"database":"postgresql","auth":"yes","auth_type":"jwt"}}',
                "description": "Create a starter project on the Desktop workspace. For backend, include spec dict.",
            },
            {
                "name": "workspace_run",
                "input": '{"cwd":"portfolio-site","command":"python3 -m http.server 4173","detach":true}',
                "description": "Run a development command inside the Magic workspace",
            },
            {
                "name": "fetch_url",
                "input": "https://example.com",
                "description": "Scrape the text content of a webpage.",
            },
            {
                "name": "execute_python_sandbox",
                "input": '{"code":"print(\'hello\')" }',
                "description": "Run python code in a temporary sandboxed file.",
            },
            {
                "name": "browser_action",
                "input": '{"action":"goto","url":"https://example.com"} | {"action":"search","url":"python web scraping"} | {"action":"extract","url":"https://...","selector":"<h2>(.*?)</h2>"}',
                "description": "Browse a webpage and extract structured data (title, headings, links, forms, meta). Actions: goto/read (structured page data), search (DuckDuckGo), extract (regex selector).",
            },
            {
                "name": "final_answer",
                "input": "Human readable final response",
                "description": "Finish the plan — give the user a clear answer. Use this when the task is done or you only need to reply with text.",
            },
            {
                "name": "send_whatsapp_messages",
                "input": '{"contacts": ["John", "Sarah"], "message": "Hi"}',
                "description": "Send a message to multiple WhatsApp contacts using AppleScript.",
            },
            {
                "name": "linkedin_auto_apply",
                "input": '{"resume_path": "resume.pdf", "job_title": "Software Engineer", "location": "New York", "max_applications": 5}',
                "description": "Automates LinkedIn job applications using browser automation.",
            },
        ]
    }
    return json.dumps(payload, indent=2)


def tool_catalog_json() -> str:
    return _cached_tool_catalog()
