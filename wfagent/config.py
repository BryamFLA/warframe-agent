"""Configuração do agente. Tudo pode ser sobrescrito por variáveis de ambiente WF_*."""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VAULT = os.environ.get("WF_VAULT", os.path.join(os.path.dirname(ROOT), "warframe-vault"))
CACHE = os.environ.get("WF_CACHE", os.path.join(ROOT, "cache"))
OLLAMA = os.environ.get("WF_OLLAMA", "http://localhost:11434")
MODEL_ROUTER = os.environ.get("WF_MODEL_ROUTER", "qwen3.5:4b")    # entende/reescreve a pergunta
MODEL_ANSWER = os.environ.get("WF_MODEL_ANSWER", "gemma4:12b")    # escreve a resposta (venceu o A/B: mais fiel ao contexto)
MODEL_EMBED = os.environ.get("WF_MODEL_EMBED", "qwen3-embedding:0.6b")
TOP_K = int(os.environ.get("WF_TOP_K", "8"))          # chunks enviados ao modelo
MAX_CONTEXT_CHARS = int(os.environ.get("WF_MAX_CTX", "14000"))
KEEP_ALIVE = os.environ.get("WF_KEEP_ALIVE", "30m")
EMBED_SCOPE = os.environ.get("WF_EMBED_SCOPE", "seletivo")   # "seletivo" ou "tudo"
EMBED_CHARS = int(os.environ.get("WF_EMBED_CHARS", "1200"))
NUM_CTX = int(os.environ.get("WF_NUM_CTX", "8192"))    # fixo para o Ollama não recarregar o modelo a cada pergunta
ROUTER_LLM = os.environ.get("WF_ROUTER_LLM", "off")   # off | auto | on  (no A/B o LLM roteador não melhorou a busca e deixou mais lento)
# Perfis de resposta. Leitura do contexto (~140 tok/s no M4) é o gargalo: menos contexto = resposta mais rápida.
MODES = {
    "texto": {"budget": 9000, "per_chunk": 2500, "num_predict": 700},
    "voz":   {"budget": 2800, "per_chunk": 1000, "num_predict": 160},
}
