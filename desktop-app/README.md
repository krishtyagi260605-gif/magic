# Magic Desktop (Electron)

A small **native window** that:

1. Waits for `http://127.0.0.1:8787/health`
2. If the API is down, starts Magic with: `python -m uvicorn app.main:app` from the parent `magic` folder (uses `.venv` if present)
3. Loads the Magic web UI (with **Speak** + **Run**)

## Requirements

- **Node.js** (LTS). Install with Homebrew: `brew install node`
- Magic Python deps already installed in the parent folder (`../.venv`, `pip install -r requirements.txt`)

## First-time setup

```bash
cd /path/to/magic/desktop-app
npm install
npm start
```

## Put a launcher on your Desktop

From the `magic` folder:

```bash
cp scripts/Magic-Desktop.command ~/Desktop/
chmod +x ~/Desktop/Magic-Desktop.command
```

Double-click **Magic-Desktop.command** on the Desktop (first run may ask to allow Terminal to run it).

## Notes

- Voice uses the **browser speech API** inside the window (Chromium). Allow the microphone when macOS prompts.
- The parent **Python API** must be able to start: keep the `magic` project path stable if you move the folder.
- To use a different port: `MAGIC_PORT=8790 npm start`
