#!/usr/bin/env python3
"""API do agente Warframe para a rede local (PC de jogo, n8n/Telegram).
Rodar:  .venv/bin/uvicorn api:app --host 0.0.0.0 --port 8765
Auth:   header  X-API-Key: <chave>   (chave em cache/api_key.txt, criada no 1º start; ou WF_API_KEY)

POST /ask          {"pergunta": "...", "modo": "texto"|"voz", "sessao": "id-opcional", "inventario": {...}}
                   -> {"resposta", "lista_completa", "fontes", ...}       (ideal para n8n / Telegram)
POST /ask/stream   mesmo corpo -> NDJSON: {"tipo":"token","texto":"..."} ... {"tipo":"fim", ...resposta completa}
GET  /health       (sem chave)
"""
import os, json, secrets, threading, queue, time, collections
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from wfagent.agent import Agent
from wfagent import config

KEY_FILE = os.path.join(config.CACHE, "api_key.txt")
API_KEY = os.environ.get("WF_API_KEY")
if not API_KEY:
    os.makedirs(config.CACHE, exist_ok=True)
    if not os.path.exists(KEY_FILE):
        open(KEY_FILE, "w").write(secrets.token_urlsafe(24))
    API_KEY = open(KEY_FILE).read().strip()

app = FastAPI(title="Warframe Agent")
ag = Agent()
LOCK = threading.Lock()                       # o Ollama atende uma geração por vez: fila simples
SESSOES = collections.defaultdict(list)       # histórico curto por sessão (ex.: chat do Telegram)

class Pergunta(BaseModel):
    pergunta: str
    modo: str = "texto"
    sessao: str | None = None
    inventario: dict | None = None

def check(key_header, key_query):
    if (key_header or key_query) != API_KEY:
        raise HTTPException(401, "chave inválida (header X-API-Key)")

def _hist(p):
    return SESSOES[p.sessao][-6:] if p.sessao else None

def _save(p, r):
    if p.sessao:
        SESSOES[p.sessao] += [{"role": "user", "content": p.pergunta}, {"role": "assistant", "content": r["resposta"][:1500]}]
        SESSOES[p.sessao] = SESSOES[p.sessao][-12:]

@app.get("/health")
def health():
    return {"ok": True, "chunks": len(ag.ix.chunks), "modelos": {"resposta": ag.answer_model, "embedding": ag.ix.embed_model}}

@app.post("/ask")
def ask(p: Pergunta, x_api_key: str | None = Header(None), key: str | None = Query(None)):
    check(x_api_key, key)
    with LOCK:
        r = ag.ask(p.pergunta, inventario=p.inventario, history=_hist(p), modo=p.modo)
    _save(p, r)
    return r

@app.post("/ask/stream")
def ask_stream(p: Pergunta, x_api_key: str | None = Header(None), key: str | None = Query(None)):
    check(x_api_key, key)
    q = queue.Queue()
    def work():
        try:
            with LOCK:
                r = ag.ask(p.pergunta, inventario=p.inventario, history=_hist(p), modo=p.modo,
                           on_token=lambda t: q.put({"tipo": "token", "texto": t}))
            _save(p, r)
            q.put({"tipo": "fim", **r})
        except Exception as e:
            q.put({"tipo": "erro", "erro": str(e)})
        q.put(None)
    threading.Thread(target=work, daemon=True).start()
    def gen():
        while (ev := q.get()) is not None:
            yield json.dumps(ev, ensure_ascii=False) + "\n"
    return StreamingResponse(gen(), media_type="application/x-ndjson")

@app.get("/buscar")
def buscar(q: str, x_api_key: str | None = Header(None), key: str | None = Query(None)):
    check(x_api_key, key)
    s = ag.search(q)
    return {"rota": s["rota"], "entidades": s["entidades"],
            "trechos": [{"nota": ag.ix.chunks[i].path, "secao": ag.ix.chunks[i].head} for i in s["hits"]]}

@app.get("/vocabulario")
def vocabulario(x_api_key: str | None = Header(None), key: str | None = Query(None)):
    """Nomes do jogo para o 'initial_prompt' do Whisper (melhora a transcrição de nomes como Rhino, Cetus, Orokin)."""
    check(x_api_key, key)
    items = ag.ents.items
    wf = sorted({e["title"] for e in items.values() if e.get("tipo") == "warframe" and "Prime" not in str(e["title"]) and "Umbra" not in str(e["title"])})
    base = ["Warframe", "Tenno", "Orokin", "Grineer", "Corpus", "Infested", "Sentient", "Lotus", "Ordis", "Cetus", "Fortuna",
            "Deimos", "Necralisk", "Zariman", "Duviri", "Höllvania", "Steel Path", "Helminth", "Riven", "Arcane", "Forma",
            "Orokin Cell", "Argon Crystal", "Cryotic", "Neurodes", "Kuva Lich", "Archon Shard", "Incarnon", "Void", "Relíquia", "Prime", "build"]
    return {"vocabulario": ", ".join(base + wf)}
