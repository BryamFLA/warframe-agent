"""Busca híbrida: entidade direta (seção certa da nota certa) + BM25 + vetorial, fundidos por RRF."""
import re
from . import config

SECTION = {  # intenção -> regex do heading da seção preferida
    "onde_conseguir": r"Onde Conseguir|Como Construir|Recompensas|Como Conseguir|Fontes de Farm|O Que Farmar",
    "como_construir": r"Como Construir|Passo a Passo|Onde Conseguir|Forja",
    "build": r"Build|Helminth|Sinergias|Habilidades",
    "historia": r"Hist[oó]ria|Lore|Narrativa|Cronologia|Origem|Resumo",
    "jornada": r"Passo a Passo|Dicas|Narrativa|Hist[oó]ria|Pr[eé]-requisitos|Recompensas|Etapas",
    "listar_itens_local": r"📦|O Que Farmar|Recursos|O Que Fazer",
    "o_que_fazer": r"Recomenda|Regras|Fase|Checklist|Prioridade|Rotina",
    "contagem": r"Contagem",
    "atividades_local": r"O Que (D[aá] para )?Fazer|Conte[uú]do Especial|Miss[oõ]es|Como Chegar|O Que Farmar|Ficha|Recompensas|Vendedores",
    "mecanica": r"Como Funciona|Mec[aâ]nica|Resumo|Dicas|Desbloque|Requisit|Como Acessar|Como Come[cç]ar|Pr[eé]-requisito|Como Usar",
}
DEFAULT_NOTES = {
    "historia": ["lore/cronologia/cronologia.md"],
    "o_que_fazer": ["mecanicas/guia_de_progressao.md", "mecanicas/rotinas_diarias_e_semanais.md"],
}

PREF_DIRS = {
    "build": ("warframes/", "armas/", "companheiros/"),
    "onde_conseguir": ("warframes/", "armas/", "companheiros/", "recursos/", "mods/"),
    "como_construir": ("armas/", "warframes/", "companheiros/"),
    "historia": ("lore/", "missoes/jornadas/"),
    "jornada": ("missoes/jornadas/",),
}

def rrf(lists, k=60, weights=None):
    sc = {}
    for li, lst in enumerate(lists):
        w = (weights or [1] * len(lists))[li]
        for rank, (i, _) in enumerate(lst):
            sc[i] = sc.get(i, 0) + w / (k + rank + 1)
    return sorted(sc.items(), key=lambda x: -x[1])

def retrieve(ix, q, route, ents, top_k=None, use_vectors=True):
    top_k = top_k or config.TOP_K
    intent = route["intencao"]; rx = SECTION.get(intent)
    query = route.get("consulta_busca") or q
    if query != q:
        query = q + " " + query
    lists, weights = [], []
    # 1) busca lexical e vetorial
    lists.append(ix.bm25.search(query, 60)); weights.append(1.0)
    if use_vectors:
        lists.append(ix.vsearch(query, 60, prefix=ix.qprefix)); weights.append(1.0)
    # 2) entidades reconhecidas: seções da nota certa, priorizando a seção da intenção
    pref_dirs = PREF_DIRS.get(intent, ())
    def pick(ps):  # entidade ambígua (ex.: Kullervo warframe x chefe): escolhe a pasta que combina com a intenção
        return next((p for p in ps if p.startswith(pref_dirs)), ps[0]) if pref_dirs else ps[0]
    ent_paths = [pick(e["caminhos"]) for e in ents]
    if pref_dirs:   # "build da Saryn no Steel Path": o item (pasta da intenção) vem antes da mecânica citada
        ent_paths.sort(key=lambda p: not p.startswith(pref_dirs))
    if route.get("local"):
        ent_paths.insert(0, route["local"])
    ent_paths += [p for p in DEFAULT_NOTES.get(intent, []) if not ents]
    forced = []
    for p in dict.fromkeys(ent_paths):
        ids = ix.by_path.get(p, [])
        if not ids:
            continue
        if pref_dirs and not p.startswith(pref_dirs) and any(x.startswith(pref_dirs) for x in ent_paths):
            continue   # item da intenção presente: a mecânica citada não ganha prioridade (só BM25/vetor)
        pref = [i for i in ids if rx and re.search(rx, ix.chunks[i].head)]
        intro = [] if intent == "contagem" else [i for i in ids if ix.chunks[i].head == "" or i == ids[0]]
        forced += pref + intro
    if forced:
        lists.append([(i, 1) for i in dict.fromkeys(forced)]); weights.append(2.0)
    fused = rrf(lists, weights=weights)
    hits = [i for i, _ in fused]
    # 3) parent-document: perguntas de "listar tudo" carregam todas as partes da lista do lugar
    if intent == "listar_itens_local" and route.get("local"):
        allparts = [i for i in ix.by_path.get(route["local"], []) if "📦" in ix.chunks[i].head]
        hits = allparts + [h for h in hits if h not in allparts]
        top_k = max(top_k, len(allparts) + 3)
    # seção longa dividida em sub-trechos: quando o trecho "pai" entra, os 2 primeiros sub-trechos vêm logo depois
    out = []
    for h in hits:
        if h in out:
            continue
        out.append(h)
        c = ix.chunks[h]
        for j in range(h + 1, min(h + 3, len(ix.chunks))):
            cj = ix.chunks[j]
            if cj.path == c.path and cj.head.startswith(c.head + " > ") and j not in out:
                out.append(j)
    return out[:top_k]
