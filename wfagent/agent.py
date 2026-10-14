"""Agente de perguntas e respostas do Warframe sobre o vault (RAG local com Ollama)."""
import time, json, re
from . import config, llm
from .index import Index
from .entities import EntityIndex
from .router import route as do_route
from .retrieve import retrieve

SYSTEM = """Você é um assistente especialista em Warframe e responde em português do Brasil.
Use SOMENTE as informações do CONTEXTO (trechos do second brain do jogo). Regras:
- Seja direto: no máximo ~250 palavras, exceto quando pedirem uma lista completa. Não repita o contexto inteiro.
- Seja organizado (passos numerados para "como fazer", listas para "liste").
- Mantenha nomes do jogo em inglês (Excalibur, Orokin Cell, Steel Path...).
- Cite as fontes no texto como [n] (números dos trechos). Não escreva uma lista "Fontes" no fim: ela é anexada automaticamente.
- Se o contexto não tiver a resposta, diga que não encontrou no guia e sugira o que o jogador pode procurar. Não invente números, chances ou nomes.
- Quando pedirem "todos os itens", liste todos os itens que estão no contexto, agrupados por tipo.
- Se houver INVENTÁRIO DO JOGADOR, adapte a resposta ao que ele já tem ou não tem."""

class Agent:
    def __init__(self, embed_model=None, answer_model=None, router_model=None, use_llm_router=None, use_vectors=True):
        if router_model: config.MODEL_ROUTER = router_model
        self.answer_model = answer_model or config.MODEL_ANSWER
        self.ix = Index(embed_model=embed_model, with_vectors=use_vectors)
        self.ents = EntityIndex()
        if use_llm_router is None:
            use_llm_router = {"off": False, "auto": "auto", "on": True}[config.ROUTER_LLM]
        self.use_llm_router, self.use_vectors = use_llm_router, use_vectors

    def search(self, q):
        t = time.time()
        ents = self.ents.find(q)
        r = do_route(q, ents, self.use_llm_router)
        for term in r.get("termos_jogo", []):
            for e in self.ents.find(term, fuzzy=False):
                if e["caminhos"][0] not in [x["caminhos"][0] for x in ents]:
                    ents.append(e)
        hits = retrieve(self.ix, q, r, ents, use_vectors=self.use_vectors)
        return {"rota": r, "entidades": ents, "hits": hits, "t_busca": round(time.time() - t, 2)}

    def context(self, hits, budget=None):
        budget = budget or config.MAX_CONTEXT_CHARS
        parts, used, total = [], [], 0
        for n, i in enumerate(hits, 1):
            c = self.ix.chunks[i]
            txt = c.text.split("\n", 1)[1] if "\n" in c.text else c.text
            txt = re.sub(r"\[\[[^\]|]*?\\?\|([^\]]+)\]\]", r"\1", txt)          # [[caminho|Nome]] -> Nome
            txt = re.sub(r"\[\[([^\]]+?)(\.md)?\]\]", lambda m: m.group(1).split("/")[-1], txt)
            txt = re.sub(r"^> \[!\w+\]\s*", "", txt, flags=re.M)
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

    def ask(self, q, inventario=None, history=None, on_token=None):
        s = self.search(q)
        big = s["rota"]["intencao"] == "listar_itens_local"
        hits = s["hits"]
        list_hits = [i for i in hits if "📦" in self.ix.chunks[i].head and "Resumo" not in self.ix.chunks[i].head] if big else []
        ctx, used = self.context([i for i in hits if i not in list_hits])
        user = f"CONTEXTO:\n{ctx}\n\n"
        if big:
            user += "(A lista completa de itens será anexada automaticamente depois da sua resposta: faça só um resumo organizado do que dá para conseguir e fazer lá, com os destaques.)\n\n"
        if inventario:
            user += "INVENTÁRIO DO JOGADOR:\n" + json.dumps(inventario, ensure_ascii=False)[:6000] + "\n\n"
        user += f"PERGUNTA: {q}"
        msgs = [{"role": "system", "content": SYSTEM}] + (history or [])[-6:] + [{"role": "user", "content": user}]
        t = time.time()
        if on_token:
            ans, raw = llm.chat_stream(self.answer_model, msgs, on_token, temperature=0.3, num_predict=1000)
        else:
            ans, raw = llm.chat(self.answer_model, msgs, temperature=0.3, num_predict=1000)
        ans = ans.strip()
        if list_hits:
            extra = "\n\n### Lista completa\n" + self.full_list(list_hits)
            ans += extra
            if on_token:
                on_token(extra)
        fontes = [{"n": n, "nota": self.ix.chunks[i].path, "secao": self.ix.chunks[i].head} for n, i in enumerate(used, 1)]
        return {"resposta": ans, "fontes": fontes, "rota": s["rota"],
                "entidades": [e["titulo"] for e in s["entidades"]],
                "tempo": {"busca": s["t_busca"], "resposta": round(time.time() - t, 1),
                          "tokens_entrada": raw.get("prompt_eval_count"), "tokens_saida": raw.get("eval_count")}}
