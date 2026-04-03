#!/bin/bash
# Kill any hung Magic backend or UI processes

echo "Cleaning up Magic processes..."

# Kill uvicorn (API server)
pkill -f "uvicorn app.main:app" || true

# Kill the startup scripts
pkill -f "start_magic.py" || true
pkill -f "start_sisi.py" || true

# Kill pywebview (which shows up as Python on macOS or com.apple.WebKit.WebContent)
# This is a bit more aggressive, so we use -f to match the script names
pkill -f "start_magic" || true
pkill -f "start_sisi" || true
pkill -f "Electron" || true
pkill -f "npm start" || true

echo "Removing broken Magic apps and shortcuts from the Desktop..."
rm -rf ~/Desktop/Magic.app
rm -f ~/Desktop/Magic-Desktop.command
rm -f ~/Desktop/Magic*.app

echo "Done. You can now try opening Magic again."
