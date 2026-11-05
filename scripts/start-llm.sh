#!/usr/bin/env bash
# Start Qwen2.5-7B-Instruct (Q4_K_M) with llama.cpp on macOS/Linux, storing the model on the drive.
#   macOS:  brew install llama.cpp      Linux: see https://github.com/ggml-org/llama.cpp
# Usage: scripts/start-llm.sh [extra llama-server args]     LOW_MEMORY=1 scripts/start-llm.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export LLAMA_CACHE="$ROOT/models"
mkdir -p "$LLAMA_CACHE"
SERVER="$(command -v llama-server || true)"
[ -z "$SERVER" ] && [ -x "$ROOT/bin/llama-server" ] && SERVER="$ROOT/bin/llama-server"
if [ -z "$SERVER" ]; then echo "llama-server not found. Install llama.cpp (macOS: brew install llama.cpp)."; exit 1; fi
CTX="${CTX:-0}"; [ "${LOW_MEMORY:-0}" = "1" ] && [ "$CTX" = "0" ] && CTX=8192
HOST="${HOST:-0.0.0.0}"; PORT="${PORT:-8034}"
echo "llama-server -hf Qwen/Qwen2.5-7B-Instruct-GGUF:Q4_K_M --jinja -c $CTX --host $HOST --port $PORT $*"
exec "$SERVER" -hf Qwen/Qwen2.5-7B-Instruct-GGUF:Q4_K_M --jinja -c "$CTX" --host "$HOST" --port "$PORT" "$@"
