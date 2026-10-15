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
| Resposta | `gemma4:12b` | `WF_MODEL_ANSWER` |
| Roteador (opcional, desligado) | `qwen3.5:4b` | `WF_MODEL_ROUTER`, `WF_ROUTER_LLM=off\|auto\|on` |
| Embedding | `qwen3-embedding:0.6b` | `WF_MODEL_EMBED` |

O vault é lido de `../warframe-vault` (mude com `WF_VAULT`). Embeddings ficam em `cache/` e só os trechos alterados são recalculados.

## Uso

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ollama pull gemma4:12b qwen3-embedding:0.6b

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

## Resultados (Mac mini M4 16 GB, 14/10/2026)

**Busca** — `eval/eval_busca.py`, acerto no top-5 (430 perguntas):

| Configuração | Total | 40 perguntas "difíceis" (gíria, PT, sem nome exato) |
|---|---|---|
| Só entidades + BM25 | 98,3% | 85,0% |
| + vetores `qwen3-embedding:0.6b` | **99,5%** | **97,5%** |
| + vetores `bge-m3` | 99,3% | 92,5% |
| + vetores `embeddinggemma` | 98,6% | 90,0% |
| + vetores qwen3 + roteador LLM `qwen3.5:4b` | 98,9% | 95,0% (e muito mais lento) |

**Resposta** — `eval/eval_respostas.py`, 15 perguntas (respostas em `eval/respostas_*.md`):

| Modelo | Tempo médio | Observação |
|---|---|---|
| `gemma4:12b` | 37,7 s | Fiel ao contexto, não inventou nada nas respostas revisadas → **padrão** |
| `qwen3.5:9b` | 38,8 s | Mais longo; inventou detalhes quando o contexto era fraco (ex.: habilidades erradas) |

Gargalo: leitura do contexto (~200 tokens/s) e geração (~18 tokens/s). O chat mostra a resposta em streaming.
Primeira pergunta após ligar o Mac leva ~2–3 min (carregar o modelo; depois fica 30 min na memória).

## Telegram

Bot direto no Mac (sem n8n, sem porta aberta): veja [docs/telegram.md](docs/telegram.md). O guia antigo com n8n continua em [docs/n8n_telegram.md](docs/n8n_telegram.md).
