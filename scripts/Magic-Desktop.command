#!/bin/bash
# Double-click launcher: opens the Magic Electron desktop app.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/desktop-app"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
if ! command -v npm >/dev/null 2>&1; then
  osascript -e 'display dialog "Install Node.js first (e.g. brew install node) then try again." buttons {"OK"} default button 1'
  exit 1
fi
if [[ ! -d node_modules ]]; then
  npm install
fi
exec npm start
