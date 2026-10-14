# Warframe Agent

Assistente de Warframe 100% local: responde perguntas usando o second brain [`warframe-vault`](../warframe-vault) e modelos abertos no **Ollama**.

## Como funciona

```
pergunta ─► 1. entidades (títulos/aliases do vault, tolera erro de digitação)
          ─► 2. roteador: regras rápidas → LLM pequeno só se precisar (intenção + consulta reescrita em termos do jogo)
          ─► 3. busca híbrida: seção certa da nota certa + BM25 + vetores (RRF);
                "liste tudo de X" carrega todas as partes da lista (parent-document)
          ─► 4. LLM de resposta com as fontes numeradas  [+ inventário do jogador, opcional]
```

| Papel | Modelo padrão | Variável |
|---|---|---|
| Resposta | `qwen3.5:9b` | `WF_MODEL_ANSWER` |
| Roteador | `qwen3.5:4b` | `WF_MODEL_ROUTER` |
| Embedding | `qwen3-embedding:0.6b` | `WF_MODEL_EMBED` |

O vault é lido de `../warframe-vault` (mude com `WF_VAULT`). Embeddings ficam em `cache/` e só os trechos alterados são recalculados.

## Uso

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ollama pull qwen3.5:9b qwen3.5:4b qwen3-embedding:0.6b

.venv/bin/python cli.py                      # chat no terminal
.venv/bin/python cli.py --debug "onde pego o frame de gelo"
.venv/bin/python cli.py --inventario meu_inventario.yaml   # formato: warframe-vault/_MODELOS/MODELO_inventario_jogador.md
.venv/bin/uvicorn api:app --port 8765        # API: POST /ask {"pergunta": "...", "inventario": {...}}
```

## Avaliação

```bash
.venv/bin/python eval/eval_busca.py                 # acerto da busca (~470 perguntas)
.venv/bin/python eval/eval_busca.py --sem-vetor     # só BM25 + entidades
.venv/bin/python eval/eval_respostas.py --modelo qwen3.5:9b   # respostas completas em Markdown
```
