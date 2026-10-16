#!/usr/bin/env python3
"""Testa o modo profundo (classificação + plano + etapas validadas) e salva as respostas em Markdown.
Uso: .venv/bin/python eval/teste_profundo.py ["pergunta" ...] [--saida eval/respostas_profundo.md] [--so-classificar]"""
import os, sys, time, json, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wfagent.agent import Agent
from wfagent.profundo import Pensador

PADRAO = ["qual a história do jogo?", "onde consigo o Rhino?", "quem é o Ballas?",
          "me conta a história completa dos Grineer", "me faz um guia de progressão do iniciante até o endgame",
          "como funciona o Helminth?", "qual a melhor build pro Rhino?", "o que é o caminho de aço?",
          "qual a diferença entre Grineer, Corpus e Infested e de onde cada um veio?", "o que aconteceu no The New War?"]
ap = argparse.ArgumentParser(); ap.add_argument("perguntas", nargs="*"); ap.add_argument("--saida")
ap.add_argument("--so-classificar", action="store_true")
a = ap.parse_args()
ag = Agent()
qs = a.perguntas or PADRAO
if a.so_classificar:
    pz = Pensador(ag)
    for q in qs:
        t = time.time(); s = ag.search(q)
        print(f"{pz.classificar(q, s)}  {time.time() - t:.1f}s  <- {q}", flush=True)
    sys.exit()
L = [f"# Modo profundo — {ag.answer_model}\n"]
for q in qs:
    t = time.time()
    r = ag.ask(q, on_event=lambda e: print(f"  [{time.time() - t:5.0f}s] {e['texto']}", flush=True))
    dt = time.time() - t
    pf = r["rota"].get("profundidade", {})
    print(f"\n=== {q}  ({dt:.0f}s, {pf.get('tipo')} via {pf.get('via')}: {pf.get('motivo')})\n{r['resposta']}\n", flush=True)
    L += [f"## {q}", "", f"*{pf.get('tipo')} ({pf.get('via')}: {pf.get('motivo')}) · total {dt:.0f}s · {len(r['resposta'].split())} palavras*", "",
          r["resposta"], ""]
    if r.get("profundo"):
        L += ["<details><summary>Plano e verificações</summary>", "", "```json",
              json.dumps({"plano": r["profundo"]["plano"], "passos": r["profundo"]["passos"], "verificacoes": r["profundo"]["verificacoes"]}, ensure_ascii=False, indent=1),
              "```", "</details>", ""]
    open(a.saida or "eval/respostas_profundo.md", "w").write("\n".join(L))
