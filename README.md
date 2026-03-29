# Magic (Mac Automation Agent)

Magic is a **local-first** agent you run on your Mac: **FastAPI + Swagger**, **LangGraph** planning/execution, **LlamaIndex** memory over your files, **voice** (Whisper), **full desktop control** (mouse, keyboard, scroll, screenshots via **PyAutoGUI**), plus Shortcuts, AppleScript, and a restricted shell.

Project folder: keep this directory anywhere (for example `~/Desktop/magic`).

## Stack

| Piece | Role |
|--------|------|
| FastAPI | HTTP API + OpenAPI/Swagger at `/docs` |
| LangGraph | Retrieve → plan → execute |
| LlamaIndex | Embeddings + vector index + query engine |
| LangChain | Chat models (Ollama or OpenAI) |
| PyAutoGUI | Clicks, typing, hotkeys, scroll, drag, screenshots |
| launchd | Optional background daemon (see `scripts/`) |
| Electron (`desktop-app/`) | Optional **desktop window** + auto-start API (see below) |

### Quality & speed (like GPT / Claude)

- **Best answers:** set `LLM_PROVIDER=openai`, add `OPENAI_API_KEY`, and pick a strong `OPENAI_MODEL` (e.g. `gpt-4.1` or `gpt-4.1-mini` for cost/latency tradeoffs).
- **Local only:** keep Ollama; use a capable model (`ollama pull qwen2.5:14b` or `llama3.1` — larger = usually smarter, slower). `OLLAMA_KEEP_ALIVE` keeps the model warm between turns.
- **API requests:** use `reasoning_level`: `easy` = fastest, `medium` = default balanced, `high` / `extra_high` = deeper multi-step (slower). Magic uses a **fast router** for reply-vs-act classification and heavier settings for chat / tool / synthesis steps.

## Desktop app (window on your Mac)

### One-time: install tools

- **Python:** `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- **Node.js:** `brew install node` (if you do not have `npm`)
- **Electron:** `cd desktop-app && npm install`

### Magic icon on your Desktop

After dependencies are installed, put the app on your Desktop:

```bash
./scripts/install_desktop_shortcut.sh
```

This creates **`~/Desktop/Magic.app`** pointing at this project’s `Magic.app`. **Double-click Magic** to open the window: type a command, use **Speak**, toggle **Really do it** when you want real actions.

If you **move the Magic project folder**, run `install_desktop_shortcut.sh` again (or remove the old Desktop shortcut and symlink it again).

**Alternative (Terminal launcher):** `scripts/Magic-Desktop.command` — `chmod +x` and double-click.

See `desktop-app/README.md` for details.

### Sanity check

```bash
./scripts/verify_magic.sh
```

If the API is offline, start Ollama (or set `LLM_PROVIDER=openai` + `OPENAI_API_KEY` in `.env`), then run `uvicorn` or open the **Magic** desktop app.

## Quickstart

```bash
cd magic
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env — at minimum set LLM and embedding providers
```

**Ollama (recommended for chat + embeddings)**

```bash
ollama pull llama3.1
ollama pull nomic-embed-text
```

```bash
export LLM_PROVIDER=ollama
export EMBEDDING_PROVIDER=ollama
# Use --reload-dir app so the watcher ignores .venv (otherwise reload loops forever)
uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8787
```

Or run `./scripts/dev.sh` from the `magic` folder (same flags).

- **Web UI (browser):** `http://127.0.0.1:8787/` — type or **Speak**, quick prompts, summary + JSON.
- **Desktop app:** `desktop-app` + `npm start` (or `Magic-Desktop.command` on the Desktop).
- **Swagger (full API):** `http://127.0.0.1:8787/docs`
- **ReDoc:** `http://127.0.0.1:8787/redoc`

## Main endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/v1/command` | Natural language task (dry-run unless `execute: true`) |
| POST | `/v1/index/ingest` | Build or update the LlamaIndex from `MAGIC_INDEX_PATHS` or a given `path` |
| GET | `/v1/memory/query?q=...` | Ask questions over indexed files |
| POST | `/v1/transcribe` | Audio → text (needs `OPENAI_API_KEY`) |
| POST | `/v1/voice/command` | Transcribe + run same pipeline as `/v1/command` |
| GET | `/v1/desktop/screen` | Screen width/height (logical points) for planning clicks |
| GET | `/v1/desktop/position` | Current mouse position |
| GET | `/health` | Liveness |

Default note folder (if `MAGIC_INDEX_PATHS` is empty): `~/Documents/MagicNotes` (create a `.md` or `.txt` file there, then call ingest).

## Full desktop robot (mouse & keyboard)

The agent can use tool **`desktop`** with a **JSON** payload (one operation per step). Examples:

- `{"op":"screen"}` — logical resolution (same info as `GET /v1/desktop/screen`)
- `{"op":"click","x":400,"y":300}` — move and click
- `{"op":"type","text":"hello"}` — typing (Unicode uses clipboard + Cmd+V)
- `{"op":"hotkey","keys":["command","space"]}` — hotkeys (`command`, `shift`, `alt`, `ctrl`, …)
- `{"op":"scroll","clicks":-5}` — vertical scroll (negative often = scroll down)
- `{"op":"drag","from_x":10,"from_y":10,"to_x":200,"to_y":200}`
- `{"op":"screenshot","path":"~/Desktop/magic.png"}` — optional path

**macOS permissions (required):**

1. **System Settings → Privacy & Security → Accessibility** — enable the app that runs Python (`Terminal`, `iTerm2`, **Cursor**, or `Python` if you use the interpreter directly). If you use a venv, it is still the **parent app** (e.g. Cursor) that must be allowed.
2. If screenshots fail or are blank: **Screen Recording** for the same app.

**Dry-run:** With `execute: false`, the plan only **describes** desktop ops; set `execute: true` for real mouse/keyboard.

**Limits:** `DESKTOP_MAX_OPS_PER_PLAN` (default 120) caps how many `desktop` steps run per request. Set `DESKTOP_AUTOMATION_ENABLED=false` to disable desktop tools entirely.

**Reality check:** Pixel-based automation breaks when resolution, scaling, or window layout changes. For stable workflows, combine **`desktop`** with **Shortcuts** / **AppleScript** where possible. True “see the screen and decide” (vision) is not in this stack yet; that would be a separate upgrade (screenshot + multimodal model loop).

## Personal memory (LlamaIndex)

1. Put notes under your index paths (or use the default `MagicNotes` folder).
2. Call `POST /v1/index/ingest` with `{ "rebuild": true }` the first time, or `{"path": "/path/to/folder"}`.
3. Chat with `POST /v1/command` — the graph **retrieves** from your index before planning. The agent can also call the **`query_memory`** tool for follow-ups.

Index storage: `MAGIC_DATA_DIR` (default `~/.magic`), with `vector_index` under it. If the home directory cannot be written (e.g. restricted environment), Magic falls back to `.magic_data/` inside this project.

## Voice

- Set `OPENAI_API_KEY` in `.env` (Whisper API).
- `POST /v1/transcribe` — multipart file field name `file`.
- `POST /v1/voice/command` — form fields: `file` (audio) and optional `execute` (`true`/`false`).

## Run in the background (launchd)

```bash
chmod +x scripts/start_magic.sh scripts/install_launchagent.sh
./scripts/install_launchagent.sh
```

Logs: `~/Library/Logs/magic.log` and `magic.err.log`. Unload: `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.user.magic.plist`

## Safety

- Default **dry-run** for automation; set `execute: true` when you mean real clicks/keys/shell.
- With `execute: true`, **`desktop` can control the whole GUI** (same as any macro tool). Do not leave it exposed on a network.
- Shell tool is **allowlisted** and **path-restricted** (see `app/config.py`).
- RAG and memory search are **read-only**.
- **Failsafe:** with `DESKTOP_FAILSAFE=true` (default), slamming the mouse to the **top-left corner** aborts PyAutoGUI (emergency stop).

## Troubleshooting: server “never stops” restarting with `--reload`

If you run `uvicorn ... --reload` from the project root, the file watcher can include **`.venv`**. Imports (numpy, LlamaIndex, etc.) touch files under `site-packages`, WatchFiles sees “changes,” and uvicorn restarts in a loop.

**Fix:** only watch your app code:

```bash
uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8787
```

Or use `./scripts/dev.sh`. For a stable process with no auto-reload, omit `--reload`.

## Copy to Desktop

```bash
cp -R /path/to/magic ~/Desktop/magic
```

Then use `~/Desktop/magic` as the working directory for venv and `uvicorn`.
