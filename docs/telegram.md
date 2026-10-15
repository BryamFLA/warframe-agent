# Bot do Telegram

O bot roda no Mac ao lado da API e conversa com o Telegram por *long polling*: ele mesmo busca as mensagens,
então **não precisa abrir porta no roteador nem ter URL pública**. A porta 8765 continua só na rede de casa.

```
Telegram ◄──► telegram_bot.py (Mac) ──► API local /ask (gemma4 + vault)
                 │ áudio: faster-whisper large-v3-turbo (CPU)
                 └ voz:   Edge TTS pt-BR + efeito Ordis -> mensagem de voz (OGG/Opus)
```

## Instalar (uma vez)

```bash
cd ~/GitHub/warframe-agent
.venv/bin/pip install -r requirements-telegram.txt
.venv/bin/python telegram_bot.py --configurar
```

1. No Telegram, fale com **@BotFather** → `/newbot` → escolha nome e usuário → copie o **token**.
2. Cole o token quando o `--configurar` pedir (não aparece na tela).
3. Mande `/start` para o seu bot: quem mandar primeiro vira **administrador**.

Rodar na mão: `.venv/bin/python telegram_bot.py` · Como serviço (inicia com o Mac): `./servico_mac.sh instalar`

## Usar

- Texto → resposta completa em texto (listas de itens incluídas).
- Áudio → mostra o que entendeu, responde curto em texto **e** em áudio (voz do Ordis).
- `/audio` liga/desliga resposta em áudio também para perguntas por texto. `/nova` esquece a conversa.

## Amigos (acesso)

- Quem não está liberado recebe o próprio ID e você recebe um aviso com o comando pronto.
- `/liberar <id> <nome>`, `/remover <id>`, `/usuarios` (só o administrador).
- Tudo roda no seu Mac: as perguntas entram numa fila (uma por vez, inclusive as do PC).

## Arquivos

- `cache/telegram.json` — token, administradores e usuários (não vai para o Git; permissão 600).
- `cache/telegram.log` — log quando roda como serviço (`./servico_mac.sh log`).
- Tempo típico no Mac mini M4: texto ~10–30 s; áudio ~15–30 s (transcrição ~5 s + resposta + voz ~2 s).
