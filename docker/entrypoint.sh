#!/usr/bin/env bash
# entrypoint.sh — boot the three sub-processes inside one container.
#   1. obsidian-headless `ob sync --continuous` against /vault
#   2. cron daemon (fires scheduled skills)
#   3. anker-mini Telegram bot (foreground — its lifetime keeps the container alive)
#
# All state lives under /state (volume-mounted). Skill output logs go to /state/logs/.
#
# If invoked with arguments (e.g. `docker compose run --rm anker-mini ob login`),
# those arguments are executed instead of the daemon stack. This is what makes
# one-shot setup commands work without spinning up cron/ob-sync/bot.
set -euo pipefail

# ---------- state layout ----------
mkdir -p /state/obsidian /state/ankermini /state/claude /state/logs

# Symlinks: tools expect ~/.obsidian-headless, ~/.ankermini, ~/.claude
ln -sfn /state/obsidian   /root/.obsidian-headless
ln -sfn /state/ankermini  /root/.ankermini
ln -sfn /state/claude     /root/.claude

# ---------- one-shot mode ----------
if [[ $# -gt 0 ]]; then
  exec "$@"
fi

# ---------- ob sync (continuous) ----------
if [[ -f /state/obsidian/auth_token && -n "${VAULT_NAME:-}" ]]; then
  echo "[entrypoint] starting ob sync --continuous (vault: $VAULT_NAME)"
  ( cd /vault && ob sync --continuous \
      >> /state/logs/ob-sync.log 2>&1 ) &
  OB_PID=$!
  echo "[entrypoint] ob sync pid=$OB_PID"
else
  echo "[entrypoint] WARN: skipping ob sync — login + sync-setup not yet done."
  echo "[entrypoint]       run:  docker compose exec anker-mini ob login"
  echo "[entrypoint]       and:  docker compose exec anker-mini ob sync-setup --vault <NAME> --path /vault"
fi

# ---------- cron daemon ----------
echo "[entrypoint] starting cron"
cron

# ---------- anker-mini Telegram bot (foreground) ----------
# If no token is configured, sleep so the container stays alive for `exec` commands.
if /app/.venv/bin/python -c "from code import config; print(config.bot_token())" >/dev/null 2>&1; then
  echo "[entrypoint] starting anker-mini Telegram bot (foreground)"
  exec /app/.venv/bin/python -m code.bot
else
  echo "[entrypoint] WARN: telegram.bot_token not set in /state/ankermini/config.json"
  echo "[entrypoint]       configure with:  docker compose exec anker-mini /app/.venv/bin/python -c \\"
  echo "[entrypoint]                            \"from code import config; config.set_telegram_token('xxxx:yyyy')\""
  echo "[entrypoint] container is up; tailing /dev/null to keep it alive for setup."
  exec tail -f /dev/null
fi
