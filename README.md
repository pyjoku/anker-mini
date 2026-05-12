# anker-mini

![tests](https://github.com/pyjoku/anker-mini/actions/workflows/test.yml/badge.svg) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Stripped-down Telegram bot and skill scheduler. Discovers Markdown skills on
your filesystem, runs them via `claude -p`, and schedules them as macOS
LaunchAgents or Linux cron jobs — no database, no GraphRAG, no frontend.

Stack: Python 3.11+, `python-telegram-bot` v21+, `launchd` / `crontab`, the
`claude` CLI.

## What it does

| Command | Action |
|---|---|
| `/skills` | List all discovered skills |
| `/sources`, `/addsource <path>`, `/removesource <path>` | Manage skill source folders at runtime |
| `/vault`, `/setvault <abs-path>` | Set a default vault root (then `/addsource` accepts vault-relative paths) |
| `/run <skill> [prompt]` | Run a skill once via `claude -p` |
| `/schedule <skill> <spec>` | Write `anker_cron:` into the skill file and reconcile (natural language OK — AI fallback) |
| `/preview <skill> <spec>` | Show the plist that would be generated, without installing it |
| `/schedules` | List active schedules with their next firing time |
| `/unschedule <skill>` | Remove `anker_cron:` from the skill file and reconcile |
| `/reconcile` | Manual reconcile from skill YAML to installed schedules |
| `/logs <skill> [n]` | Tail the skill's output log |
| `/check <skill>` | Validate frontmatter, triggers, body |
| _(plain text)_ | Forwarded to `claude -p` as a prompt, with skill-trigger detection |

## SSOT — skill files drive schedules

`anker_cron:` in YAML frontmatter is the source of truth for scheduling. On
bot startup (and on `/reconcile`), the scheduler reads every skill, compares
to currently installed LaunchAgents, and adds / updates / removes as needed.

```yaml
---
name: daily-brief
triggers:
  - daily brief
anker_cron: "05:55 mo-fr"      # ← installs itself automatically
---
```

You can edit this line directly in Obsidian. It takes effect on the next bot
start or `/reconcile`.

Day specs: `daily`, single days (`mo,di,fr`), ranges (`mo-fr`). German and
English weekday names are both accepted (`mo`/`mon`, `di`/`tue`, …).

## Install

```bash
git clone https://github.com/pyjoku/anker-mini.git ~/projects/anker-mini
cd ~/projects/anker-mini
cp .env.example .env
$EDITOR .env          # TELEGRAM_BOT_TOKEN, allowed users, skill paths
uv sync               # or: python -m venv .venv && pip install -e .
./scripts/install_bot.sh
```

The bot runs as a LaunchAgent `com.anker.mini` — auto-start, keep-alive.
Logs in `~/Library/Logs/anker-mini/bot.log`.

On first run, settings from `.env` are migrated into
`~/.ankermini/config.json`. After that the JSON file is the canonical config
location.

## macOS menubar (optional)

```bash
uv sync --extra mac          # installs rumps + PyObjC
anker-mini-menu              # launches the ⚓ menubar app
```

Menu structure: **Skills** (each skill → Run now / Schedule… / Remove schedule),
**Sources** (Add… via native folder picker), **Schedules** (with next-run
time), **Vault** (Change…), **Bot** (Start / Stop / Tail log). Reconcile is in
the Schedules submenu.

**Known quirk:** `rumps.notification` fails on `uv`-created venvs that lack an
`Info.plist`. One-time fix:

```bash
/usr/libexec/PlistBuddy -c 'Add :CFBundleIdentifier string "rumps"' .venv/bin/Info.plist
```

## CLI alternative

For headless setup, scripting, or when Telegram is not configured:

```bash
anker-mini-cli skills
anker-mini-cli run pre-planner
anker-mini-cli schedule daily-brief "05:55 mo-fr"
anker-mini-cli preview daily-brief "05:55 mo-fr"
anker-mini-cli schedules
anker-mini-cli unschedule <id-prefix>
anker-mini-cli reinstall    # re-generate all schedule artefacts from state
anker-mini-cli verify-env   # check token, skills, claude CLI, backend
```

**Tip:** after editing `.env`, always run `anker-mini-cli verify-env` — it
reports any FAILs (missing bot token, missing `claude` CLI, etc.) and WARNs
(open whitelist) before you start the bot.

## .env variables

| Variable | Meaning | Required |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | ✅ |
| `TELEGRAM_ALLOWED_USERS` | Comma-separated user IDs (whitelist). Empty = open (dev only) | ⚠️ recommended |
| `SKILL_PATHS` | Colon-separated absolute paths to folders of `*.md` skills | ✅ |
| `CLAUDE_CWD` | Working directory for `claude -p` (where CLAUDE.md lives) | ✅ |
| `CLAUDE_BIN` | Path to the `claude` CLI | default: `claude` |
| `LOG_DIR` | Where skill logs go | default: `~/Library/Logs/anker-mini` |

## Skill format

A skill is a `.md` file with YAML frontmatter — compatible with the same
pattern used by e.g. Nick Milo's AIOS:

```yaml
---
name: pre-planner
description: |
  Break an activity into time blocks, compute a departure time via forward
  + backward + sum cross-check ...
triggers:
  - when do I have to leave
  - pre-planner
anker_cron: "07:00 mo-fr"     # optional — schedules the skill
---

# Pre-Planner

... skill body ...
```

- `name` (defaults to the filename without `.md`) → used as the skill ID.
- `description` → shown in `/skills` listings.
- `triggers` → the first entry is the default prompt passed to `claude -p`;
  any of them, if found in plain-text Telegram messages, will fire the skill.
- `anker_cron` (optional) → installs a recurring schedule. Format `HH:MM <days>`.

## Architecture

```
anker-mini/
├── code/
│   ├── bot.py           Telegram bot (commands + plain-text handler)
│   ├── menubar.py       macOS menubar app (rumps)
│   ├── cli.py           local CLI (anker-mini-cli)
│   ├── scheduler.py     Platform-dispatched scheduling (launchd / crontab)
│   ├── skill_runner.py  Skill discovery + claude -p invocation
│   └── config.py        ~/.ankermini/config.json loader
├── scripts/
│   └── install_bot.sh   Installs the bot as a LaunchAgent
├── examples/            Example skills (daily-brief, weekly-review)
├── tests/               unittest suite (23 cases)
└── pyproject.toml
```

State files:

| File | Role |
|---|---|
| Skill `.md` files (`anker_cron:` field) | Source of truth for scheduling |
| `~/.ankermini/config.json` | Telegram token, allowed users, skill paths, vault, claude config |
| `~/.ankermini/schedules.json` | Cache of currently installed schedules |
| `~/Library/LaunchAgents/com.anker.skill-*.plist` | macOS backend artefacts |
| user crontab (entries marked `# ANKER_MINI[<id>]`) | Linux backend artefacts |

If state and backend artefacts drift: `anker-mini-cli reinstall` rebuilds the
backend from `schedules.json`; `/reconcile` rebuilds both from skill files.

## Platform support

- **macOS:** fully supported. Schedules install as
  `~/Library/LaunchAgents/com.anker.skill-*.plist` and load via
  `launchctl bootstrap`.
- **Linux:** supported. Schedules go into the user `crontab` with an
  `# ANKER_MINI[<id>]` marker.
- **Windows:** the bot runs, but the scheduler backend (Task Scheduler
  integration) is not implemented yet — backlog.

Backend dispatch lives in `code/scheduler.py` and keys on `platform.system()`.

## Troubleshooting

Run `anker-mini-cli verify-env` first — it catches most setup problems.

| Symptom | Likely cause | Fix |
|---|---|---|
| Bot does not start / Telegram silent | `TELEGRAM_BOT_TOKEN` missing or wrong | Re-issue with @BotFather, paste into `.env` |
| `/start` replies "access denied" | You're not in `TELEGRAM_ALLOWED_USERS` | Get your user ID via @userinfobot, add to `.env` |
| `/skills` shows empty list | `SKILL_PATHS` empty or wrong | Verify paths — colon-separated, absolute, containing `*.md` files |
| `/run` hangs or errors | `claude` CLI not on PATH | `which claude`; set `CLAUDE_BIN` in `.env` if needed |
| `/schedule` succeeds but the skill never fires | macOS: app sandbox blocks it; Linux: user crontab disabled | macOS: grant Full-Disk-Access to Terminal; Linux: verify `crontab -l` works |
| `launchctl bootstrap` returns error 5 or 78 | Already loaded, or no GUI session | `bootout` first, or run inside a GUI session (not SSH-only) |
| `~/.ankermini/schedules.json` out of sync with installed artefacts | An artefact was hand-deleted | `anker-mini-cli reinstall` — regenerates everything from state |
| `rumps.notification` crashes | venv missing `Info.plist` | Apply the `PlistBuddy` fix shown in the menubar section above |
| LaunchAgent loaded but skill never fires | The `StartCalendarInterval` trigger hasn't fired yet | `launchctl print gui/$(id -u)/<label>` shows the next trigger time |
| Skill output doesn't land in the vault | The skill body writes raw files instead of using Obsidian CLI | Edit the skill so its output path is explicit, preferably via Obsidian CLI |

## Security

- Always set `TELEGRAM_ALLOWED_USERS` outside dev.
- Running a skill via `claude -p` means anything `claude` can do, the bot can
  trigger — file writes, Bash, MCP calls. Whitelist is mandatory.
- `~/.ankermini/config.json` holds your bot token in plaintext (`chmod 600`).
  Don't commit it. The first-run migration may leave a `.env` in the project
  root; that file is gitignored — keep it that way or delete it once
  `config.json` is established.

## Where this fits — vs. cloud-based AIOS patterns

anker-mini is built as a lean owner-path counterpoint to cloud-hosted AI
operating systems (e.g. Nick Milo's AIOS on Anthropic's Cowork):

- Skills stay as Markdown files in your own filesystem — portable.
- Scheduling lives in the skill file itself (`anker_cron:`), not in a vendor UI.
- No cloud state, no proprietary workspace — everything is local.
- Vault writes should go through Obsidian CLI from inside skills, to keep
  Markdown formatting consistent.

If your daily workflow already runs through Claude Code locally, anker-mini
gives you the missing scheduler + Telegram surface without adding any new
moving parts.
