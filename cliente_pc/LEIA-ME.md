# Assistente de voz — PC do jogo (Windows)

Segure **F9**, fale a pergunta, solte. O PC transcreve sua voz, pergunta ao agente que roda no **Mac mini** e responde em voz (masculina, `pm_alex`) enquanto mostra o texto numa janela por cima do jogo. **F10** mostra/esconde a janela. A placa de vídeo fica livre para o jogo: transcrição e voz rodam no processador.

## Instalar (uma vez)

1. Instale o **Python 3.12** em python.org (marque *Add python.exe to PATH*).
2. Copie esta pasta `cliente_pc` para o PC (ex.: `C:\WarframeVoz`).
3. Dê dois cliques em **`instalar.bat`** (baixa ~600 MB: bibliotecas, voz Kokoro e, no 1º uso, o modelo de transcrição).
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
| `whisper_modelo` | `small` (rápido, padrão) ou `medium` (mais preciso, mais lento) |
| `whisper_device` | `cpu` (padrão, não pesa no jogo) ou `cuda` (placa NVIDIA; precisa das libs CUDA 12) |
| `voz` / `velocidade_voz` | `pm_alex`, `pm_santa` (masculinas), `pf_dora` (feminina) |
| `modo` | `voz` (resposta curta, falada) ou `texto` (resposta completa) |
| `janela_segundos` | Some a janela depois de N segundos parada (0 = nunca) |
