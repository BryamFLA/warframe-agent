# Agente Warframe no Telegram via n8n

O n8n só repassa mensagens: quem responde é a API do agente no Mac (`POST /ask`). Nada de IA roda no n8n.

```
Telegram ──► n8n: Telegram Trigger ──► HTTP Request (POST /ask no Mac) ──► Telegram: Send Message
```

## Pré-requisitos

- API rodando no Mac (`./servico_mac.sh status` → `ok: true`). Chave em `cache/api_key.txt`.
- O n8n precisa **alcançar o Mac** (mesma rede: `http://192.168.3.38:8765`; ou n8n no próprio Mac: `http://localhost:8765`).
- O **Telegram Trigger** precisa de uma URL pública para o webhook do n8n (n8n Cloud, ou túnel como Cloudflare Tunnel/ngrok apontando para o n8n). **Não exponha a porta 8765 do Mac na internet** — exponha só o n8n.
- Bot criado no @BotFather (token vai na credencial "Telegram API" do n8n).

## Nós

1. **Telegram Trigger** — Updates: `message`.
2. **HTTP Request**
   - Method `POST`, URL `http://192.168.3.38:8765/ask`
   - Header `X-API-Key` = sua chave (guarde como credencial *Header Auth* no n8n)
   - Body (JSON):
     ```json
     {
       "pergunta": "{{ $json.message.text }}",
       "modo": "texto",
       "sessao": "tg-{{ $json.message.chat.id }}"
     }
     ```
   - Timeout: 180000 ms (a 1ª pergunta após o Mac ficar parado carrega o modelo).
   - `sessao` faz o agente lembrar as últimas mensagens daquele chat ("e a build dele?").
3. **Code** (opcional, mensagens > 4096 caracteres, ex.: listas de Cetus):
   ```js
   const t = $json.resposta + ($json.lista_completa ? "\n\n" + $json.lista_completa : "");
   const partes = t.match(/[\s\S]{1,3900}(\n|$)/g) || [t];
   return partes.map(p => ({ json: { texto: p, chat: $('Telegram Trigger').item.json.message.chat.id } }));
   ```
4. **Telegram → Send Message** — Chat ID `{{ $json.chat }}` (ou `{{ $('Telegram Trigger').item.json.message.chat.id }}`), Text `{{ $json.texto }}` (ou `{{ $json.resposta }}`), Parse Mode `Markdown` (se der erro de formatação, use sem parse mode).

## Dicas

- Use **Typing action** (Telegram → Send Chat Action = typing) antes do HTTP Request, porque a resposta leva ~10–40 s.
- Restrinja quem usa o bot: um nó **IF** checando `message.from.id` contra a sua lista.
- Mensagem de voz no Telegram: baixe o arquivo (Telegram → Get File) e transcreva com o mesmo faster-whisper (endpoint futuro `/transcrever`) — ainda não implementado.
