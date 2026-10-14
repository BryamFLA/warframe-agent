"""Indexa o vault: chunks por '## ' (sub-chunks por '### ' em seções longas), BM25 e embeddings."""
import os, re, json, math, hashlib, unicodedata, collections
import numpy as np
from . import config, llm

STOP = set("a o as os de da do das dos e em no na nos nas um uma para por com que qual quais como onde posso pode me eu meu minha mais the of to and is in se ao aos sua seu ser ter tem pra ou isso esse essa".split())
SKIP_HEAD = re.compile(r"(🔗 Relacionados|📚 Fontes)")

def norm_text(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))

def tokens(s):
    return [w for w in re.findall(r"[a-z0-9]+", norm_text(s)) if w not in STOP and len(w) > 1]

def parse_note(path):
    t = open(path, encoding="utf-8").read()
    m = re.match(r"---\n(.*?)\n---\n", t, re.S)
    fm, body = (m.group(1), t[m.end():]) if m else ("", t)
    if re.search(r"^rag:\s*false", fm, re.M):
        return None
    get = lambda k: (re.search(rf"^{k}:\s*(.*)$", fm, re.M) or [None, ""])[1].strip().strip('"')
    al = get("aliases").strip("[]")
    return {"title": get("title") or os.path.basename(path)[:-3], "aliases": al, "tipo": get("tipo"),
            "status": get("status"), "resumo": get("resumo"), "body": body}

class Chunk:
    __slots__ = ("id", "path", "title", "head", "text", "tipo")
    def __init__(self, i, path, title, head, text, tipo):
        self.id, self.path, self.title, self.head, self.text, self.tipo = i, path, title, head, text, tipo

def build_chunks(vault=None):
    vault = vault or config.VAULT
    chunks, notes = [], {}
    for dp, dn, fn in os.walk(vault):
        dn[:] = [d for d in dn if not d.startswith(".") and d != "_MODELOS"]
        for f in sorted(fn):
            if not f.endswith(".md"):
                continue
            p = os.path.join(dp, f); rel = os.path.relpath(p, vault)
            n = parse_note(p)
            if not n:
                continue
            notes[rel] = n
            pre = f"{n['title']} | {n['aliases']}\n"
            for part in re.split(r"\n(?=## )", n["body"]):
                head = part.split("\n", 1)[0].strip("# ").strip()
                if SKIP_HEAD.match(head) or len(part.strip()) < 20:
                    continue
                subs = re.split(r"\n(?=### )", part)
                if len(part) > 2500 and len(subs) > 1:
                    chunks.append(Chunk(len(chunks), rel, n["title"], head, pre + subs[0], n["tipo"]))
                    for sp in subs[1:]:
                        sh = head + " > " + sp.split("\n", 1)[0].strip("# ").strip()
                        chunks.append(Chunk(len(chunks), rel, n["title"], sh, pre + head + "\n" + sp, n["tipo"]))
                else:
                    chunks.append(Chunk(len(chunks), rel, n["title"], head, pre + part, n["tipo"]))
    return chunks, notes

class BM25:
    def __init__(self, texts, k1=1.2, b=0.75):
        self.docs = [tokens(t) for t in texts]
        self.N = len(self.docs); self.avg = sum(map(len, self.docs)) / max(self.N, 1)
        self.df = collections.Counter(w for d in self.docs for w in set(d))
        self.inv = collections.defaultdict(list)
        for i, d in enumerate(self.docs):
            for w, c in collections.Counter(d).items():
                self.inv[w].append((i, c))
        self.k1, self.b = k1, b

    def search(self, q, k=50, restrict=None):
        acc = collections.Counter()
        for w in set(tokens(q)):
            if w not in self.df:
                continue
            idf = math.log(1 + (self.N - self.df[w] + .5) / (self.df[w] + .5))
            for i, c in self.inv[w]:
                if restrict is not None and i not in restrict:
                    continue
                L = len(self.docs[i])
                acc[i] += idf * c * (self.k1 + 1) / (c + self.k1 * (1 - self.b + self.b * L / self.avg))
        return acc.most_common(k)

QUERY_PREFIX = {  # instrução de consulta recomendada por modelo de embedding
    "qwen3-embedding": "Instruct: Given a question about the game Warframe, retrieve the guide passage that answers it\nQuery: ",
    "embeddinggemma": "task: search result | query: ",
    "bge-m3": "",
}

class Index:
    """Chunks + BM25 + matriz de embeddings (cache em disco por modelo e hash do conteúdo)."""
    def __init__(self, embed_model=None, vault=None, verbose=True, with_vectors=True):
        self.embed_model = embed_model or config.MODEL_EMBED
        self.chunks, self.notes = build_chunks(vault)
        self.bm25 = BM25([c.text for c in self.chunks])
        self.by_path = collections.defaultdict(list)
        for c in self.chunks:
            self.by_path[c.path].append(c.id)
        self.qprefix = next((v for k, v in QUERY_PREFIX.items() if self.embed_model.startswith(k)), "")
        self.E = self._load_embeddings(verbose) if with_vectors else None

    def vector_ids(self):
        """Subconjunto com embedding: notas conceituais inteiras + resumo/Onde Conseguir dos itens.
        Itens específicos são achados pelo reconhecimento de entidades + BM25; o vetor cobre a linguagem natural."""
        concept = ("mecanicas/", "lore/", "missoes/", "locais/", "_W")
        if config.EMBED_SCOPE == "tudo":
            return list(range(len(self.chunks)))
        return [c.id for c in self.chunks if c.path.startswith(concept) or c.head == ""
                or (c.head.startswith("🌍 Onde Conseguir") and not c.path.startswith("mods/"))]

    def _load_embeddings(self, verbose):
        os.makedirs(config.CACHE, exist_ok=True)
        tag = re.sub(r"[^a-z0-9]+", "_", self.embed_model.lower())
        fv, fm = os.path.join(config.CACHE, f"emb_{tag}.npy"), os.path.join(config.CACHE, f"emb_{tag}.json")
        self.vids = self.vector_ids()
        keys = [hashlib.md5(self.chunks[i].text[:config.EMBED_CHARS].encode()).hexdigest() for i in self.vids]
        store = {}
        if os.path.exists(fv) and os.path.exists(fm):
            M = np.load(fv); ks = json.load(open(fm))
            store = {k: M[n] for n, k in enumerate(ks)}
        todo = [n for n, k in enumerate(keys) if k not in store]
        def save():
            ks = list(store); np.save(fv, np.stack([store[k] for k in ks]).astype(np.float32)); json.dump(ks, open(fm, "w"))
        if todo and verbose:
            print(f"[index] gerando {len(todo)} embeddings com {self.embed_model} ...", flush=True)
        B = 32
        for b in range(0, len(todo), B):
            part = todo[b:b + B]
            vecs = llm.embed([self.chunks[self.vids[n]].text[:config.EMBED_CHARS] for n in part], self.embed_model, batch=B)
            for n, v in zip(part, vecs):
                store[keys[n]] = np.asarray(v, dtype=np.float32)
            if verbose and (b // B) % 20 == 19:
                print(f"[index] {b + B}/{len(todo)}", flush=True); save()
        if todo:
            save()
        E = np.stack([store[k] for k in keys]).astype(np.float32)
        E /= np.linalg.norm(E, axis=1, keepdims=True) + 1e-9
        return E

    def vsearch(self, q, k=50, prefix=""):
        v = np.asarray(llm.embed([prefix + q], self.embed_model)[0], dtype=np.float32)
        v /= np.linalg.norm(v) + 1e-9
        s = self.E @ v
        idx = np.argpartition(-s, min(k, len(s) - 1))[:k]
        return sorted(((self.vids[int(i)], float(s[i])) for i in idx), key=lambda x: -x[1])
