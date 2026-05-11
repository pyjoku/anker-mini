# Changelog

All notable changes to this project.

## [0.1.0] — 2026-05-11

Initial release. Built during one focused morning session (06:44–11:00).

### Added
- **Telegram bot** (`code/bot.py`) with commands:
  - `/start`, `/help`
  - `/skills` — list discoverable skills
  - `/run <skill> [prompt]` — execute via `claude -p`
  - `/schedule <skill> <HH:MM> [days]` — create LaunchAgent
  - `/preview <skill> <HH:MM> [days]` — show plist without installing
  - `/schedules` — list active schedules
  - `/unschedule <id>` — remove a schedule
  - `/logs <skill> [n]` — show tail of skill output log
  - Optional Whitelist via `TELEGRAM_ALLOWED_USERS`
- **CLI** (`code/cli.py` → `anker-mini-cli`) with the same surface as the bot, for headless setup.
- **Skill discovery** (`code/skill_runner.py`) — `*.md` files in configured paths, YAML frontmatter parsed for `name`, `description`, `triggers`. Supports `description: |` literal blocks.
- **Skill execution** via `subprocess.run(["claude", "-p", prompt])` from configured working directory; output redirected to per-skill log file.
- **Scheduler** (`code/scheduler.py`) — macOS launchd plist generation with `StartCalendarInterval`, supports daily / single weekday / weekday range / weekday list. `data/schedules.json` is the source of truth.
- **Install script** (`scripts/install_bot.sh`) — sets up `com.anker.mini` LaunchAgent.
- **Example skill** (`examples/daily-brief.md`) — Nick-Milo-pattern daily brief with Jochen's calendar set.
- **Tests** (`tests/test_smoke.py`) — 17 unittest cases covering parser, plist gen (round-trips through `plistlib`), frontmatter (incl. literal blocks), and discovery.
- **Docs:** `README.md`, `DEMO.md` (5-min walkthrough for demos), `LICENSE` (MIT).

### Not yet
- Linux/Windows scheduling backends (Backlog).
- Frontmatter-driven `schedule:` field (auto-register schedules from skill files).
- Obsidian-CLI vault writes from within skills (recommended pattern, not enforced).
- Pre-Planner / Daily-Brief as built-in commands (kept external as skills).
