#!/usr/bin/env python3
"""Avalia a BUSCA do agente (sem gerar resposta).
Uso: .venv/bin/python eval/eval_busca.py [--embed MODELO] [--sem-vetor] [--router off|auto|on] [--k 5] [--amostra 120]"""
import os, re, sys, ast, random, argparse, collections, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wfagent import config
from wfagent.agent import Agent

ap = argparse.ArgumentParser()
ap.add_argument("--embed"); ap.add_argument("--sem-vetor", action="store_true")
ap.add_argument("--router", default="off"); ap.add_argument("--k", type=int, default=5)
ap.add_argument("--amostra", type=int, default=120)
ap.add_argument("--reescrever", action="store_true", help="liga a reescrita pelo LLM (lento: ~1 s por pergunta)")
a = ap.parse_args()
router = {"off": False, "auto": "auto", "on": True}[a.router]
ag = Agent(embed_model=a.embed, use_llm_router=router, use_vectors=not a.sem_vetor, reescrever=a.reescrever)
random.seed(7)
V = config.VAULT
def title(rel):
    t = open(os.path.join(V, rel), encoding="utf-8").read(3000)
    return (re.search(r'^title:\s*"?(.*?)"?\s*$', t, re.M) or [0, ""])[1]

cases = []  # (categoria, pergunta, caminho_esperado, regex_secao|None)
src = open(os.path.join(V, "_MODELOS", "rag_eval.py"), encoding="utf-8").read()
for q, p in ast.literal_eval(src[src.index("Q=[") + 2: src.index("]\n", src.index("Q=[")) + 1]):
    cases.append(("perguntas-alvo", q, p, None))
files = sorted(ag.ix.by_path)
quests = [f for f in files if f.startswith("missoes/jornadas/") and "/_" not in f]
for f in quests:
    t = title(f)
    cases.append(("jornada: o que faz", f"O que a jornada {t} faz", f, None))
    cases.append(("jornada: dicas p/ terminar", f"Dicas de como terminar a jornada {t}", f, r"Dica|Passo|Etapa"))
for q in ["Qual a história do jogo", "Me conte a história do Warframe", "Resumo da história do game", "Qual é o lore do Warframe", "história completa do warframe do começo ao fim"]:
    cases.append(("história do jogo", q, "lore/cronologia/cronologia.md", None))
wf = [f for f in files if f.startswith("warframes/") and "/_" not in f]
ar = [f for f in files if f.startswith("armas/") and "/_" not in f and not f.startswith("armas/amps/")]
for f in random.sample(wf, min(a.amostra, len(wf))):
    cases.append(("build warframe", f"Qual a melhor build para o {title(f)}", f, r"Build"))
for f in random.sample(ar, min(a.amostra, len(ar))):
    cases.append(("build arma", f"Qual a melhor build para a {title(f)}", f, r"Build"))
    cases.append(("onde conseguir arma", f"Onde consigo a arma {title(f)}", f, None))
rec = [f for f in files if f.startswith("recursos/") and "/_" not in f]
for f in random.sample(rec, min(a.amostra, len(rec))):
    cases.append(("onde conseguir recurso", f"Como posso conseguir {title(f)}", f, None))
HUB = {"locais/open-worlds/cetus.md": ["CETUS", "Plains of Eidolon"], "locais/open-worlds/fortuna.md": ["FORTUNA", "Orb Vallis"],
       "locais/open-worlds/deimos.md": ["Deimos", "Necralisk"], "locais/open-worlds/zariman.md": ["Zariman"],
       "locais/open-worlds/duviri.md": ["Duviri"], "locais/hollvania.md": ["Höllvania"]}
for p, ns in HUB.items():
    for n in ns:
        cases.append(("listar itens do hub", f"Me liste todos os itens que eu posso adquirir em {n}", p, r"📦"))
        cases.append(("listar itens do hub", f"O que eu posso conseguir em {n}", p, r"📦"))
# perguntas livres, com erros e gírias
for q, p, rx in [("onde dropa criotico", "recursos/raridades/raro/cryotic.md", None),
                 ("qual build boa pro excal prime no steel path", "warframes/primes/excalibur_prime.md", r"Build"),
                 ("como faço a alternox passo a passo", "armas/primarias/alternox.md", None),
                 ("o q da pra farmar na terra", "locais/planetas/terra.md", None),
                 ("quem é a lotus", "lore/personagens/lotus.md", None),
                 ("como mata o profit taker", "lore/chefes/profit_taker.md", None),
                 ("como desbloqueio o helminth", "mecanicas/helminth.md", None),
                 ("como funciona o sistema de rivens", "mecanicas/rivens.md", None),
                 ("onde farmar argon crystal", "recursos/raridades/raro/argon_crystal.md", None),
                 ("o que fazer depois do second dream", "mecanicas/guia_de_progressao.md", None)]:
    cases.append(("perguntas livres", q, p, rx))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from perguntas_dificeis import HARD
for q, ps in HARD:
    cases.append(("perguntas difíceis", q, ps, None))
res = collections.OrderedDict(); fails = collections.defaultdict(list); t0 = time.time()
for cat, q, p, rx in cases:
    s = ag.search(q); hits = s["hits"][:a.k] if cat != "listar itens do hub" else s["hits"][:max(a.k, 12)]
    ok = any(ag.ix.chunks[i].path in p.split("|") and (rx is None or re.search(rx, ag.ix.chunks[i].head)) for i in hits)
    r = res.setdefault(cat, [0, 0]); r[0] += ok; r[1] += 1
    if not ok:
        top = ag.ix.chunks[s["hits"][0]] if s["hits"] else None
        fails[cat].append((q, s["rota"]["intencao"], top.path + " :: " + top.head[:40] if top else "-"))
tot = [sum(v[0] for v in res.values()), sum(v[1] for v in res.values())]
print(f"\nCONFIG embed={ag.ix.embed_model} vetor={not a.sem_vetor} router={a.router} reescrita={a.reescrever} k={a.k}  ({len(cases)} perguntas, {time.time()-t0:.0f}s)")
for c, (x, n) in res.items():
    print(f"  {c:28s} {x:4d}/{n:<4d} {100*x/n:5.1f}%")
print(f"  {'TOTAL':28s} {tot[0]:4d}/{tot[1]:<4d} {100*tot[0]/tot[1]:5.1f}%")
for c, v in fails.items():
    print(f"\n-- falhas {c} ({len(v)})"); [print("   ", x) for x in v[:6]]
