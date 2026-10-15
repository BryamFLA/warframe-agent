"""Reescreve a pergunta antes da busca, com o MESMO modelo de resposta (gemma4, já carregado: ~1 s).
Resolve referências do histórico ("e a build dele?"), corrige nomes mal transcritos ("ruino" -> Rhino)
e deixa a pergunta completa e autossuficiente. Se falhar ou sair estranha, a busca usa a pergunta original."""
import json, re
from . import config, llm

PROMPT = """Você prepara perguntas de um jogador de Warframe para um buscador. Tarefa:
1. Use o histórico para resolver referências ("dele", "dela", "lá", "isso", "e a build?", "e o prime?").
2. Corrija nomes mal escritos ou mal transcritos por voz para a grafia oficial do jogo
   (ex.: "ruino" -> Rhino, "setus" -> Cetus, "sarina" -> Saryn, "caminho de aço" -> Steel Path, "criótico" -> Cryotic).
3. Escreva UMA pergunta completa e autossuficiente em português, mantendo a intenção original
   (não acrescente assuntos novos, não troque o item perguntado, não responda).
Se a pergunta já estiver clara e completa, devolva-a quase igual.
{dica}HISTÓRICO:
{hist}
PERGUNTA ATUAL: {q}
Responda só JSON: {{"pergunta": "..."}}"""

SCHEMA = {"type": "object", "properties": {"pergunta": {"type": "string"}}, "required": ["pergunta"]}

def _hist(history, n=4, lim=300):
    linhas = []
    for m in (history or [])[-n:]:
        quem = "Jogador" if m.get("role") == "user" else "Assistente"
        txt = re.sub(r"\s+", " ", m.get("content", ""))[:lim]
        linhas.append(f"{quem}: {txt}")
    return "\n".join(linhas) or "(sem histórico)"

def reescrever(q, history=None, nomes=(), model=None):
    """Retorna a pergunta reescrita, ou None se não deu (aí usa-se a original)."""
    dica = f"Nomes do jogo reconhecidos por aproximação na pergunta: {', '.join(nomes)}\n" if nomes else ""
    try:
        txt, _ = llm.chat(model or config.MODEL_ANSWER,
                          [{"role": "user", "content": PROMPT.format(dica=dica, hist=_hist(history), q=q)}],
                          json_schema=SCHEMA, temperature=0, num_predict=90)
        r = json.loads(txt).get("pergunta", "").strip()
    except Exception:
        return None
    if not r or len(r) > 3 * len(q) + 120:      # saída vazia ou que "viajou": ignora
        return None
    return r
