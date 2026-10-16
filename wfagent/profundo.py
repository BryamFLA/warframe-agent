"""Modo profundo: para perguntas complexas o agente pensa em etapas, usando o mesmo gemma4:12b como "cérebro" reutilizável.

  1. classificar   -> a pergunta é simples (fluxo normal, uma busca) ou complexa?
  2. planejar      -> com a 1ª busca na mão, monta um plano de 3–7 etapas (cada uma com consulta e nota-fonte do vault)
  3. pesquisar     -> para cada etapa: busca própria + nota indicada pelo plano
  4. escrever      -> rascunho da etapa só com fatos do contexto
  5. verificar     -> o modelo revisa o rascunho contra o contexto (afirmações sem suporte, pontos faltando);
                      se reprovar: busca extra e/ou reescrita (até MAX_REVISOES vezes)
  6. revisar tudo  -> a resposta montada cobre a pergunta? lacunas viram novas etapas (1 rodada)
  7. montar        -> introdução + etapas + conclusão
Cada chamada ao modelo é uma tarefa pequena e focada: é assim que um modelo de 12B rende mais."""
import os, json, re, time
from . import config, llm
from .index import norm_text
from .router import rule_route
from .retrieve import SECTION

MAX_ETAPAS = 7
MAX_REVISOES = int(os.environ.get("WF_MAX_REVISOES", "1"))   # rodadas de verificação/reescrita por etapa
# (no M4 cada chamada lê ~3 mil tokens de contexto a ~130 tok/s: cada rodada a mais custa ~1 min por etapa)
BUDGET_ETAPA = 8000         # caracteres de contexto por etapa
NUM_PREDICT_ETAPA = 800

# ------------------------------------------------------------------ 1. classificação
COMPLEXA_RX = re.compile(
    r"\b(historia|lore|enredo) (do|de) (jogo|game|warframe)\b|\bhistoria (completa|inteira|toda)\b|\bdo (comeco|inicio) ao fim\b"
    r"|\b(em|com) (detalhes?|profundidade)\b|\bdetalhad[ao]\b|\bguia completo\b|\bme (explica|conta|fala) tudo\b|\btudo sobre\b"
    r"|\bresumo (completo|geral)\b|\bexplica(r|cao)? completa\b|\bdo iniciante ao (endgame|fim)\b")
SIMPLES_INTENTS = {"onde_conseguir", "como_construir", "build", "listar_itens_local", "contagem"}

CLASSIF = """Você decide como um assistente de Warframe vai responder a pergunta de um jogador.
- "simples": a resposta está num lugar só e é direta. Ex.: onde conseguir um item, build de um frame, o que é uma mecânica,
  quem é um personagem, dicas de uma quest específica, uma lista ou contagem, uma continuação curta de conversa.
- "complexa": pede uma explicação ampla que junta vários assuntos ou etapas e precisa de várias buscas. Ex.: a história/lore
  geral do jogo, a história de uma facção ou personagem em detalhes do começo ao fim, um guia completo de progressão,
  explicar um sistema grande em todas as partes, comparar várias coisas a fundo, "me explica tudo sobre X".
Exemplos:
- "onde consigo o Rhino?" -> simples
- "qual a história do jogo?" -> complexa
- "quem é o Ballas?" -> simples
- "me conta a história completa do Ballas" -> complexa
- "como funciona o Helminth?" -> simples
- "me faz um guia do iniciante até o endgame" -> complexa
- "qual a melhor build pro Rhino?" -> simples
- "qual a diferença entre Grineer, Corpus e Infested e de onde cada um veio?" -> complexa
Notas que a busca inicial encontrou: {notas}
Pergunta: {q}
Responda só JSON: {{"tipo": "simples" ou "complexa", "motivo": "até 12 palavras"}}"""
SCHEMA_CLASSIF = {"type": "object", "properties": {"tipo": {"type": "string", "enum": ["simples", "complexa"]},
                                                   "motivo": {"type": "string"}}, "required": ["tipo", "motivo"]}

# ------------------------------------------------------------------ 2. plano
PLANO = """Você planeja a pesquisa para responder a uma pergunta COMPLEXA sobre Warframe usando um second brain (vault de notas).
Abaixo está o resultado de uma PRIMEIRA BUSCA e a lista de NOTAS DISPONÍVEIS citadas nela.

PRIMEIRA BUSCA:
{ctx}

NOTAS DISPONÍVEIS (caminho — título):
{notas}

PERGUNTA DO JOGADOR: {q}

Monte um plano de 3 a {maxe} etapas que, juntas, cobrem a resposta completa, na ordem em que devem aparecer
(cronológica para história; do básico ao avançado para guias). As etapas não podem se sobrepor e todas devem
tratar do ASSUNTO DA PERGUNTA (ex.: na história de uma facção, cada etapa é sobre essa facção, não sobre o jogo em geral).
Para cada etapa:
- titulo: curto, como um subtítulo da resposta
- objetivo: o que essa parte deve explicar (1 frase)
- consulta: busca curta, com os nomes do jogo em inglês
- nota: o caminho de UMA nota da lista que é a melhor fonte para a etapa, ou "" se nenhuma servir
Também: titulo (título da resposta inteira) e formato ("narrativa cronológica", "guia passo a passo", "explicação por tópicos" ou "comparação").
Responda só JSON."""
SCHEMA_PLANO = {"type": "object", "properties": {
    "titulo": {"type": "string"}, "formato": {"type": "string"},
    "etapas": {"type": "array", "items": {"type": "object", "properties": {
        "titulo": {"type": "string"}, "objetivo": {"type": "string"}, "consulta": {"type": "string"}, "nota": {"type": "string"}},
        "required": ["titulo", "objetivo", "consulta", "nota"]}}},
    "required": ["titulo", "formato", "etapas"]}

# ------------------------------------------------------------------ 3-5. etapa: escrever e verificar
SYS = """Você é um pesquisador especialista em Warframe e escreve em português do Brasil a partir de trechos de um second brain do jogo.
Regras:
- Use SOMENTE fatos que estão no CONTEXTO. Não invente nomes, números, datas ou acontecimentos.
- Mantenha os nomes do jogo em inglês (Orokin, Sentient, Warframe, Operator, Void...).
- Escreva em prosa explicativa: parágrafos com frases completas que contam o que aconteceu, por quê e o que isso causou.
  Não faça listas de nomes soltos.
- Sem citações [n], sem lista de fontes."""

ESCREVER = """CONTEXTO:
{ctx}

---
PERGUNTA ORIGINAL DO JOGADOR: {q}
Você está escrevendo a parte {i} de {n} de uma resposta completa em formato de {formato}.
Plano completo: {plano}
PARTE {i}: {titulo}
OBJETIVO DESTA PARTE: {objetivo}
NÃO escreva aqui sobre o que é assunto das outras partes: {outras}.
{ja_dito}{anterior}
Escreva só esta parte: 2 a 4 parágrafos (150 a 350 palavras), sem título no início, sem adiantar o assunto das outras partes.
Use do contexto só o que serve à PERGUNTA ORIGINAL e ao objetivo desta parte; ignore o resto. Se a pergunta é sobre
história/lore, não explique mecânicas de jogo (ranks, recompensas, mods, como farmar) a não ser que façam parte da história.
Se o contexto não tiver informação para algum ponto do objetivo, deixe esse ponto de fora (não invente)."""

VERIFICAR = """CONTEXTO:
{ctx}

---
Você é o REVISOR. Abaixo está um texto escrito a partir do CONTEXTO acima, para a parte "{titulo}" (objetivo: {objetivo}).
As outras partes da resposta (escritas separadamente) tratam de: {outras}.

TEXTO:
{texto}

Procure só ERROS GRAVES:
1. erros: fatos inventados, nomes trocados (personagem/facção/quest errada), contradições com o contexto ou ordem errada
   dos acontecimentos. Para cada um: "trecho" (copiado do texto) e "correcao" (o que o contexto diz).
   Também é erro um trecho que trata do assunto de OUTRA parte (correcao: "remover, é assunto de <parte>").
   NÃO conta como erro: paráfrase, resumo, palavras diferentes, conclusões óbvias, ligação entre fatos que o contexto apoia.
2. falta: no máximo 2 pontos CENTRAIS do objetivo que o texto deixou de fora. Lista vazia se o objetivo foi cumprido no essencial.
3. consulta_extra: só se um ponto que falta NÃO estiver no contexto: uma busca curta (nomes em inglês) para achá-lo; senão "".
Na dúvida, não aponte. Texto bom = listas vazias. Responda só JSON."""
SCHEMA_VERIF = {"type": "object", "properties": {
    "erros": {"type": "array", "items": {"type": "object", "properties": {"trecho": {"type": "string"}, "correcao": {"type": "string"}},
                                         "required": ["trecho", "correcao"]}},
    "falta": {"type": "array", "items": {"type": "string"}},
    "consulta_extra": {"type": "string"}}, "required": ["erros", "falta", "consulta_extra"]}

CORRIGIR = """O revisor encontrou problemas no seu texto:
{problemas}
Reescreva a parte "{titulo}" inteira corrigindo isso, usando SOMENTE o CONTEXTO (que pode ter trechos novos).
Se um ponto que falta não estiver no contexto, apenas não o mencione. Mesmo tamanho (2 a 4 parágrafos), sem título."""

# ------------------------------------------------------------------ 6. revisão geral
REVISAR = """PERGUNTA DO JOGADOR: {q}

RESPOSTA MONTADA (partes):
{partes}

Você é o EDITOR. A resposta acima responde bem à pergunta, de forma completa?
Liste em "lacunas" no máximo 1 assunto CENTRAL para a pergunta que ficou totalmente de fora. Não aponte detalhes,
nem nada que já aparece em alguma parte, mesmo que de passagem. Para cada lacuna: titulo, objetivo, consulta (nomes em inglês) e
depois_da_parte (número da parte depois da qual ela deve entrar). Se estiver completa, "lacunas": [].
Responda só JSON."""
SCHEMA_REVISAR = {"type": "object", "properties": {"lacunas": {"type": "array", "items": {"type": "object", "properties": {
    "titulo": {"type": "string"}, "objetivo": {"type": "string"}, "consulta": {"type": "string"},
    "depois_da_parte": {"type": "integer"}}, "required": ["titulo", "objetivo", "consulta", "depois_da_parte"]}}},
    "required": ["lacunas"]}

# ------------------------------------------------------------------ 7. abertura e fechamento
MOLDURA = """PERGUNTA DO JOGADOR: {q}
Título da resposta: {titulo}

PARTES JÁ ESCRITAS:
{partes}

Escreva, em português do Brasil e usando só o que está nas partes:
- introducao: 1 parágrafo (3 a 5 frases) que apresenta o panorama geral e prepara a leitura das partes;
- conclusao: 1 parágrafo (3 a 5 frases) que amarra tudo: o fio que liga as partes e onde a história/o assunto está agora.
Sem repetir frases das partes, sem exageros nem frases de efeito ("prepare-se", "galáxias inteiras"). Responda só JSON."""
SCHEMA_MOLDURA = {"type": "object", "properties": {"introducao": {"type": "string"}, "conclusao": {"type": "string"}},
                  "required": ["introducao", "conclusao"]}

LINK_RX = re.compile(r"\[\[([^\]|#]+?)(?:#[^\]|]*)?(?:\\?\|[^\]]*)?\]\]")


def _json(model, prompt, schema, num_predict, system=None, temperature=0):
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    txt, _ = llm.chat(model, msgs, json_schema=schema, temperature=temperature, num_predict=num_predict)
    try:
        return json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.S)
        return json.loads(m.group(0)) if m else None


class Pensador:
    def __init__(self, agent):
        self.ag = agent
        self.model = agent.answer_model

    # ---------------------------------------------------------- 1
    def classificar(self, q, s, history=None):
        """-> ("simples"|"complexa", motivo, via)"""
        n = norm_text(q)
        if COMPLEXA_RX.search(n):
            return "complexa", "pedido explícito de explicação ampla/detalhada", "regras"
        if s["rota"]["intencao"] in SIMPLES_INTENTS and s["entidades"]:
            return "simples", f"intenção {s['rota']['intencao']} com item reconhecido", "regras"
        notas = list(dict.fromkeys(self.ag.ix.chunks[i].title for i in s["hits"][:6]))
        r = _json(self.model, CLASSIF.format(notas=", ".join(notas), q=s["pergunta_busca"]), SCHEMA_CLASSIF, 80)
        if not r or r.get("tipo") not in ("simples", "complexa"):
            return "simples", "classificação falhou", "llm"
        return r["tipo"], r.get("motivo", ""), "llm"

    # ---------------------------------------------------------- 2
    def notas_citadas(self, hits, lim=40):
        ix, out = self.ag.ix, {}
        for i in hits:
            c = ix.chunks[i]
            out.setdefault(c.path, c.title)
            for m in LINK_RX.finditer(c.text):
                p = m.group(1).strip()
                p = p if p.endswith(".md") else p + ".md"
                if p in ix.by_path and p not in out:
                    out[p] = self.ag.ents.title_of.get(p) or ix.chunks[ix.by_path[p][0]].title
            if len(out) >= lim:
                break
        return out

    def planejar(self, q, s):
        ctx, _ = self.ag.context(s["hits"], budget=7000, per_chunk=2000)
        notas = self.notas_citadas(s["hits"])
        r = _json(self.model, PLANO.format(ctx=ctx, notas="\n".join(f"- {p} — {t}" for p, t in notas.items()),
                                           q=q, maxe=MAX_ETAPAS), SCHEMA_PLANO, 900)
        if not r or not r.get("etapas"):
            return None
        etapas = []
        for e in r["etapas"][:MAX_ETAPAS]:
            if not e.get("titulo"):
                continue
            nota = (e.get("nota") or "").strip()
            e["nota"] = nota if nota in self.ag.ix.by_path else ""
            etapas.append(e)
        r["etapas"] = etapas
        return r if len(etapas) >= 2 else None

    # ---------------------------------------------------------- 3
    def pesquisar(self, etapa, extra_hits=()):
        ix = self.ag.ix
        consulta = f"{etapa.get('consulta', '')} {etapa['titulo']}".strip()
        s = self.ag.search(consulta, reescrever=False)
        forced = []
        if etapa.get("nota"):
            ids = ix.by_path[etapa["nota"]]
            rx = SECTION.get(rule_route(consulta)["intencao"]) or SECTION["historia"]
            # a nota escolhida pelo plano entra inteira, com a seção da intenção primeiro
            forced = [i for i in ids if re.search(rx, ix.chunks[i].head)] + ids
        hits = list(dict.fromkeys(forced + list(extra_hits) + s["hits"]))
        return hits

    # ---------------------------------------------------------- 4-5
    @staticmethod
    def sem_repeticao(texto, feitas, limiar=0.45):
        """Remove parágrafos quase iguais a parágrafos de outras partes (o 12B às vezes recopia a parte anterior)."""
        def bag(t):
            return {w for w in re.findall(r"[a-z0-9]{4,}", norm_text(t))}
        antigos = [bag(par) for p in feitas for par in p["texto"].split("\n\n") if par.strip()]
        pars = [par for par in texto.split("\n\n") if par.strip()]
        manter = []
        for par in pars:
            b = bag(par)
            sim = max((len(b & a) / (len(b | a) or 1) for a in antigos), default=0)
            if sim < limiar:
                manter.append(par)
        if not manter:                  # tudo repetido: mantém o original (melhor que parte vazia)
            return texto, 0
        return "\n\n".join(manter), len(pars) - len(manter)

    @staticmethod
    def resumo_dito(partes, lim=1500):
        """Primeira frase de cada parágrafo das partes já escritas: o redator sabe o que não repetir."""
        frases = []
        for p in partes:
            for par in p["texto"].split("\n\n"):
                f = re.split(r"(?<=[.!?])\s", par.strip(), 1)[0]
                if f:
                    frases.append(f"- ({p['titulo']}) {f}")
        txt = "\n".join(frases)
        return ("JÁ FOI DITO NAS OUTRAS PARTES (não repita, só faça referência se precisar):\n" + txt[-lim:] + "\n") if txt else ""

    def executar_etapa(self, q, plano, k, anterior, log, feitas=()):
        etapa = plano["etapas"][k]
        n = len(plano["etapas"])
        hits = self.pesquisar(etapa)
        ctx, used = self.ag.context(hits, budget=BUDGET_ETAPA, per_chunk=2500)
        resumo_plano = " | ".join(f"{j + 1}. {e['titulo']}" for j, e in enumerate(plano["etapas"]))
        ja_dito = self.resumo_dito(feitas)
        outras = "; ".join(e["titulo"] for j, e in enumerate(plano["etapas"]) if j != k) or "(nenhuma)"
        ult = re.split(r"(?<=[.!?])\s+", anterior.strip())[-1][:300] if anterior else ""
        ant = (f'A parte anterior terminou com: "{ult}"\nAbra esta parte com uma transição curta (uma frase) e siga para '
               'o assunto NOVO desta parte; não reescreva nem resuma a parte anterior.') if ult else ""
        prompt = ESCREVER.format(ctx=ctx, q=q, i=k + 1, n=n, formato=plano.get("formato", "explicação"),
                                 plano=resumo_plano, titulo=etapa["titulo"], objetivo=etapa["objetivo"], anterior=ant, outras=outras,
                                 ja_dito=ja_dito)
        msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": prompt}]
        texto, _ = llm.chat(self.model, msgs, temperature=0.3, num_predict=NUM_PREDICT_ETAPA)
        texto = texto.strip()
        hist = []
        for rodada in range(MAX_REVISOES):
            v = _json(self.model, VERIFICAR.format(ctx=ctx, titulo=etapa["titulo"], objetivo=etapa["objetivo"], texto=texto, outras=outras),
                      SCHEMA_VERIF, 400, system=SYS) or {}
            sem = [f'"{x.get("trecho", "").strip()}" -> {x.get("correcao", "").strip()}' for x in v.get("erros", [])
                   if isinstance(x, dict) and x.get("trecho", "").strip()][:5]
            falta = [x for x in v.get("falta", []) if isinstance(x, str) and x.strip()][:2]
            extra = (v.get("consulta_extra") or "").strip()
            hist.append({"rodada": rodada + 1, "sem_suporte": sem, "falta": falta, "consulta_extra": extra})
            if not sem and not falta:
                log("   ✓ conferido")
                break
            log(f"   ↻ revisão {rodada + 1}: {len(sem)} erro(s), {len(falta)} ponto(s) faltando"
                + (f", busca extra: {extra}" if extra and falta else ""))
            if extra and falta:      # falta informação: busca de novo e amplia o contexto
                s2 = self.ag.search(extra, reescrever=False)
                novos = [h for h in s2["hits"][:5] if h not in used]
                if novos:
                    hits = used + novos
                    ctx, used = self.ag.context(hits, budget=BUDGET_ETAPA + 3000, per_chunk=2500)
                    prompt = ESCREVER.format(ctx=ctx, q=q, i=k + 1, n=n, formato=plano.get("formato", "explicação"),
                                             plano=resumo_plano, titulo=etapa["titulo"], objetivo=etapa["objetivo"], anterior=ant, outras=outras,
                                 ja_dito=ja_dito)
            problemas = "\n".join([f"- Erro: {x}" for x in sem] + [f"- Faltou explicar: {x}" for x in falta])
            msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": prompt},
                    {"role": "assistant", "content": texto},
                    {"role": "user", "content": CORRIGIR.format(problemas=problemas, titulo=etapa["titulo"])}]
            novo, _ = llm.chat(self.model, msgs, temperature=0.2, num_predict=NUM_PREDICT_ETAPA)
            if len(novo.strip()) > 200:
                texto = novo.strip()
        texto, removidos = self.sem_repeticao(texto, feitas)
        if removidos:
            log(f"   ✂️ {removidos} parágrafo(s) repetido(s) de outras partes removido(s)")
        return {"titulo": etapa["titulo"], "texto": texto, "chunks": used, "verificacao": hist}

    def ja_coberto(self, lacuna, partes):
        """O editor de 12B às vezes pede "lacuna" de um assunto já tratado: se os nomes do jogo dela já aparecem no texto, ignora."""
        texto = norm_text(" ".join(p["texto"] for p in partes))
        q = f"{lacuna['titulo']} {lacuna.get('consulta', '')}"
        singular = re.sub(r"\b(\w{4,}?)s\b", r"\1", q)          # "Sentients" -> "Sentient"
        nomes = {e["titulo"] for x in (q, singular) for e in self.ag.ents.find(x, fuzzy=False)}
        return bool(nomes) and all(norm_text(n) in texto for n in nomes)

    # ---------------------------------------------------------- orquestração
    def responder(self, q, s, on_event=None):
        t0 = time.time()
        passos = []
        def log(msg, **kw):
            passos.append(msg)
            if on_event:
                on_event({"tipo": "progresso", "texto": msg, **kw})
        log("🧠 Pergunta complexa: fazendo uma primeira busca e planejando a pesquisa…")
        plano = self.planejar(q, s)
        if not plano:
            return None
        log("📋 Plano: " + " → ".join(e["titulo"] for e in plano["etapas"]),
            plano=[e["titulo"] for e in plano["etapas"]])
        partes, anterior = [], ""
        for k, e in enumerate(plano["etapas"]):
            log(f"🔎 Etapa {k + 1}/{len(plano['etapas'])}: {e['titulo']}" + (f"  ({e['nota']})" if e.get("nota") else ""), etapa=k + 1, total=len(plano["etapas"]))
            p = self.executar_etapa(q, plano, k, anterior, log, feitas=partes)
            partes.append(p); anterior = p["texto"]
        # revisão geral: lacunas viram etapas novas (1 rodada)
        log("🧐 Revisando a resposta inteira…")
        rev = _json(self.model, REVISAR.format(q=q, partes="\n\n".join(
            f"PARTE {j + 1} — {p['titulo']}:\n{p['texto'][:1200]}" for j, p in enumerate(partes))), SCHEMA_REVISAR, 400) or {}
        lacunas = [l for l in rev.get("lacunas", []) if l.get("titulo") and not self.ja_coberto(l, partes)][:1]
        for l in sorted(lacunas, key=lambda l: -int(l.get("depois_da_parte") or len(partes))):
            pos = max(0, min(len(partes), int(l.get("depois_da_parte") or len(partes))))
            l["nota"] = ""
            log(f"➕ Lacuna encontrada: {l['titulo']}")
            plano["etapas"].insert(pos, l)
            p = self.executar_etapa(q, plano, pos, partes[pos - 1]["texto"] if pos else "", log, feitas=partes)
            partes.insert(pos, p)
        log("✍️ Escrevendo introdução e conclusão…")
        m = _json(self.model, MOLDURA.format(q=q, titulo=plano.get("titulo") or q, partes="\n\n".join(
            f"PARTE {j + 1} — {p['titulo']}:\n{p['texto']}" for j, p in enumerate(partes))), SCHEMA_MOLDURA, 600,
            temperature=0.3) or {}
        out = [f"# {plano.get('titulo') or q}", ""]
        if m.get("introducao"):
            out += [m["introducao"].strip(), ""]
        for j, p in enumerate(partes, 1):
            out += [f"## {j}. {p['titulo']}", "", p["texto"], ""]
        if m.get("conclusao"):
            out += ["## Em resumo", "", m["conclusao"].strip()]
        usados = list(dict.fromkeys(i for p in partes for i in p["chunks"]))
        return {"resposta": "\n".join(out).strip(), "chunks": usados, "plano": plano, "lacunas": lacunas,
                "verificacoes": [{"etapa": p["titulo"], "rodadas": p["verificacao"]} for p in partes],
                "passos": passos, "t_total": round(time.time() - t0, 1)}
