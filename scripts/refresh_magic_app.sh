#!/bin/bash
set -euo pipefail

PROJECT_ROOT="/Users/krishtyagi/Desktop/untitled folder/magic"
APP_ROOT="$PROJECT_ROOT/Magic.app"
DESKTOP_APP="/Users/krishtyagi/Desktop/Magic.app"

if [[ -L "$DESKTOP_APP" ]]; then
  LINK_TARGET="$(readlink "$DESKTOP_APP")"
  if [[ "$LINK_TARGET" == "$APP_ROOT" ]]; then
    chmod +x "$APP_ROOT/Contents/MacOS/Magic"
    touch "$APP_ROOT"
    echo "Refreshed $APP_ROOT (Desktop app is a symlink to it)"
    exit 0
  fi
fi

mkdir -p "$DESKTOP_APP/Contents/MacOS" "$DESKTOP_APP/Contents/Resources"
cp "$APP_ROOT/Contents/Info.plist" "$DESKTOP_APP/Contents/Info.plist"
cp "$APP_ROOT/Contents/MacOS/Magic" "$DESKTOP_APP/Contents/MacOS/Magic"
cp "$APP_ROOT/Contents/Resources/Magic.icns" "$DESKTOP_APP/Contents/Resources/Magic.icns"
chmod +x "$DESKTOP_APP/Contents/MacOS/Magic"
touch "$APP_ROOT" "$DESKTOP_APP"
echo "Refreshed $DESKTOP_APP"
