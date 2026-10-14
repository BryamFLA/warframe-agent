#!/usr/bin/env python3
"""Gera respostas completas para um conjunto de perguntas e salva em Markdown para comparar modelos.
Uso: .venv/bin/python eval/eval_respostas.py --modelo qwen3.5:9b [--saida eval/respostas_qwen.md]"""
import os, sys, time, json, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wfagent.agent import Agent

PERGUNTAS = [
    "Onde posso conseguir o warframe Excalibur?",
    "O que posso farmar em CETUS?",
    "Me liste tudo o que posso fazer em FORTUNA",
    "Qual a história dos Corpus?",
    "Crie um passo a passo de como criar a arma Alternox",
    "Como posso conseguir CRIÓTICO?",
    "Me conte um resumo da história do game",
    "O que dá pra fazer e farmar na Terra, como missões, itens e tudo o mais que tiver?",
    "Dicas de como terminar a jornada The Second Dream",
    "Qual a melhor build para o Rhino?",
    "Me liste todos os itens que eu posso adquirir em Cetus",
    "o que é o caminho de aço e quando devo começar?",
    "como consigo archon shard?",
    "qual frame é bom pra tankar no começo?",
    "Quem é o Ballas?",
]
ap = argparse.ArgumentParser(); ap.add_argument("--modelo"); ap.add_argument("--saida"); ap.add_argument("--n", type=int, default=len(PERGUNTAS)); ap.add_argument("--modo", default="texto")
a = ap.parse_args()
ag = Agent(answer_model=a.modelo)
out = a.saida or f"eval/respostas_{ag.answer_model.replace(':', '_')}_{a.modo}.md"
primeiras = []
L = [f"# Respostas — {ag.answer_model} (embedding {ag.ix.embed_model})\n"]; tempos = []
for q in PERGUNTAS[:a.n]:
    t = time.time(); marks = {}; buf = []
    def tok(x):
        marks.setdefault("primeiro", time.time() - t); buf.append(x)
        if "frase" not in marks and any(ch in "".join(buf) for ch in ".!?") and len("".join(buf)) > 25:
            marks["frase"] = time.time() - t
    r = ag.ask(q, modo=a.modo, on_token=tok); dt = time.time() - t; tempos.append(dt)
    primeiras.append(marks.get("frase", dt))
    L += [f"## {q}", "", f"*rota: {r['rota']['intencao']} · entidades: {', '.join(r['entidades']) or '—'} · total {dt:.1f}s · 1ª frase {marks.get('frase', dt):.1f}s · tokens {r['tempo'].get('tokens_entrada')}→{r['tempo'].get('tokens_saida')}*", "",
          r["resposta"], "", "Fontes: " + "; ".join(f"[{f['n']}] {f['nota']} — {f['secao'][:40]}" for f in r["fontes"]), ""]
    print(f"{dt:5.1f}s (1ª frase {marks.get('frase', dt):4.1f}s)  {q}", flush=True)
    open(out, "w", encoding="utf-8").write("\n".join(L))
L.append(f"\n**Tempo médio: {sum(tempos)/len(tempos):.1f}s · máx {max(tempos):.1f}s · 1ª frase média {sum(primeiras)/len(primeiras):.1f}s**")
open(out, "w", encoding="utf-8").write("\n".join(L)); print("salvo em", out)
