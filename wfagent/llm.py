"""Cliente mínimo do Ollama (sem dependências além da stdlib)."""
import json, urllib.request
from . import config

def _post(path, payload, timeout=600):
    req = urllib.request.Request(config.OLLAMA + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def chat(model, messages, json_schema=None, temperature=0.2, num_ctx=None, think=False, num_predict=None):
    p = {"model": model, "messages": messages, "stream": False, "think": think,
         "keep_alive": config.KEEP_ALIVE,
         "options": {"temperature": temperature, "num_ctx": num_ctx or config.NUM_CTX}}
    if num_predict:
        p["options"]["num_predict"] = num_predict
    if json_schema is not None:
        p["format"] = json_schema
    out = _post("/api/chat", p)
    return out["message"]["content"], out

def embed(texts, model=None, batch=32):
    model = model or config.MODEL_EMBED
    vecs = []
    for i in range(0, len(texts), batch):
        out = _post("/api/embed", {"model": model, "input": texts[i:i + batch],
                                   "keep_alive": config.KEEP_ALIVE, "truncate": True})
        vecs.extend(out["embeddings"])
    return vecs

def chat_stream(model, messages, on_token, temperature=0.3, num_ctx=None, num_predict=None, think=False):
    """Como chat(), mas chama on_token(texto) a cada pedaço gerado. Retorna (texto, último_evento)."""
    p = {"model": model, "messages": messages, "stream": True, "think": think, "keep_alive": config.KEEP_ALIVE,
         "options": {"temperature": temperature, "num_ctx": num_ctx or config.NUM_CTX}}
    if num_predict:
        p["options"]["num_predict"] = num_predict
    req = urllib.request.Request(config.OLLAMA + "/api/chat", data=json.dumps(p).encode(),
                                 headers={"Content-Type": "application/json"})
    out, last = [], {}
    with urllib.request.urlopen(req, timeout=900) as r:
        for line in r:
            if not line.strip():
                continue
            ev = json.loads(line); last = ev
            piece = ev.get("message", {}).get("content", "")
            if piece:
                out.append(piece); on_token(piece)
            if ev.get("done"):
                break
    return "".join(out), last
