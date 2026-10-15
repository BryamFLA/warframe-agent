"""Entende a pergunta: intenção + entidades + consulta reescrita.
Primeiro regras (rápidas, sem LLM); o LLM pequeno só entra quando as regras não bastam."""
import re, json
from . import config, llm
from .index import norm_text

INTENTS = ["onde_conseguir", "como_construir", "build", "historia", "jornada", "listar_itens_local",
           "o_que_fazer", "atividades_local", "contagem", "mecanica", "comparar", "outro"]
HUBS = {"cetus": "locais/open-worlds/cetus.md", "plains": "locais/open-worlds/cetus.md", "eidolon": "locais/open-worlds/cetus.md",
        "fortuna": "locais/open-worlds/fortuna.md", "vallis": "locais/open-worlds/fortuna.md",
        "deimos": "locais/open-worlds/deimos.md", "necralisk": "locais/open-worlds/deimos.md", "cambion": "locais/open-worlds/deimos.md",
        "zariman": "locais/open-worlds/zariman.md", "chrysalith": "locais/open-worlds/zariman.md",
        "duviri": "locais/open-worlds/duviri.md", "hollvania": "locais/hollvania.md", "1999": "locais/hollvania.md"}

RULES = [  # (intenção, regex sobre a pergunta normalizada sem acento)
    ("listar_itens_local", r"\b(liste|listar|lista|todos os itens|tudo (o )?que|quais itens)\b.*\b(adquirir|conseguir|farmar|comprar|pegar|obter|tem|da pra|posso)\b|\bo que (eu )?(posso|da pra|consigo) (conseguir|farmar|adquirir|obter|pegar) (em|no|na)\b"),
    ("build", r"\bbuild|\bmontar (o|a|um|uma)?\s*\w+.*\bmods?\b|\bquais mods\b|\bmelhores mods\b"),
    ("jornada", r"\b(jornada|quest|missao da historia)\b|\bcomo (terminar|completar|passar|fazer) (a )?(jornada|quest)\b"),
    ("historia", r"\b(historia|lore|enredo|narrativa|quem (e|foi|era))\b"),
    ("como_construir", r"\b(passo a passo|como (criar|construir|craftar|fabricar|montar|fazer) )|\bforja\b|\bfoundry\b"),
    ("onde_conseguir", r"\b(onde|como) (eu )?((posso|poderia|devo|da pra|consigo) )?(consigo|conseguir|acho|achar|encontro|encontrar|farmo|farmar|dropa|obter|obtenho|pego|pegar|compro|comprar)\b|\bonde (dropa|cai|farma)\b|\bdrop(a|s)?\b"),
    ("mecanica", r"\bo que (e|sao|significa|faz)\b|\bcomo funciona|\bpra que serve|\bpara que serve|\bcomo (eu )?(fa[cç]o pra |faco para |posso )?(libero|liberar|desbloqueio|desbloquear|destravo|destravar|subir|evoluir|aumento|aumentar|ganhar|ganho|acesso|acessar|entro|entrar)\b"),
    ("o_que_fazer", r"\bo que (eu )?((posso|devo|consigo|da pra|tem pra|tem para|vale) )?(faco|fazer)\b|\bproximo passo\b|\bpor onde comecar\b|\b(diari|semana)"),
    ("comparar", r"\b(melhor|pior) (que|entre)\b|\bvs\.?\b|\bcomparar\b|\bou o\b.*\?"),
]

HUB_PATHS = set(HUBS.values())

def rule_route(q, ents=()):
    n = norm_text(q)
    intent = next((i for i, rx in RULES if re.search(rx, n)), "outro")
    hub = next((p for k, p in HUBS.items() if re.search(rf"\b{k}\b", n)), None)
    if not hub:   # nome do lugar mal transcrito/digitado ("setus") mas reconhecido como entidade
        hub = next((p for e in ents for p in e["caminhos"] if p in HUB_PATHS), None)
    if hub and intent in ("o_que_fazer", "outro", "mecanica") and re.search(
            r"\b(fazer|faco|atividades?|tem (em|no|na|pra fazer)|vale a pena)\b", n) and not re.search(r"\b(farmar|conseguir|adquirir|itens)\b", n):
        intent = "atividades_local"
    if re.search(r"\b(quant[oa]s|numero de|total de|quantidade de)\b", n) and any(
            p.endswith("_Indice.md") for e in ents for p in e["caminhos"]):
        intent = "contagem"        # "quantos warframes tem no jogo?" -> seção 🔢 Contagem do índice
    if intent == "listar_itens_local" and not hub:
        intent = "outro"
    if hub and intent in ("outro", "o_que_fazer") and re.search(r"\b(farmar|conseguir|adquirir|itens)\b", n):
        intent = "listar_itens_local"
    return {"intencao": intent, "local": hub}

SCHEMA = {"type": "object", "properties": {
    "intencao": {"type": "string", "enum": INTENTS},
    "consulta_busca": {"type": "string"},
    "termos_jogo": {"type": "array", "items": {"type": "string"}}},
    "required": ["intencao", "consulta_busca", "termos_jogo"]}

PROMPT = """Você classifica perguntas sobre o jogo Warframe para um sistema de busca.
Responda só JSON. Campos:
- intencao: uma de {intents}
  (onde_conseguir=como obter/farmar um item; como_construir=passo a passo de forja; build=mods/setup;
   historia=lore/enredo; jornada=quest: o que faz, como completar, dicas; listar_itens_local=listar itens de um lugar;
   o_que_fazer=próximo passo/rotina do jogador; atividades_local=o que dá para fazer num lugar (Cetus, Fortuna...); mecanica=como funciona um sistema; comparar=comparação; outro)
- consulta_busca: reescreva a pergunta como consulta curta de busca, com os nomes oficiais do jogo em inglês
  (ex.: "criótico" -> "Cryotic"; "jornada" -> "quest") e palavras-chave das seções (Onde Conseguir, Build, História, Passo a Passo, Dicas, Itens).
- termos_jogo: nomes próprios do jogo citados (itens, warframes, armas, lugares, quests, facções), na grafia oficial.
Exemplos:
- "o que é o caminho de aço" -> {{"intencao":"mecanica","consulta_busca":"Steel Path como funciona","termos_jogo":["Steel Path"]}}
- "onde pego o frame de gelo" -> {{"intencao":"onde_conseguir","consulta_busca":"Frost Onde Conseguir","termos_jogo":["Frost"]}}
- "como trocar itens com outros jogadores" -> {{"intencao":"mecanica","consulta_busca":"Trading troca de itens Platinum","termos_jogo":["Trading"]}}
- "qual frame é bom pra tankar" -> {{"intencao":"o_que_fazer","consulta_busca":"warframe tanque iniciante Rhino guia de progressão","termos_jogo":["Rhino"]}}
Entidades já reconhecidas no vault (podem ajudar): {ents}
Pergunta: {q}"""

def llm_route(q, ents):
    txt, _ = llm.chat(config.MODEL_ROUTER, [{"role": "user", "content": PROMPT.format(
        intents=", ".join(INTENTS), ents=json.dumps([e["titulo"] for e in ents], ensure_ascii=False), q=q)}],
        json_schema=SCHEMA, temperature=0, num_ctx=4096, num_predict=200)
    try:
        return json.loads(txt)
    except Exception:
        return {"intencao": "outro", "consulta_busca": q, "termos_jogo": []}

def route(q, ents, use_llm="auto"):
    r = rule_route(q, ents)
    r.update({"consulta_busca": q, "termos_jogo": [], "via": "regras"})
    need = use_llm is True or (use_llm == "auto" and (r["intencao"] == "outro" or not ents))
    if need:
        l = llm_route(q, ents)
        if r["intencao"] == "outro" and l.get("intencao") in INTENTS:
            r["intencao"] = l["intencao"]
        r["consulta_busca"] = l.get("consulta_busca") or q
        r["termos_jogo"] = l.get("termos_jogo") or []
        r["via"] = "regras+llm"
    return r
