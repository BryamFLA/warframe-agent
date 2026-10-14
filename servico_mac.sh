#!/bin/bash
# Instala/remove a API do agente como serviço do macOS (inicia sozinha ao ligar o Mac).
# Uso: ./servico_mac.sh instalar | remover | status
DIR="$(cd "$(dirname "$0")" && pwd)"; PL="$HOME/Library/LaunchAgents/com.warframe.agent.plist"
case "$1" in
instalar)
cat > "$PL" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.warframe.agent</string>
  <key>ProgramArguments</key><array>
    <string>$DIR/.venv/bin/uvicorn</string><string>api:app</string>
    <string>--host</string><string>0.0.0.0</string><string>--port</string><string>8765</string></array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardOutPath</key><string>$DIR/cache/api.log</string>
  <key>StandardErrorPath</key><string>$DIR/cache/api.log</string>
</dict></plist>
PL
launchctl unload "$PL" 2>/dev/null; launchctl load "$PL" && echo "Serviço instalado. Chave da API: $(cat "$DIR/cache/api_key.txt" 2>/dev/null || echo 'gerada no 1º start')";;
remover) launchctl unload "$PL" 2>/dev/null; rm -f "$PL"; echo "Serviço removido.";;
status) launchctl list | grep com.warframe.agent || echo "não está rodando"; curl -s -m 5 localhost:8765/health; echo;;
*) echo "Uso: $0 instalar|remover|status";;
esac
