# 🤖 Warframe Agent — o Ordis que roda no seu PC

**Um modelo pequeno + uma boa base de conhecimento + lógica bem feita = um assistente que responde como especialista.**

O Warframe Agent é um assistente de IA **100% local** (sem nuvem, sem API paga) que responde qualquer pergunta sobre Warframe usando o [warframe-vault](https://github.com/BryamFLA/warframe-vault), um grafo de conhecimento com mais de 3.300 notas.

> 🧪 **Status: BETA inicial.** Funciona, foi testado com centenas de perguntas, e está evoluindo rápido.

---

## A tese

Modelos gigantes não são a única saída. Este projeto prova que um modelo **leve (Gemma 4 de 12B)**, rodando num **Mac mini de 16 GB**, entrega respostas precisas quando o código faz o trabalho pesado: encontrar a informação certa, planejar, verificar e só então responder.

Warframe foi escolhido por ser um domínio **propositalmente difícil** — história fragmentada, centenas de itens, regras que se cruzam e muita gíria da comunidade. Se funciona aqui, funciona em documentação técnica, suporte ao cliente ou qualquer base interna.

## Dois produtos em um

### 1. Um agente genérico para modelos leves
A arquitetura não depende de Warframe. Troque o vault por outra base em Markdown e você tem um assistente especializado rodando em hardware comum.

- **Entende o que você quer** — reconhece nomes, apelidos e até erros de digitação ("frame de gelo" → Frost).
- **Busca no lugar certo** — vai direto à **seção** certa da nota certa, combinando busca por palavras e por significado.
- **Pensa antes de responder perguntas grandes** — no *modo profundo*, divide a pergunta em etapas, pesquisa cada uma, **revisa o próprio rascunho** em busca de erros e só depois monta a resposta final.
- **Não inventa** — responde com base nas fontes do vault, citadas na resposta.

### 2. O Ordis para quem joga
Para o jogo em si, o objetivo é recriar o **Ordis**, a IA da nave do jogador:

- 🎙️ **Segure uma tecla e pergunte em voz alta** durante a partida.
- 🔊 **Ouça a resposta em voz** e leia o texto numa janela sobre o jogo.
- 💬 Também disponível pelo **Telegram** e por **API**.

## Resultados

Testado num **Mac mini M4 (16 GB)** em outubro de 2026:

| O que medimos | Resultado |
|---|---|
| Acerto da busca (430 perguntas) | **99,5%** |
| Acerto em perguntas "difíceis" (gíria, sem nome exato) | **97,5%** |
| Tempo médio de resposta | **~38 s** |
| Invenção de fatos (15 respostas revisadas) | **nenhuma** |

Na comparação de modelos, o Gemma 4 12B foi mais fiel ao conteúdo do que o Qwen 3.5 9B, que inventou detalhes quando a informação era escassa — por isso virou o padrão.

## 🗺️ Roadmap

- [x] Busca híbrida por seção + resposta com fontes
- [x] Modo profundo: planejamento, verificação e revisão
- [x] Bot de Telegram e API
- [x] Voz no PC do jogo: fala → texto (Whisper) e resposta falada
- [ ] **GraphRAG** — usar as ligações do vault para responder perguntas que cruzam vários temas
- [ ] Classificação mais esperta entre perguntas simples e complexas
- [ ] Voz com a personalidade do Ordis (modelo de voz dedicado)
- [ ] Respostas mais rápidas

---

## Para desenvolvedores

<details>
<summary><b>Como funciona por dentro</b></summary>

```
pergunta ─► 1. entidades (títulos/aliases do vault, tolera erro de digitação)
         ─► 2. roteador: regras rápidas → LLM pequeno só se precisar
         ─► 3. busca híbrida: seção certa da nota certa + BM25 + vetores (RRF);
               "liste tudo de X" carrega todas as partes da lista (parent-document)
         ─► 4. LLM de resposta com as fontes numeradas [+ inventário do jogador, opcional]
```

**Modo profundo** (`wfagent/profundo.py`) — para perguntas amplas ("história completa dos Grineer", "guia do iniciante ao endgame"):

```
1ª busca ─► classificar ── simples ─► fluxo normal
                       └ complexa ─► plano (3–7 etapas)
   para cada etapa: busca ─► rascunho ─► VERIFICADOR ─► (reprovou: busca extra / reescrita)
   editor: cobre a pergunta? lacuna ─► nova etapa ─► introdução + etapas + conclusão
```

~10–12 min por resposta longa no M4. O modo voz nunca usa o modo profundo.

| Papel | Modelo padrão | Variável |
|---|---|---|
| Resposta | `gemma4:12b` | `WF_MODEL_ANSWER` |
| Roteador (opcional, desligado) | `qwen3.5:4b` | `WF_MODEL_ROUTER`, `WF_ROUTER_LLM=off\|auto\|on` |
| Embedding | `qwen3-embedding:0.6b` | `WF_MODEL_EMBED` |

Outras opções: `WF_VAULT` (padrão `../warframe-vault`), `WF_PROFUNDIDADE=simples` (desliga o modo profundo), `WF_MAX_REVISOES` (padrão 1). Embeddings ficam em `cache/` e só trechos alterados são recalculados.
</details>

<details>
<summary><b>Instalação e uso</b></summary>

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ollama pull gemma4:12b qwen3-embedding:0.6b

.venv/bin/python cli.py                                   # chat no terminal
.venv/bin/python cli.py --debug "onde pego o frame de gelo"
.venv/bin/python cli.py --inventario meu_inventario.yaml  # formato: warframe-vault/_MODELOS/MODELO_inventario_jogador.md
.venv/bin/uvicorn api:app --port 8765                     # API: POST /ask {"pergunta": "...", "inventario": {...}}
```

- **API:** campo `"profundidade": "auto" | "simples" | "profunda"`; `/ask/stream` envia `{"tipo":"progresso",...}` a cada etapa.
- **Telegram:** bot direto no Mac, sem porta aberta — veja [`docs/telegram.md`](docs/telegram.md). `/profundo <pergunta>` força o modo profundo; `/rapido <pergunta>` desliga. Guia antigo com n8n: [`docs/n8n_telegram.md`](docs/n8n_telegram.md).
- **Voz no PC do jogo (Windows):** veja [`cliente_pc/LEIA-ME.md`](cliente_pc/LEIA-ME.md).
</details>

<details>
<summary><b>Avaliação completa</b></summary>

```bash
.venv/bin/python eval/eval_busca.py                          # acerto da busca
.venv/bin/python eval/eval_busca.py --sem-vetor              # só BM25 + entidades
.venv/bin/python eval/eval_respostas.py --modelo qwen3.5:9b  # respostas completas em Markdown
.venv/bin/python eval/teste_profundo.py                      # modo profundo
.venv/bin/python eval/teste_verificador.py                   # verificador com erros plantados
```

**Busca** — acerto no top-5 (430 perguntas), Mac mini M4 16 GB, 14/10/2026:

| Configuração | Total | 40 perguntas "difíceis" |
|---|---|---|
| Só entidades + BM25 | 98,3% | 85,0% |
| + vetores `qwen3-embedding:0.6b` | **99,5%** | **97,5%** |
| + vetores `bge-m3` | 99,3% | 92,5% |
| + vetores `embeddinggemma` | 98,6% | 90,0% |
| + vetores qwen3 + roteador LLM `qwen3.5:4b` | 98,9% | 95,0% (muito mais lento) |

**Resposta** — 15 perguntas (respostas em `eval/respostas_*.md`):

| Modelo | Tempo médio | Observação |
|---|---|---|
| `gemma4:12b` | 37,7 s | Fiel ao contexto, não inventou nada nas respostas revisadas → padrão |
| `qwen3.5:9b` | 38,8 s | Mais longo; inventou detalhes quando o contexto era fraco |

Gargalo: leitura do contexto (~200 tokens/s) e geração (~18 tokens/s). A resposta aparece em streaming. A primeira pergunta após ligar o Mac leva ~2–3 min (carregamento do modelo, que depois fica 30 min na memória).
</details>

---

*Warframe e Ordis são marcas da Digital Extremes. Projeto de fãs, sem afiliação oficial.*
