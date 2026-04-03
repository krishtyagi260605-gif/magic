#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

build_app() {
  local app_name=$1
  local script_name=$2
  local target="${HOME}/Desktop/${app_name}.app"
  local exec_name="$(echo "$app_name" | tr ' ' '_')"

  rm -rf "$target"
  mkdir -p "$target/Contents/MacOS"

  cat << 'EX' > "$target/Contents/MacOS/$exec_name"
#!/bin/bash
ROOT="REPLACE_ROOT"
SCRIPT="REPLACE_SCRIPT"
APP_NAME="REPLACE_APP_NAME"

# Ensure common paths are available even in GUI environment
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"
export PYTHONPATH="$ROOT"

cd "$ROOT"
if [[ -f "$ROOT/.venv/bin/python3" ]]; then
  PY="$ROOT/.venv/bin/python3"
else
  PY="python3"
fi

exec arch -arm64 "$PY" "$ROOT/$SCRIPT" > "${HOME}/Desktop/${APP_NAME}_log.txt" 2>&1
EX
  sed -i '' "s|REPLACE_ROOT|$ROOT|g" "$target/Contents/MacOS/$exec_name"
  sed -i '' "s|REPLACE_SCRIPT|$script_name|g" "$target/Contents/MacOS/$exec_name"
  sed -i '' "s|REPLACE_APP_NAME|$app_name|g" "$target/Contents/MacOS/$exec_name"
  chmod +x "$target/Contents/MacOS/$exec_name"

  mkdir -p "$target/Contents/Resources"
  if [[ -f "$ROOT/Magic.icns" ]]; then
    cp "$ROOT/Magic.icns" "$target/Contents/Resources/AppIcon.icns"
  fi

  # Add PkgInfo (Essential for identifying as an application)
  echo "APPL????" > "$target/Contents/PkgInfo"

  cat << EX > "$target/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>$exec_name</string>
    <key>CFBundleIdentifier</key>
    <string>com.magic.$(echo "$exec_name" | tr '[:upper:]' '[:lower:]')</string>
    <key>CFBundleName</key>
    <string>$app_name</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon.icns</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>LSUIElement</key>
    <false/>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSSupportsAutomaticGraphicsSwitching</key>
    <true/>
</dict>
</plist>
EX
  
  # Remove macOS quarantine attributes that may block starting
  xattr -cr "$target" 2>/dev/null || true
}

build_app "Magic Chat" "start_magic.py"
build_app "Magic Sisi" "start_sisi.py"

echo "Apps built on Desktop (from $ROOT)."
