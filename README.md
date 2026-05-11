# anker-mini

Stripped-down Telegram-Bot + Skill-Scheduler. Findet Markdown-Skills im
Filesystem, fuehrt sie ueber `claude -p` aus, und kann sie ueber Telegram-Befehle
als macOS LaunchAgents schedulen — ohne zusaetzliche Datenbank, ohne GraphRAG,
ohne Frontend.

Stack: Python 3.11+, `python-telegram-bot` v21+, `launchd`, `claude` CLI.

## Was es kann

| Befehl | Tut |
|---|---|
| `/skills` | Listet alle gefundenen Skills (aus `SKILL_PATHS`) |
| `/run <skill> [prompt]` | Fuehrt einen Skill sofort via `claude -p` aus |
| `/schedule <skill> <HH:MM> [days]` | Legt LaunchAgent an (z.B. `daily-brief 05:55 mo-fr`) |
| `/preview <skill> <HH:MM> [days]` | Zeigt die plist die generiert wuerde — ohne zu installieren |
| `/schedules` | Listet aktive Schedules |
| `/unschedule <id>` | Entfernt Schedule + LaunchAgent |
| `/logs <skill> [n]` | Zeigt die letzten N Zeilen aus dem Skill-Output-Log |

Tagesangaben: `daily`, einzelne (`mo,di,fr`), Bereich (`mo-fr`).

## Installation

```bash
git clone <repo> ~/projects/anker-mini
cd ~/projects/anker-mini
cp .env.example .env
$EDITOR .env          # TELEGRAM_BOT_TOKEN, allowed users, skill paths
uv sync               # oder: python -m venv .venv && pip install -e .
./scripts/install_bot.sh
```

Der Bot laeuft danach als LaunchAgent `com.anker.mini` — auto-start, keep-alive.
Logs in `~/Library/Logs/anker-mini/bot.log`.

## CLI-Alternative

Falls Telegram nicht eingerichtet ist (oder fuer Setup-Skripte):

```bash
anker-mini-cli skills
anker-mini-cli run pre-planner
anker-mini-cli schedule daily-brief "05:55 mo-fr"
anker-mini-cli preview daily-brief "05:55 mo-fr"
anker-mini-cli schedules
anker-mini-cli unschedule <id-prefix>
anker-mini-cli reinstall    # alle plists aus schedules.json neu generieren
```

## .env Variablen

| Variable | Bedeutung | Pflicht |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot-Token vom @BotFather | ✅ |
| `TELEGRAM_ALLOWED_USERS` | Komma-getrennte User-IDs (Whitelist). Leer = offen (dev only) | ⚠️ empfohlen |
| `SKILL_PATHS` | Doppelpunkt-getrennte absolute Pfade mit `*.md` Skill-Files | ✅ |
| `CLAUDE_CWD` | Working Directory fuer `claude -p` (wo CLAUDE.md liegt) | ✅ |
| `CLAUDE_BIN` | Pfad zur `claude` CLI | default: `claude` |
| `LOG_DIR` | Wo Skill-Logs landen | default: `~/Library/Logs/anker-mini` |

## Skill-Format

Jeder Skill ist eine `.md` mit YAML-Frontmatter — kompatibel mit dem Pattern,
das z.B. Nick Milos AIOS und Jochens Anker-Vault nutzen:

```yaml
---
name: pre-planner
description: |
  Zerlegt eine Aktivitaet in Zeitbloecke ...
triggers:
  - wann muss ich los
  - pre-planner
---

# Pre-Planner

... Skill-Inhalt ...
```

- `name` (default: filename ohne `.md`) → wird als Skill-ID verwendet.
- `description` (erste Zeile) → erscheint im `/skills` Listing.
- `triggers` → erster Eintrag wird zum Default-Prompt fuer `claude -p`.

## Architektur

```
anker-mini/
├── code/
│   ├── bot.py           Telegram-Bot (commands)
│   ├── scheduler.py     Plist-Generierung, launchctl bootstrap/bootout
│   ├── skill_runner.py  Skill-Discovery + claude -p Aufruf
│   └── config.py        .env-Loader
├── scripts/
│   └── install_bot.sh   Setzt com.anker.mini als LaunchAgent
├── data/
│   └── schedules.json   Source of Truth — Plists werden hieraus generiert
└── pyproject.toml
```

State: `data/schedules.json` ist Single Source of Truth. Plists werden
deterministisch daraus generiert. Bei Setup-Verlust:
`python -c "from code.scheduler import reinstall_all; reinstall_all()"`.

## Plattform

- **macOS:** voll unterstuetzt (launchd).
- **Linux/Windows:** Bot laeuft, aber `/schedule` und `/unschedule` fehlt
  System-Layer (cron / Task Scheduler). Hinzufuegen waere mechanisch — Backlog.

## Sicherheit

- `TELEGRAM_ALLOWED_USERS` immer setzen ausserhalb von Dev.
- Skill-Execution per `claude -p` heisst: alles was `claude` kann, kann der Bot ausloesen — File-Schreiben, Bash, MCPs. Daher Whitelist Pflicht.
- `.env` ist gitignored; nicht committen, nicht zippen ohne Verschluesselung (siehe `anker-mini-secrets` falls verfuegbar).

## Demo / Vergleich mit Nicks AIOS

anker-mini ist als **schlanker Owner-Pfad-Counter-Punkt** zu Nicks AIOS gebaut:
- Skills bleiben Markdown → portable
- Scheduling im Skill-File (Frontmatter `schedule:`) → zukuenftige Erweiterung
- Kein Cowork, kein Cloud-State, alles lokal
- Vault-Schreiben empfohlen via Obsidian CLI (`obsidian write:note ...` aus dem
  Skill heraus) statt rohes File-Writing — sichert Markdown-Konsistenz
