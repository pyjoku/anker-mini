# anker-mini in Docker — 24/7 Obsidian automation

This sets up an unattended container that:

1. Keeps an Obsidian vault in continuous bidirectional sync via `obsidian-headless`.
2. Runs the anker-mini Telegram bot.
3. Fires scheduled skills via cron, talking to `claude -p`.

The whole thing fits in **one container**, ~500 MB image, ~150 MB RAM at idle.
Works on Docker Desktop (Mac, Windows, Linux) and on any Linux VPS with Docker.

## Prerequisites

- Docker + Docker Compose
- An **Obsidian Sync** subscription (the vault transport)
- A **Telegram bot token** from [@BotFather](https://t.me/botfather)
- A **Claude Code** account (OAuth or API key)

## Setup (one-time, ~5 minutes)

```bash
cd anker-mini/docker
cp .env.example .env
$EDITOR .env                       # set VAULT_NAME, VAULT_HOST_PATH, TZ
docker compose build
```

### 1. Authenticate Obsidian Sync

```bash
docker compose run --rm anker-mini ob login
```

Enter email + password + (optional) MFA. The auth token persists in the `state` volume.

```bash
docker compose run --rm anker-mini ob sync-list-remote
```

Pick a vault name. Then set up the sync target — this prompts for your E2E
encryption password (the one you set up in Obsidian Sync the first time):

```bash
docker compose run --rm anker-mini \
  ob sync-setup --vault "$VAULT_NAME" --path /vault --device-name "anker-mini-docker"
```

### 2. Authenticate Claude Code

Easiest: log in once on your Mac via `claude login`, then copy the credentials
into the state volume:

```bash
docker run --rm -v anker-mini_state:/state -v ~/.claude:/host-claude:ro alpine \
  sh -c "mkdir -p /state/claude && cp -R /host-claude/. /state/claude/"
```

(Alternative: use an Anthropic API key via env var — see "API key mode" below.)

### 3. Configure the Telegram bot + skill paths

```bash
docker compose run --rm anker-mini /app/.venv/bin/python -c "
from code import config
config.set_telegram_token('123456:abcdef...')
config.set_allowed_users([123456789])               # your Telegram user ID
config.add_user_skill_path('/vault/AIOS/Skills')    # or wherever your skills live
"
```

### 4. Bring it up

```bash
docker compose up -d
docker compose logs -f
```

You should see:
```
[entrypoint] starting ob sync --continuous (vault: My Vault)
[entrypoint] starting cron
[entrypoint] starting anker-mini Telegram bot (foreground)
anker-mini started
startup reconcile: +0 ~0 -0
```

The Telegram bot is now polling. Send `/start` to your bot to confirm.

## Day-to-day operations

```bash
# Container status
docker compose ps

# Live logs (Ctrl-C to detach)
docker compose logs -f

# Get a shell inside
docker compose exec anker-mini bash

# Run anker-mini-cli inside
docker compose exec anker-mini /app/.venv/bin/python -m code.cli skills
docker compose exec anker-mini /app/.venv/bin/python -m code.cli verify-env

# Force a re-sync
docker compose exec anker-mini ob sync

# Restart everything
docker compose restart

# Stop (state persists in volumes)
docker compose down

# Nuke state (CAREFUL — clears auth tokens, schedules, logs; vault stays)
docker compose down -v
```

## Architecture

```
┌─ Docker container (anker-mini) ──────────────────────────┐
│                                                          │
│  ob sync --continuous ──────► /vault ◄── cron ──► claude │
│         ▲ ▼                                              │
│  Obsidian Sync                                           │
│  (E2E encrypted)                                         │
│         ▲ ▼                                              │
└─────────┼────────────────────────────────────────────────┘
          ▼
   Your Mac (Obsidian Desktop) — same vault, kept in sync.
```

- **`/vault`** is a bind-mount → you can browse it in Finder, or it can be
  a named volume for stricter isolation.
- **`/state/`** holds: `obsidian/` (auth token + sync config),
  `ankermini/` (Telegram + skill config + schedules), `claude/` (OAuth tokens),
  `logs/` (per-skill output logs).
- **One container, three processes** managed by `tini`: the Telegram bot stays
  in foreground; ob sync and cron run in background. If the bot dies, the
  whole container restarts (Docker policy `unless-stopped`).

## Deploying to a Hetzner VPS

Once it works locally on Docker Desktop, moving to a VPS is the same compose
file:

```bash
# On the VPS (Ubuntu 24.04 with docker installed)
git clone https://github.com/pyjoku/anker-mini.git
cd anker-mini/docker
cp .env.example .env
$EDITOR .env
docker compose build
# repeat the auth steps above
docker compose up -d
```

The container is happy with ~150 MB RAM at idle. A Hetzner CX22 (€4.51/mo,
2 vCPU, 4 GB RAM) has plenty of headroom for this plus other small services.

## API-key mode (alternative to Claude OAuth)

If you'd rather use an Anthropic API key instead of copying OAuth tokens:

```bash
# Add to docker/.env
ANTHROPIC_API_KEY=sk-ant-...
```

…and adjust `docker-compose.yml` to pass it through:

```yaml
environment:
  ...
  ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
```

`claude` will use it transparently. Trade-off: API-key usage is billed
per-request (no Pro plan included).

## Troubleshooting

| Symptom | Check |
|---|---|
| `ob sync` says "Failed to validate password" | E2E encryption password is wrong (different from login password). Reset via Obsidian Sync settings. |
| Bot doesn't reply | `docker compose logs -f` — usually missing token or wrong skill paths |
| Skills don't fire on schedule | `docker compose exec anker-mini crontab -l` — entries should match active `anker_cron:` |
| Sync conflicts | The default merge strategy keeps both versions. Inspect `Conflicts/` in your vault. |
| Container restart-looping | `docker compose logs --tail 100` — usually a syntax error in `anker_cron` somewhere |

## Backup

The container holds two things that aren't elsewhere:

1. **State volume** — Obsidian auth token, anker-mini config, schedules. Back up:
   ```bash
   docker run --rm -v anker-mini_state:/state -v $PWD:/backup alpine \
     tar czf /backup/anker-mini-state-$(date +%F).tar.gz -C /state .
   ```
2. **Vault** — covered by Obsidian Sync's history + whatever you do on your Mac.
