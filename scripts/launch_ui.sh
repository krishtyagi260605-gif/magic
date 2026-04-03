#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$(dirname "$0")/../desktop-app"
if [ ! -d "node_modules" ]; then
    npm install
fi
npm start
