#!/bin/bash
# Navigate to project root
cd "$(dirname "$0")/.." || exit

echo "🧹 1. Cleaning up background processes and old desktop files..."
bash scripts/cleanup.sh

echo "🎨 2. Generating new premium Magic icon..."
# Ensure we use the virtual environment for PIL
source .venv/bin/activate 2>/dev/null || true
python3 scripts/generate_magic_assets.py

echo " 3. Ensuring Desktop App dependencies are ready..."
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if command -v npm >/dev/null 2>&1; then
    cd desktop-app && npm install && cd ..
else
    echo "⚠️  npm not found. You might need to install Node.js (brew install node)"
fi

echo "🔨 4. Compiling a native Magic Mac App on your Desktop..."
if [ -f "./scripts/install_desktop_shortcut.sh" ]; then
    bash ./scripts/install_desktop_shortcut.sh
else
    # Fallback to standard Terminal launcher just in case
    echo '#!/bin/bash' > ~/Desktop/Magic-Desktop.command
    echo 'cd "'$(pwd)'" && python3 start_magic.py' >> ~/Desktop/Magic-Desktop.command
    chmod +x ~/Desktop/Magic-Desktop.command
fi

echo "✨ All done! Go to your Desktop and double-click the new Magic icon."