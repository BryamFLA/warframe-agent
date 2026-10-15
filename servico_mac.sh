#!/bin/bash
# Instala/remove a API do agente (e o bot do Telegram, se configurado) como serviços do macOS:
# iniciam sozinhos ao ligar o Mac e reiniciam se caírem.
# Uso: ./servico_mac.sh instalar | remover | status | log
DIR="$(cd "$(dirname "$0")" && pwd)"; LA="$HOME/Library/LaunchAgents"
PL="$LA/com.warframe.agent.plist"; PLB="$LA/com.warframe.telegram.plist"

plist() {  # label, log, programa e argumentos...
  local label="$1" log="$2"; shift 2
  local args=""; for a in "$@"; do args="$args<string>$a</string>"; done
  cat <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array>$args</array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Interactive</string>
  <key>EnvironmentVariables</key><dict><key>PYTHONUNBUFFERED</key><string>1</string></dict>
  <key>StandardOutPath</key><string>$DIR/cache/$log</string>
  <key>StandardErrorPath</key><string>$DIR/cache/$log</string>
</dict></plist>
PL
}

case "$1" in
instalar)
  mkdir -p "$LA" "$DIR/cache"
  plist com.warframe.agent api.log "$DIR/.venv/bin/uvicorn" api:app --host 0.0.0.0 --port 8765 > "$PL"
  launchctl unload "$PL" 2>/dev/null; launchctl load "$PL" && echo "API instalada (porta 8765)."
  if [ -f "$DIR/cache/telegram.json" ]; then
    plist com.warframe.telegram telegram.log "$DIR/.venv/bin/python" "$DIR/telegram_bot.py" > "$PLB"
    launchctl unload "$PLB" 2>/dev/null; launchctl load "$PLB" && echo "Bot do Telegram instalado."
  else
    echo "Bot do Telegram não configurado (rode: .venv/bin/python telegram_bot.py --configurar e depois instale de novo)."
  fi;;
remover)
  for p in "$PLB" "$PL"; do launchctl unload "$p" 2>/dev/null; rm -f "$p"; done; echo "Serviços removidos.";;
status)
  launchctl list | grep -E "com.warframe.(agent|telegram)" || echo "nenhum serviço rodando"
  curl -s -m 5 localhost:8765/health; echo;;
log)
  tail -n 30 "$DIR/cache/api.log" "$DIR/cache/telegram.log" 2>/dev/null;;
*) echo "Uso: $0 instalar|remover|status|log";;
esac
