#!/usr/bin/env bash
# One-time setup. Downloads two open model files from Hugging Face (about 2.2 GB) and registers
# them with a local Ollama. No accounts, API keys or hosted AI services.
set -euo pipefail
cd "$(dirname "$0")"
command -v ollama >/dev/null || { echo "Install Ollama first: https://ollama.com/download"; exit 1; }
mkdir -p models
[ -f models/qwen2.5-3b-instruct-q4_k_m.gguf ] || curl -fL -o models/qwen2.5-3b-instruct-q4_k_m.gguf \
  https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf
[ -f models/nomic-embed-text-v1.5.Q8_0.gguf ] || curl -fL -o models/nomic-embed-text-v1.5.Q8_0.gguf \
  https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/nomic-embed-text-v1.5.Q8_0.gguf
printf 'FROM ./qwen2.5-3b-instruct-q4_k_m.gguf\nPARAMETER temperature 0.1\nPARAMETER num_ctx 8192\n' > models/Modelfile.qwen
printf 'FROM ./nomic-embed-text-v1.5.Q8_0.gguf\n' > models/Modelfile.nomic
(cd models && ollama create sfv-qwen2.5-3b -f Modelfile.qwen && ollama create sfv-nomic-embed -f Modelfile.nomic)
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
# Snapshot and index ship with the repo. Rebuild the snapshot only when SFV_SOURCE
# points at a programs.json file; rebuild the index if it is missing.
if [ -n "${SFV_SOURCE:-}" ] || [ ! -f data/index.npz ]; then
  .venv/bin/python -m sfv_agent.data
else
  echo "Using existing data/programs.snapshot.json and data/index.npz"
fi
