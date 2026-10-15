#!/usr/bin/env python3
"""Avalia a busca em CONVERSA (perguntas de continuação e nomes mal transcritos), com e sem a reescrita pelo LLM.
Uso: .venv/bin/python eval/eval_conversa.py"""
import os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wfagent.agent import Agent

def H(*pares):  # histórico: (pergunta, resumo da resposta)
    out = []
    for q, r in pares:
        out += [{"role": "user", "content": q}, {"role": "assistant", "content": r}]
    return out

RHINO = H(("onde consigo o ruino?", "Para conseguir o Rhino, compre o blueprint no Mercado e derrote o Jackal em Fossa, Vênus."))
SARYN = H(("como pego a sarina", "A Saryn: blueprint no Mercado, componentes da Kela De Thaym em Merrow, Sedna."))
CETUS = H(("o que eu posso fazer em setus?", "Em Cetus você pode fazer bounties, pesca, mineração e caçar Eidolons à noite."))
SP = H(("o que é o caminho de aço?", "O Steel Path é uma versão mais difícil do Star Chart, com inimigos mais fortes."))
SOMA = H(("qual a melhor build pra soma prime", "Para a Soma Prime use Serration, Split Chamber, Vital Sense e Point Strike."))
CASOS = [  # (histórico, pergunta, caminho(s) esperado(s), regex da seção ou None)
    (RHINO, "e qual a melhor build dele?", "warframes/regular/rhino.md", r"Build"),
    (RHINO, "e o prime dele, onde dropa?", "warframes/primes/rhino_prime.md", None),
    (RHINO, "qual a história dele?", "warframes/regular/rhino.md", r"Hist"),
    (RHINO, "e esse boss que dropa, como mata?", "lore/chefes/jackal.md", None),
    (SARYN, "e a build dela pro steel path?", "warframes/regular/saryn.md", r"Build"),
    (SARYN, "quanto custa o blueprint dela?", "warframes/regular/saryn.md", None),
    (CETUS, "e quais recursos tem lá?", "locais/open-worlds/cetus.md", None),
    (CETUS, "como eu chego lá?", "locais/open-worlds/cetus.md", r"Chegar"),
    (CETUS, "e como caça esses eidolons?", "missoes/bounties/eidolon.md|lore/chefes/eidolon_teralyst.md|locais/open-worlds/cetus.md", None),
    (SP, "como eu desbloqueio isso?", "mecanicas/steel_path.md", r"Desbloque|Requisit|Como Acessar|Como Funciona"),
    (SP, "e o que ganho jogando nele?", "mecanicas/steel_path.md", None),
    (SOMA, "e onde dropa ela?", "armas/primarias/soma_prime.md", None),
    ([], "onde farmo o criótico", "recursos/raridades/raro/cryotic.md", None),
    ([], "como pego o jakau", "lore/chefes/jackal.md", None),
    ([], "qual a melhor bild pra sarina no caminho de aço", "warframes/regular/saryn.md", r"Build"),
    ([], "onde fica o necralisco", "locais/open-worlds/deimos.md", None),
]

def rodar(ag, nome):
    ok, t0, falhas = 0, time.time(), []
    for hist, q, p, rx in CASOS:
        ant = [m["content"] for m in reversed(hist) if m["role"] == "user"]
        s = ag.search(q, fonetico=True, anteriores=ant, history=hist)
        hit = any(ag.ix.chunks[i].path in p.split("|") and (rx is None or re.search(rx, ag.ix.chunks[i].head))
                  for i in s["hits"][:5])
        ok += hit
        if not hit:
            falhas.append((q, s["pergunta_busca"], ag.ix.chunks[s["hits"][0]].path if s["hits"] else "-"))
    print(f"{nome:16s} {ok}/{len(CASOS)}  ({(time.time() - t0) / len(CASOS):.1f} s/pergunta)")
    for f in falhas:
        print("   falhou:", f)

ag = Agent(reescrever=False)
rodar(ag, "sem reescrita")
ag.reescrever = True
rodar(ag, "com reescrita")
