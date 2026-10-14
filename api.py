#!/usr/bin/env python3
"""API local.  Uso: .venv/bin/uvicorn api:app --port 8765
POST /ask {"pergunta": "...", "inventario": {...}?, "historico": [...]?}  |  GET /buscar?q=...  |  GET /health"""
from fastapi import FastAPI
from pydantic import BaseModel
from wfagent.agent import Agent
from wfagent import config

app = FastAPI(title="Warframe Agent")
ag = Agent()

class Pergunta(BaseModel):
    pergunta: str
    inventario: dict | None = None
    historico: list | None = None

@app.get("/health")
def health():
    return {"ok": True, "chunks": len(ag.ix.chunks), "modelos": {"resposta": ag.answer_model,
            "roteador": config.MODEL_ROUTER, "embedding": ag.ix.embed_model}}

@app.post("/ask")
def ask(p: Pergunta):
    return ag.ask(p.pergunta, inventario=p.inventario, history=p.historico)

@app.get("/buscar")
def buscar(q: str):
    s = ag.search(q)
    return {"rota": s["rota"], "entidades": s["entidades"],
            "trechos": [{"nota": ag.ix.chunks[i].path, "secao": ag.ix.chunks[i].head} for i in s["hits"]]}
