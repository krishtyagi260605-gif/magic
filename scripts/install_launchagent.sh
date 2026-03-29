#!/usr/bin/env bash
set -euo pipefail
# Installs Magic as a LaunchAgent (login daemon) on macOS.
# Usage: ./scripts/install_launchagent.sh

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
START_SH="$ROOT/scripts/start_magic.sh"
PLIST_SRC="$ROOT/scripts/com.user.magic.plist.template"
DEST="$HOME/Library/LaunchAgents/com.user.magic.plist"
LOG_DIR="$HOME/Library/Logs"

chmod +x "$START_SH" || true
mkdir -p "$LOG_DIR"

sed \
  -e "s|REPLACE_WITH_PATH_TO_START_MAGIC_SH|$START_SH|g" \
  -e "s|REPLACE_WITH_MAGIC_PROJECT_DIR|$ROOT|g" \
  -e "s|REPLACE_WITH_HOME|$HOME|g" \
  "$PLIST_SRC" > "$DEST"

echo "Wrote $DEST"
launchctl bootout "gui/$(id -u)" "$DEST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
launchctl enable "gui/$(id -u)/com.user.magic"
echo "Magic scheduled. Logs: $LOG_DIR/magic.log"
echo "Check: curl -s http://127.0.0.1:8787/health"
