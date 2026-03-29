#!/usr/bin/env bash
# Puts Magic on your Desktop as Magic.app (symlink to this repo's bundle).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$HOME/Desktop/Magic.app"
rm -f "$TARGET"
ln -sf "$ROOT/Magic.app" "$TARGET"
echo "Desktop shortcut: $TARGET -> $ROOT/Magic.app"
echo "Double-click Magic on your Desktop to open."
