#!/usr/bin/env python3
"""Mede velocidade de leitura (prefill) e escrita (decode) de um modelo com um contexto real do vault.
Uso: .venv/bin/python eval/bench_modelo.py gemma4:12b gemma4:12b-mlx"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wfagent.agent import Agent, SYSTEM
from wfagent import llm
ag = Agent()
q = "Qual a melhor build para o Rhino?"
ctx, _ = ag.context(ag.search(q)["hits"])
msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"CONTEXTO:\n{ctx}\n\nPERGUNTA: {q}"}]
for m in sys.argv[1:]:
    llm.chat(m, [{"role": "user", "content": "oi"}], num_predict=5)   # aquece/carrega
    t = time.time(); txt, raw = llm.chat(m, msgs, num_predict=400); dt = time.time() - t
    pe, pc, ee, ec = raw.get("prompt_eval_duration", 0) / 1e9, raw.get("prompt_eval_count", 0), raw.get("eval_duration", 0) / 1e9, raw.get("eval_count", 0)
    print(f"{m:22s} total {dt:5.1f}s | leitura {pc} tok em {pe:4.1f}s = {pc/max(pe,1e-9):5.0f} tok/s | escrita {ec} tok em {ee:4.1f}s = {ec/max(ee,1e-9):4.1f} tok/s", flush=True)
    os.system(f"ollama stop {m} >/dev/null 2>&1")
