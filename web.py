"""Minimal local web page.  Run: .venv/bin/uvicorn web:app --host 127.0.0.1 --port 8765"""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from sfv_agent.agent import run
from sfv_agent.llm import CHAT_MODEL

app = FastAPI()


class Ask(BaseModel):
    question: str


@app.post("/ask")
def ask(body: Ask):
    t = run(body.question[:500])
    return {"answer": t["answer"], "seconds": t["seconds"], "tool_calls": t["tool_calls"],
            "guardrail_events": t["guardrail_events"]}


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Skills for Vets program finder (local demo)</title>
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem;color:#1b2a3a}
textarea{width:100%;height:4.5rem;font:inherit;padding:.5rem}button{font:inherit;padding:.4rem 1rem;margin-top:.5rem}
#out{white-space:pre-wrap;background:#f4f6f9;padding:1rem;border-radius:6px;margin-top:1rem}
details{margin-top:.5rem;color:#555;font-size:14px}small{color:#666}</style></head><body>
<h1>Skills for Vets program finder</h1>
<p><small>Local demo. Runs MODEL on this computer through Ollama; nothing is sent to an outside AI service.
Answers come only from the Skills for Vets program list. Always confirm on the official page.</small></p>
<textarea id="q" placeholder="e.g. Free welding training in Texas?"></textarea><br>
<button id="go">Ask</button> <small id="st"></small>
<div id="out"></div><details><summary>What the agent did</summary><pre id="dbg"></pre></details>
<script>
const go=document.getElementById('go');
go.onclick=async()=>{const q=document.getElementById('q').value.trim();if(!q)return;
go.disabled=true;document.getElementById('st').textContent='Thinking (CPU model, usually 10 to 30 seconds)...';
try{const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});
const j=await r.json();
document.getElementById('out').innerHTML=j.answer.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))
 .replace(/\\*\\*(.+?)\\*\\*/g,'<b>$1</b>').replace(/(https?:\\/\\/[^\\s)]+)/g,'<a href="$1" target="_blank" rel="noopener">$1</a>');
document.getElementById('dbg').textContent=JSON.stringify({tool_calls:j.tool_calls,guardrail_events:j.guardrail_events},null,1);
document.getElementById('st').textContent=j.seconds+'s';}catch(e){document.getElementById('st').textContent='Error: '+e}
go.disabled=false;};
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def home():
    return PAGE.replace("MODEL", CHAT_MODEL)
