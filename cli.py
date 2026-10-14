#!/usr/bin/env python3
"""Chat no terminal com o agente Warframe.  Uso: .venv/bin/python cli.py [--debug] [--inventario arquivo.json]"""
import sys, json, argparse
from wfagent.agent import Agent

ap = argparse.ArgumentParser()
ap.add_argument("--debug", action="store_true", help="mostra rota, entidades e fontes")
ap.add_argument("--inventario", help="JSON/YAML com o inventário do jogador")
ap.add_argument("pergunta", nargs="*", help="pergunta única (sem abrir o chat)")
a = ap.parse_args()
inv = None
if a.inventario:
    import yaml
    inv = yaml.safe_load(open(a.inventario, encoding="utf-8"))
print("Carregando índice...", flush=True)
ag = Agent()
hist = []

def run(q):
    print()
    r = ag.ask(q, inventario=inv, history=hist, on_token=lambda x: print(x, end="", flush=True))
    print()
    print("\nFontes: " + "; ".join(f"[{f['n']}] {f['nota']}" for f in r["fontes"]))
    if a.debug:
        print(f"\n[debug] rota={r['rota']} entidades={r['entidades']} tempo={r['tempo']}")
    hist.extend([{"role": "user", "content": q}, {"role": "assistant", "content": r["resposta"]}])

if a.pergunta:
    run(" ".join(a.pergunta)); sys.exit()
print("Pergunte sobre Warframe (Ctrl+C para sair).")
while True:
    try:
        q = input("\nVocê> ").strip()
    except (KeyboardInterrupt, EOFError):
        break
    if q:
        run(q)
