#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed. Download it from https://ollama.com/download"
  exit 1
fi

echo "Pulling best free local assistant model..."
ollama pull qwen2.5:7b

echo "Pulling local embedding model..."
ollama pull nomic-embed-text

echo
echo "Local AI setup complete."
echo "Magic is configured to use:"
echo "  OLLAMA_MODEL=qwen2.5:7b"
echo "  OLLAMA_EMBEDDING_MODEL=nomic-embed-text"
