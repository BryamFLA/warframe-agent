"""Reconhece entidades do jogo na pergunta usando títulos e aliases do vault (itens.json)."""
import os, re, json, difflib, collections
from . import config
from .index import norm_text, STOP

GENERIC = set("""prime mod mods arma armas warframe warframes quest jornada missao missoes item itens build melhor
historia jogo game lore todos todas tudo farm farmar onde como conseguir fazer recurso recursos
companheiro sindicato local planeta boss chefe dicas passo""".split())

# palavras comuns do português que nunca devem virar nome do jogo na comparação fonética
COMUNS = set("""quanto quanta quantos custa custo faco faz fazer feito posso pode podem quero queria preciso tenho tem temos
melhor melhores consigo conseguir pegar pego pegam acho achar onde quando como porque qual quais quem esse essa isso este esta
isto aquele aquela dele dela deles mais menos muito muita pouco pouca tudo todos todas nada algum alguma outro outra outros
ainda agora depois antes sempre nunca jogo jogar jogando jogador missao missoes item itens arma armas build ajuda ajudar
falar fala diga dizer saber sabe vale valer compensa usar usando serve servir funciona funcionar comecar comeco final fim
primeiro primeira segundo segunda terceiro rapido rapida facil dificil forte fraco bom boa ruim novo nova velho velha grande
pequeno lugar local mapa planeta farmar farmo farm dropa drop cair cai chance quanto tempo hora horas dias semana hoje amanha
dinheiro platina creditos recurso recursos material materiais peca pecas parte partes blueprint receita construir montar
""".split())

def fonetica(s):
    """Chave fonética simples para nomes transcritos de voz (Rhino~Raino~Ruino, Jackal~Jakao)."""
    s = s.replace("ph", "f").replace("ck", "k").replace("qu", "k").replace("q", "k").replace("c", "k")
    s = s.replace("w", "u").replace("y", "i").replace("h", "").replace("z", "s")
    s = re.sub(r"(.)\1+", r"\1", s)          # letras repetidas
    s = re.sub(r"(ao|al|au)$", "al", s)       # final "-al" falado como "-ao/-au"
    return s

def words(s):
    return re.findall(r"[a-z0-9]+", norm_text(s.replace("&", " e ")))

class EntityIndex:
    def __init__(self, vault=None):
        vault = vault or config.VAULT
        data = json.load(open(os.path.join(vault, "_MODELOS", "dados", "itens.json"), encoding="utf-8"))
        self.items = {e["caminho"]: e for e in data}
        self.alias = collections.defaultdict(set)   # "frase normalizada" -> {caminho}
        self.title_of = {}
        for e in data:
            p = e["caminho"]; t = str(e.get("title", ""))
            self.title_of[p] = t
            names = [t, re.sub(r"\s*\(.*?\)", "", t)] + [str(a) for a in (e.get("aliases") or [])]
            names += [n[4:] for n in names if n.lower().startswith("the ") and len(n) > 8]  # "The Drifter" -> "Drifter"
            for n in names:
                k = " ".join(words(n))
                if k and not (len(k.split()) == 1 and (k in GENERIC or len(k) < 3)):
                    self.alias[k].add(p)
        self.keys = list(self.alias)
        self.fon = {}                       # chave fonética (1-2 palavras) -> chave do alias
        for k in self.keys:
            if len(k.split()) <= 2 and len(k) >= 4:
                self.fon.setdefault(" ".join(fonetica(x) for x in k.split()), k)
        self.fon_keys = list(self.fon)
        self.maxn = max(len(k.split()) for k in self.keys)

    def _rank(self, paths, key):
        # prefere a nota cujo título é exatamente a chave; depois notas não-índice; depois caminho curto
        def score(p):
            t = " ".join(words(self.title_of.get(p, "")))
            return (t != key, "/_" in p, p.startswith("mods/"), len(p))
        return sorted(paths, key=score)

    def find(self, query, fuzzy=True, fonetico=False):
        w = words(query); used = [False] * len(w); found = []
        for n in range(min(self.maxn, len(w)), 0, -1):
            for i in range(len(w) - n + 1):
                if any(used[i:i + n]):
                    continue
                k = " ".join(w[i:i + n])
                if k in self.alias:
                    found.append((i, k, self._rank(self.alias[k], k)))
                    for j in range(i, i + n):
                        used[j] = True
        if fuzzy:   # erros de digitação: n-gramas de 1-3 palavras ainda livres
            for n in (3, 2, 1):
                for i in range(len(w) - n + 1):
                    if any(used[i:i + n]):
                        continue
                    ws = w[i:i + n]; k = " ".join(ws)
                    if len(k) < 5 or any(x in GENERIC or x in STOP or len(x) < 3 for x in ws):
                        continue
                    m = difflib.get_close_matches(k, self.keys, n=1, cutoff=0.88)
                    if m:
                        found.append((i, m[0], self._rank(self.alias[m[0]], m[0])))
                        for j in range(i, i + n):
                            used[j] = True
        if fonetico:   # transcrição de voz: compara pela pronúncia aproximada
            for n in (2, 1):
                for i in range(len(w) - n + 1):
                    if any(used[i:i + n]):
                        continue
                    ws = w[i:i + n]
                    if any(x in GENERIC or x in STOP or x in COMUNS or len(x) < 4 for x in ws):
                        continue
                    m = difflib.get_close_matches(" ".join(fonetica(x) for x in ws), self.fon_keys, n=1,
                                                  cutoff=0.8 if len(ws[0]) >= 5 else 0.88)
                    if m:
                        k = self.fon[m[0]]
                        found.append((i, k, self._rank(self.alias[k], k)))
                        for j in range(i, i + n):
                            used[j] = True
        found.sort()
        # "excal prime" / "rhino prime": promove para a versão Prime quando existir
        out = []
        for i, k, ps in found:
            nxt = w[i + len(k.split())] if i + len(k.split()) < len(w) else ""
            if nxt == "prime" and "prime" not in k:
                tp = " ".join(words(self.title_of.get(ps[0], ""))) + " prime"
                if tp in self.alias:
                    k, ps = tp, self._rank(self.alias[tp], tp)
            out.append((i, k, ps))
        found = out
        return [{"termo": k, "caminhos": ps[:4], "titulo": self.title_of.get(ps[0], k)} for _, k, ps in found]
