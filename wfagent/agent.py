"""Agente de perguntas e respostas do Warframe sobre o vault (RAG local com Ollama)."""
import time, json, re
from . import config, llm
from .index import Index, norm_text
from .entities import corrigir_nomes, words
from .entities import EntityIndex
from .router import route as do_route
from .retrieve import retrieve
from .reescrita import reescrever

SYSTEM = """Você é um assistente especialista em Warframe e responde em português do Brasil.
Use SOMENTE as informações do CONTEXTO (trechos do second brain do jogo). Regras:
- Seja direto: no máximo ~250 palavras, exceto quando pedirem uma lista completa. Não repita o contexto inteiro.
- Seja organizado (passos numerados para "como fazer", listas para "liste").
- Mantenha nomes do jogo em inglês (Excalibur, Orokin Cell, Steel Path...).
- Cite as fontes no texto como [n] (números dos trechos). Não escreva uma lista "Fontes" no fim: ela é anexada automaticamente.
- Se o contexto não tiver a resposta, diga que não encontrou no guia e sugira o que o jogador pode procurar. Não invente números, chances ou nomes.
- Quando pedirem "todos os itens", liste todos os itens que estão no contexto, agrupados por tipo.
- Se houver INVENTÁRIO DO JOGADOR, adapte a resposta ao que ele já tem ou não tem."""

VOZ = """
MODO VOZ: a resposta será FALADA em voz alta durante o jogo.
- No máximo 3 a 4 frases curtas (até ~60 palavras no total), com o essencial primeiro.
- Escreva para ser ouvido, num ritmo calmo: frases de no máximo 15 palavras, terminadas em ponto final.
- Use vírgulas para criar pausas naturais: depois de expressões de abertura ("Para isso,", "Primeiro,", "Depois disso,"),
  entre itens de uma enumeração e antes de explicações ("o Rhino, que é um tanque,").
- Sem markdown, sem listas, sem emojis, sem citações [n], sem tabelas.
- Escreva números por extenso quando curtos ("dois Orokin Cell"), porcentagens como "38 por cento"."""

SEGUIMENTO = re.compile(r"\b(dele|dela|deles|delas|nele|nela|ele|ela|isso|nisso|disso|esse|essa|esses|essas|este|esta|"
                        r"aquele|aquela|mesmo|mesma|la|lá)\b|^e\b|^(e )?(qual|quais|onde|como|quanto)\b.{0,25}$")

class Agent:
    def __init__(self, embed_model=None, answer_model=None, router_model=None, use_llm_router=None, use_vectors=True,
                 reescrever=None):
        if router_model: config.MODEL_ROUTER = router_model
        self.answer_model = answer_model or config.MODEL_ANSWER
        self.ix = Index(embed_model=embed_model, with_vectors=use_vectors)
        self.ents = EntityIndex()
        if use_llm_router is None:
            use_llm_router = {"off": False, "auto": "auto", "on": True}[config.ROUTER_LLM]
        self.use_llm_router, self.use_vectors = use_llm_router, use_vectors
        self.reescrever = config.REESCREVER if reescrever is None else reescrever

    def search(self, q, fonetico=False, anteriores=(), history=None):
        t = time.time()
        q_orig, qr = q, None
        ents0 = self.ents.find(q, fonetico=fonetico)
        exatas = [e for e in ents0 if e["termo"] == e.get("falado")]
        seguimento = bool(history) and bool(SEGUIMENTO.search(norm_text(q)))
        # reescreve só quando ajuda: continuação de conversa, nome aproximado (voz/erro) ou nenhum nome reconhecido
        if self.reescrever and (seguimento or not exatas or len(exatas) < len(ents0)):
            qr = reescrever(q, history if seguimento or not exatas else None,
                            [e["titulo"] for e in ents0], self.answer_model)
            if qr:
                achados = {p for e in self.ents.find(qr, fonetico=fonetico) for p in e["caminhos"]}
                if any(e["caminhos"][0] not in achados for e in exatas):
                    qr = None  # o modelo trocou/perdeu um nome que o jogador disse certo: descarta a reescrita
            q = qr or q
        t_re = round(time.time() - t, 2)
        ents = self.ents.find(q, fonetico=fonetico) if qr else ents0
        for e in exatas:       # nomes ditos certos nunca se perdem
            if e["caminhos"][0] not in [x["caminhos"][0] for x in ents]:
                ents.append(e)
        if not ents and qr:
            ents = ents0
        herdadas = []
        if not ents and anteriores and SEGUIMENTO.search(norm_text(q)):
            # pergunta de continuação ("e a build dele?"): herda o item/lugar da pergunta anterior
            for prev in anteriores[:2]:
                herdadas = self.ents.find(prev, fonetico=fonetico)
                if herdadas and re.search(r"\bprime\b", norm_text(q)):   # "e o prime dele?" -> versão Prime
                    herdadas = [(self.ents.find(e["titulo"] + " Prime", fuzzy=False) or [e])[0]
                                if "Prime" not in e["titulo"] else e for e in herdadas]
                if herdadas:
                    ents = herdadas
                    break
        r = do_route(q, ents, self.use_llm_router)
        if herdadas:
            r["consulta_busca"] = q + " " + " ".join(e["titulo"] for e in herdadas)
            r["herdou"] = [e["titulo"] for e in herdadas]
        for term in r.get("termos_jogo", []):
            for e in self.ents.find(term, fuzzy=False):
                if e["caminhos"][0] not in [x["caminhos"][0] for x in ents]:
                    ents.append(e)
        if qr and not seguimento:   # sem conversa: busca com o texto original + o reescrito (um cobre o outro)
            r["consulta_busca"] = qr if r.get("consulta_busca") in (None, q) else r["consulta_busca"]
            hits = retrieve(self.ix, q_orig, r, ents, use_vectors=self.use_vectors)
        else:
            hits = retrieve(self.ix, q, r, ents, use_vectors=self.use_vectors)
        return {"rota": r, "entidades": ents, "hits": hits, "t_busca": round(time.time() - t, 2),
                "pergunta_busca": q, "t_reescrita": t_re}

    def context(self, hits, budget=None, per_chunk=2500):
        budget = budget or config.MAX_CONTEXT_CHARS
        parts, used, total = [], [], 0
        for n, i in enumerate(hits, 1):
            c = self.ix.chunks[i]
            txt = c.text.split("\n", 1)[1] if "\n" in c.text else c.text
            txt = re.sub(r"\[\[[^\]|]*?\\?\|([^\]]+)\]\]", r"\1", txt)          # [[caminho|Nome]] -> Nome
            txt = re.sub(r"\[\[([^\]]+?)(\.md)?\]\]", lambda m: m.group(1).split("/")[-1], txt)
            txt = re.sub(r"^> \[!\w+\]\s*", "", txt, flags=re.M)
            txt = re.sub(r"^\|[-| :]+\|\s*$\n?", "", txt, flags=re.M)              # linha separadora de tabela
            txt = re.sub(r"[ \t]{2,}", " ", txt)
            lim = per_chunk * 2 if n == 1 else per_chunk     # o trecho mais relevante entra mais completo
            if len(txt) > lim:
                txt = txt[:lim].rsplit("\n", 1)[0] + "\n…"
            block = f"[{n}] ({c.path} — {c.head or c.title})\n{txt.strip()}"
            if total + len(block) > budget and parts:
                break
            parts.append(block); used.append(i); total += len(block)
        return "\n\n".join(parts), used

    def full_list(self, hits):
        """Monta a lista completa de itens a partir das seções 📦 (sem LLM: completa e instantânea)."""
        out = []
        for i in hits:
            c = self.ix.chunks[i]
            if "📦" not in c.head or "Resumo" in c.head:
                continue
            cat = re.sub(r"^📦 Itens de .*? — ", "", c.head)
            cat = re.sub(r" — parte \d+/\d+.*$| \(.*$", "", cat)
            rows = re.findall(r"^\| \[\[[^\]|]*?\\?\|([^\]]+)\]\] \| (.*?) \|\s*$", c.text, re.M)
            if not rows:
                continue
            if not out or out[-1][0] != cat:
                out.append((cat, []))
            out[-1][1].extend(rows)
        lines = []
        for cat, rows in out:
            lines.append(f"\n**{cat} ({len(rows)})**")
            for name, how in rows:
                how = re.sub(r"\*\*|\[\[[^\]|]*?\\?\|([^\]]+)\]\]", lambda m: m.group(1) or "", how)
                lines.append(f"- {name} — {how[:110]}{'…' if len(how) > 110 else ''}")
        return "\n".join(lines)

    def ask(self, q, inventario=None, history=None, on_token=None, modo="texto"):
        M = config.MODES.get(modo, config.MODES["texto"])
        s = self.search(q, fonetico=(modo == "voz"),
                        anteriores=[m["content"] for m in reversed(history or []) if m.get("role") == "user"],
                        history=history)
        big = s["rota"]["intencao"] == "listar_itens_local"
        hits = s["hits"]
        list_hits = [i for i in hits if "📦" in self.ix.chunks[i].head and "Resumo" not in self.ix.chunks[i].head] if big else []
        ctx, used = self.context([i for i in hits if i not in list_hits], budget=M["budget"], per_chunk=M["per_chunk"])
        user = f"CONTEXTO:\n{ctx}\n\n"
        if big:
            user += "(A lista completa de itens será anexada automaticamente depois da sua resposta: faça só um resumo organizado do que dá para conseguir e fazer lá, com os destaques.)\n\n"
        if inventario:
            user += "INVENTÁRIO DO JOGADOR:\n" + json.dumps(inventario, ensure_ascii=False)[:6000] + "\n\n"
        if s["entidades"]:   # pergunta transcrita de voz/digitada com erro ("ruino", "setus"): diz ao modelo o nome certo
            user += ("NOMES DO JOGO RECONHECIDOS NA PERGUNTA (podem estar escritos errado na pergunta; use estes): "
                     + ", ".join(dict.fromkeys(e["titulo"] for e in s["entidades"])) + "\n\n")
        pq = corrigir_nomes(q, s["entidades"])
        if norm_text(s["pergunta_busca"]) != norm_text(pq):
            user += f"PERGUNTA DO JOGADOR: {pq}\nPERGUNTA INTERPRETADA (use para entender referências e nomes): {s['pergunta_busca']}"
        else:
            user += f"PERGUNTA: {pq}"
        msgs = [{"role": "system", "content": SYSTEM + (VOZ if modo == "voz" else "")}] + (history or [])[-6:] + [{"role": "user", "content": user}]
        t = time.time()
        if on_token:
            ans, raw = llm.chat_stream(self.answer_model, msgs, on_token, temperature=0.3, num_predict=M["num_predict"])
        else:
            ans, raw = llm.chat(self.answer_model, msgs, temperature=0.3, num_predict=M["num_predict"])
        ans = ans.strip()
        lista = self.full_list(list_hits) if list_hits else ""
        if lista and modo != "voz":   # na voz a lista vai separada (para a tela), não é falada
            extra = "\n\n### Lista completa\n" + lista
            ans += extra
            if on_token:
                on_token(extra)
        fontes = [{"n": n, "nota": self.ix.chunks[i].path, "secao": self.ix.chunks[i].head} for n, i in enumerate(used, 1)]
        return {"resposta": ans, "lista_completa": lista if modo == "voz" else "", "fontes": fontes, "rota": s["rota"],
                "entidades": [e["titulo"] for e in s["entidades"]], "pergunta_busca": s["pergunta_busca"],
                "tempo": {"busca": s["t_busca"], "reescrita": s["t_reescrita"], "resposta": round(time.time() - t, 1),
                          "tokens_entrada": raw.get("prompt_eval_count"), "tokens_saida": raw.get("eval_count")}}
