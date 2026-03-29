#!/usr/bin/env bash
# Quick sanity check: venv, deps, API health (start server separately or use desktop app).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -f .venv/bin/activate ]]; then
  echo "Missing .venv — run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi
# shellcheck source=/dev/null
source .venv/bin/activate
python -c "import fastapi, uvicorn; print('Python deps OK')"
if [[ -d desktop-app/node_modules/electron ]]; then
  echo "Electron OK"
else
  echo "Optional: cd desktop-app && npm install"
fi
if curl -sf "http://127.0.0.1:8787/health" >/dev/null; then
  echo "API is up at http://127.0.0.1:8787"
  curl -s "http://127.0.0.1:8787/health" | python -m json.tool
else
  echo "API not running. Start: source .venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 8787"
  exit 0
fi
