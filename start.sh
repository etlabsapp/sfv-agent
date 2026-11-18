#!/usr/bin/env bash
# Start local Ollama (cloud features off) and the web page at http://127.0.0.1:8765
cd "$(dirname "$0")"
export OLLAMA_NO_CLOUD=1
pgrep -x ollama >/dev/null || (nohup ollama serve > ollama.log 2>&1 &) ; sleep 2
exec .venv/bin/uvicorn web:app --host 127.0.0.1 --port 8765
