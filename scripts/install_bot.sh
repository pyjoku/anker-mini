#!/usr/bin/env bash
# install_bot.sh — installiert den anker-mini Telegram-Bot als macOS LaunchAgent.
# Idempotent — laeuft beliebig oft.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.anker.mini"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  echo "FEHLER: $PROJECT_DIR/.env fehlt. Lege es aus .env.example an."
  exit 1
fi

# Determine Python interpreter
if [[ -d "$PROJECT_DIR/.venv" ]]; then
  PY="$PROJECT_DIR/.venv/bin/python"
elif command -v uv >/dev/null 2>&1; then
  echo "Erstelle uv venv …"
  (cd "$PROJECT_DIR" && uv sync)
  PY="$PROJECT_DIR/.venv/bin/python"
else
  echo "FEHLER: weder .venv noch uv vorhanden. Installiere uv (https://docs.astral.sh/uv) oder lege ein .venv an."
  exit 1
fi

LOG_DIR="$HOME/Library/Logs/anker-mini"
mkdir -p "$LOG_DIR"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PY</string>
        <string>-m</string>
        <string>code.bot</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/bot.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/bot.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

UID_NUM="$(id -u)"
echo "Bootout (falls geladen) …"
launchctl bootout "gui/$UID_NUM" "$PLIST" 2>/dev/null || true
echo "Bootstrap …"
launchctl bootstrap "gui/$UID_NUM" "$PLIST"

echo ""
echo "✅ anker-mini Bot installiert."
echo "   Plist: $PLIST"
echo "   Log:   $LOG_DIR/bot.log"
echo ""
echo "Status pruefen: launchctl print gui/$UID_NUM/$LABEL"
echo "Stoppen:        launchctl bootout gui/$UID_NUM $PLIST"
