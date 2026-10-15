# Assistente de voz — PC do jogo (Windows)

Segure **F9**, fale a pergunta, solte. O PC transcreve sua voz, pergunta ao agente que roda no **Mac mini** e responde em voz (neural masculina, `pt-BR-AntonioNeural` via Edge TTS) enquanto mostra o texto numa janela por cima do jogo. **F10** mostra/esconde a janela.

- **Transcrição:** Whisper `large-v3-turbo` na placa NVIDIA (~1–1,5 GB de VRAM). Sem GPU disponível, cai sozinho para o processador (mais lento).
- **Voz:** Edge TTS (vozes neurais da Microsoft, grátis, precisa de internet). Sem internet, usa o Kokoro offline (mais robótico).

## Instalar (uma vez)

1. Instale o **Python 3.12** em python.org (marque *Add python.exe to PATH*).
2. Copie esta pasta `cliente_pc` para o PC (ex.: `C:\WarframeVoz`).
3. Dê dois cliques em **`instalar.bat`** (baixa ~1,5 GB: bibliotecas CUDA, voz Kokoro de reserva e, no 1º uso, ~1,6 GB do modelo de transcrição).
4. Abra `config.json` e confira:
   - `api_url`: `http://192.168.3.38:8765` (IP do Mac; se mudar, veja em Ajustes do Sistema → Rede no Mac);
   - `api_key`: a chave que está no Mac em `warframe-agent/cache/api_key.txt`.
5. Rode **`testar.bat`**: fala uma frase de teste, transcreve de volta e faz uma pergunta ao Mac.

## Usar

- Dê dois cliques em **`iniciar.bat`** e abra o Warframe em **janela sem borda** (*Borderless*), senão a janela não aparece por cima.
- Segure F9 → fale → solte. Apertar F9 de novo interrompe a fala.
- Se o atalho não funcionar dentro do jogo, rode `iniciar.bat` como administrador.

## Ajustes (`config.json`)

| Campo | O que faz |
|---|---|
| `tecla_falar` / `tecla_janela` | Teclas (ex.: `f9`, `caps lock`, `x`) |
| `stt_modelo` | `large-v3-turbo` (padrão), `small` (mais leve, pior) |
| `stt_device` | `auto` (GPU se der, senão CPU), `cuda` ou `cpu` |
| `stt_beam` | 5 (mais preciso) ou 1 (mais rápido) |
| `tts` | `edge` (natural, online) ou `kokoro` (offline, robótico) |
| `voz_edge` / `velocidade_edge` | `pt-BR-AntonioNeural` (masc.), `pt-BR-FranciscaNeural` (fem.); velocidade `+0%`, `+10%`... |
| `efeito` | `ordis` (voz de Cephalon: metálica, rádio, gaguejo digital — efeito próprio, não é clone) ou `nenhum` |
| `ordis_metal` / `ordis_glitch` | Intensidade do metálico (0–1, padrão 0,35) e chance de gaguejo por frase (0–1, padrão 0,3) |
| `tom_edge` | Tom da voz Edge, ex.: `-5Hz`, `+0Hz`, `+5Hz` |
| `som_espera` / `volume_disco` | Enquanto o Mac pensa: frase curta + som de HD girando (`false` desliga; volume 0–1) |
| `frases_espera` | Lista de frases de espera (uma é sorteada a cada pergunta) |
| `voz` / `velocidade_voz` | Voz do Kokoro (reserva): `pm_alex`, `pm_santa`, `pf_dora` |
| `salvar_gravacao` | Salva sua última fala em `ultima_gravacao.wav` (para conferir o microfone) |
| `modo` | `voz` (resposta curta, falada) ou `texto` (resposta completa) |
| `janela_segundos` | Some a janela depois de N segundos parada (0 = nunca) |

## Transcrição ruim?

Ouça `ultima_gravacao.wav`. Se estiver baixo, chiado ou cortado, o problema é o microfone (escolha o certo em *Configurações → Som → Entrada* do Windows e aumente o volume). Fale só depois de apertar F9 e solte só depois de terminar.
