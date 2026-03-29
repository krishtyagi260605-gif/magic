#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

build_app() {
  local app_name=$1
  local script_name=$2
  local target="${HOME}/Desktop/${app_name}.app"

  rm -rf "$target"
  mkdir -p "$target/Contents/MacOS"

  cat << 'EX' > "$target/Contents/MacOS/$app_name"
#!/bin/bash
ROOT="REPLACE_ROOT"
SCRIPT="REPLACE_SCRIPT"
APP_NAME="REPLACE_APP_NAME"
cd "$ROOT"
if [[ -f "$ROOT/.venv/bin/python3" ]]; then
  PY="$ROOT/.venv/bin/python3"
else
  PY="python3"
fi
export PYTHONPATH="$ROOT"
exec "$PY" "$ROOT/$SCRIPT" > "${HOME}/Desktop/${APP_NAME}_log.txt" 2>&1
EX
  sed -i '' "s|REPLACE_ROOT|$ROOT|g" "$target/Contents/MacOS/$app_name"
  sed -i '' "s|REPLACE_SCRIPT|$script_name|g" "$target/Contents/MacOS/$app_name"
  sed -i '' "s|REPLACE_APP_NAME|$app_name|g" "$target/Contents/MacOS/$app_name"
  chmod +x "$target/Contents/MacOS/$app_name"

  mkdir -p "$target/Contents/Resources"
  if [[ -f "$ROOT/Magic.icns" ]]; then
    cp "$ROOT/Magic.icns" "$target/Contents/Resources/AppIcon.icns"
  fi

  cat << EX > "$target/Contents/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>$app_name</string>
    <key>CFBundleIdentifier</key>
    <string>com.magic.$(echo "$app_name" | tr ' ' '_' | tr '[:upper:]' '[:lower:]')</string>
    <key>CFBundleName</key>
    <string>$app_name</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon.icns</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
EX
}

build_app "Magic Chat" "start_magic.py"
build_app "Magic Sisi" "start_sisi.py"

echo "Apps built on Desktop (from $ROOT)."
