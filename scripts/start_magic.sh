#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source ".venv/bin/activate"
fi
export PYTHONPATH="$DIR:${PYTHONPATH:-}"
exec python -m uvicorn app.main:app --host 127.0.0.1 --port "${MAGIC_PORT:-8787}"
