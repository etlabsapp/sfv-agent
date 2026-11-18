"""Thin client for a local Ollama server. No API keys, no hosted services."""
import json
import os
import urllib.request

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
CHAT_MODEL = os.environ.get("SFV_CHAT_MODEL", "sfv-qwen2.5-3b")
EMBED_MODEL = os.environ.get("SFV_EMBED_MODEL", "sfv-nomic-embed")

if not OLLAMA_URL.startswith(("http://127.0.0.1", "http://localhost")):
    raise SystemExit("OLLAMA_URL must point at a local Ollama server.")


def _post(path, body, timeout=600):
    req = urllib.request.Request(
        OLLAMA_URL + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def embed(texts, kind="query"):
    """nomic-embed-text expects a task prefix on every input."""
    prefix = "search_query: " if kind == "query" else "search_document: "
    out = _post("/api/embed", {"model": EMBED_MODEL, "input": [prefix + t for t in texts]})
    return out["embeddings"]


def chat(messages, tools=None):
    body = {
        "model": CHAT_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 8192},
    }
    if tools:
        body["tools"] = tools
    return _post("/api/chat", body)
