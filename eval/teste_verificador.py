#!/usr/bin/env python3
"""Confere se o verificador do modo profundo pega erros plantados (e não reprova texto correto).
Uso: .venv/bin/python eval/teste_verificador.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wfagent.agent import Agent
from wfagent import profundo as P

ag = Agent()
ids = ag.ix.by_path["lore/cronologia/o_colapso.md"]
ctx, _ = ag.context(ids, budget=P.BUDGET_ETAPA)
CERTO = ("Na festa da vitória contra os Sentients, os Orokin reuniram os Tenno para homenageá-los. Os Tenno, que nunca perdoaram "
         "a execução de Margulis, massacraram a liderança Orokin sob a ordem de Natah. Depois disso, Natah escondeu Lua e o "
         "Reservoir no Void, colocou as Warframes em criosono e passou a se chamar Lotus.")
CASOS = {
    "correto": CERTO,
    "nome trocado": CERTO.replace("Natah", "Ballas"),
    "fato inventado": CERTO + " O massacre aconteceu em Marte, comandado pelo Captain Vor, que liderava os Tenno.",
    "contradição": CERTO.replace("massacraram a liderança Orokin", "protegeram a liderança Orokin"),
}
for nome, texto in CASOS.items():
    v = P._json(ag.answer_model, P.VERIFICAR.format(ctx=ctx, titulo="O Colapso", objetivo="explicar o massacre e o fim do Império", outras="A Era Orokin; A Nova Guerra",
                                                    texto=texto), P.SCHEMA_VERIF, 400, system=P.SYS) or {}
    erros = v.get("erros", [])
    ok = (not erros) if nome == "correto" else bool(erros)
    print(f"{'OK ' if ok else 'FALHOU'} {nome:15} erros={len(erros)} falta={len(v.get('falta', []))}  {[e.get('trecho', '')[:60] for e in erros]}", flush=True)
