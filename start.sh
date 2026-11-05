#!/usr/bin/env bash
# macOS/Linux: start the LLM (if needed) and the SocialAgent web app.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
LLM_URL="$(python3 -c 'import json;print(json.load(open("config/settings.json"))["llm_url"].rstrip("/"))')"
UI_PORT="$(python3 -c 'import json;print(json.load(open("config/settings.json"))["ui_port"])')"
if ! curl -sf "$LLM_URL/health" >/dev/null 2>&1; then
  mkdir -p data
  "$ROOT/scripts/start-llm.sh" "$@" > data/llm.log 2>&1 &
  echo "Starting the LLM (log: data/llm.log). First run downloads ~4.7 GB..."
  until curl -sf "$LLM_URL/health" >/dev/null 2>&1; do sleep 3; printf "."; done; echo " ready."
fi
( sleep 1; (command -v open >/dev/null && open "http://localhost:$UI_PORT") || (command -v xdg-open >/dev/null && xdg-open "http://localhost:$UI_PORT") || true ) &
exec python3 "$ROOT/run_agent.py" serve
