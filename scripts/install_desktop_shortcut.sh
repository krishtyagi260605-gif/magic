#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$HOME/Desktop/Magic.app"

echo "Removing old shortcut..."
rm -rf "$TARGET"

# 1. Create a bulletproof launcher script for the premium Electron app
cat << 'EOF' > "$ROOT/scripts/launch_ui.sh"
#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")/../desktop-app"
if [ ! -d "node_modules" ]; then
    npm install
fi
npm start
EOF
chmod +x "$ROOT/scripts/launch_ui.sh"

# 2. Compile a 100% native macOS Applet that runs the script silently
osacompile -e "do shell script \"'$ROOT/scripts/launch_ui.sh' >/dev/null 2>&1 &\"" -o "$TARGET"

# 3. Convert our iconset and apply it natively
iconutil -c icns "$ROOT/Magic.app/Contents/Resources/Magic.iconset" -o "$TARGET/Contents/Resources/applet.icns" || true
iconutil -c icns "$ROOT/Magic.app/Contents/Resources/Magic.iconset" -o "$ROOT/Magic.app/Contents/Resources/Magic.icns" || true

echo "Native Desktop App compiled at $TARGET"
echo "Double-click Magic on your Desktop to open."
