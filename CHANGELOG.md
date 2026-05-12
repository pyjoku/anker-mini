# Changelog

All notable changes to this project.

## [0.2.0] — 2026-05-12

Big pivot: skill `.md` frontmatter is now Single Source of Truth for scheduling.
Config moves to `~/.ankermini/config.json`. macOS menubar app shipped.

### Added
- **`anker_cron:` YAML frontmatter in skill files** is the SSOT. Format: `HH:MM <days>` (e.g. `"05:55 mo-fr"`). On bot startup and on `/reconcile`, the scheduler reads every skill's `anker_cron` and reconciles installed plist/cron entries: adds new ones, updates changed ones, removes orphans. `data/schedules.json` is now a cache, not the source.
- **`/sources`, `/addsource <path>`, `/removesource <path>`** — manage skill-source folders at runtime, no `.env` editing.
- **`/vault`, `/setvault <abs-path>`** — set a default vault root. `/addsource` then accepts vault-relative paths (e.g. `/addsource AIOS/Skills`).
- **`/reconcile`** — force a manual reconcile from skill files.
- **`/check <skill>`** — inspect a skill's frontmatter (triggers, description, body size).
- **Plain-text handler** — non-command messages are forwarded as `claude -p` prompts. If a skill trigger phrase is detected in the text, that skill is bound; otherwise it runs as a bare conversation. Bot is never silent.
- **AI fallback for schedule specs** — `/schedule daily-brief "jeden morgen um halb sieben unter der woche"` calls `claude -p` with a strict prompt to normalize to `HH:MM <days>`. Strict parser tries first; AI only on failure.
- **`code/menubar.py` — macOS menubar app** (rumps). `⚓` icon with submenus for Skills (Run / Schedule… / Remove schedule / Reveal source), Sources (Add… / Remove / Reveal in Finder, native folder picker), Schedules (with next-firing time), Vault (Change…), Bot (Start/Stop/Tail log). Long-running ops (`claude -p` AI normalize, `launchctl bootstrap`, reconcile) run in worker threads so the menu stays responsive. Native AppleScript dialog for text input.
- **`anker-mini-menu` entry point + `mac` extras** — `uv sync --extra mac` installs rumps + PyObjC.
- **Config migration** — first run migrates `.env` → `~/.ankermini/config.json` (token, paths, vault).

### Changed
- `pyproject.toml`: added `mac` optional dependency group and the `anker-mini-menu` script entry point.
- `bot.py`: `/schedule` now writes `anker_cron:` into the skill file and reconciles, instead of writing directly to schedules.json. `/unschedule <skill>` removes the YAML key.

### Fixed
- rumps `_notify` failures (missing `Info.plist` in `uv`-created venvs) no longer crash callbacks. Project README documents the `PlistBuddy -c 'Add :CFBundleIdentifier string "rumps"'` workaround.

## [0.1.0] — 2026-05-11

Initial release. Built during one focused morning session (06:44–11:00).

### Added
- **Telegram bot** (`code/bot.py`) with commands:
  - `/start`, `/help`
  - `/skills` — list discoverable skills
  - `/run <skill> [prompt]` — execute via `claude -p`
  - `/schedule <skill> <HH:MM> [days]` — create LaunchAgent
  - `/preview <skill> <HH:MM> [days]` — show plist without installing
  - `/schedules` — list active schedules (with next-firing time)
  - `/unschedule <id>` — remove a schedule
  - `/logs <skill> [n]` — show tail of skill output log
  - `/check <skill>` — validate frontmatter and body
  - Optional Whitelist via `TELEGRAM_ALLOWED_USERS`
- **CLI** (`code/cli.py` → `anker-mini-cli`) with the same surface as the bot, for headless setup.
- **Skill discovery** (`code/skill_runner.py`) — `*.md` files in configured paths, YAML frontmatter parsed for `name`, `description`, `triggers`. Supports `description: |` literal blocks.
- **Skill execution** via `subprocess.run(["claude", "-p", prompt])` from configured working directory; output redirected to per-skill log file.
- **Scheduler** (`code/scheduler.py`) — macOS launchd plist generation with `StartCalendarInterval`, supports daily / single weekday / weekday range / weekday list. `data/schedules.json` is the source of truth.
- **Install script** (`scripts/install_bot.sh`) — sets up `com.anker.mini` LaunchAgent.
- **Example skill** (`examples/daily-brief.md`) — Nick-Milo-pattern daily brief with Jochen's calendar set.
- **Tests** (`tests/test_smoke.py`) — 17 unittest cases covering parser, plist gen (round-trips through `plistlib`), frontmatter (incl. literal blocks), and discovery.
- **Docs:** `README.md`, `DEMO.md` (5-min walkthrough for demos), `LICENSE` (MIT).

### Added (continued)
- **Linux scheduling backend** — `crontab` based, auto-dispatched via `platform.system()`. macOS keeps using launchd. Cron line: `MM HH * * <DAYS> cd <cwd> && claude -p '<prompt>' >> <log> 2>&1  # ANKER_MINI[<id>]`. ISO weekday 7 (Sun) gets remapped to cron 0.
- **`anker-mini-cli verify-env`** — sanity-checks the .env + runtime: token, whitelist, skill paths, skill count, claude CLI presence, CLAUDE_CWD, platform backend (launchctl/crontab), log dir writable. Returns exit code 1 on any FAIL.
- **`examples/weekly-review.md`** — second example skill, models a Sunday-evening review reading Daily Notes + Daily Logs + Daily Briefs from the past 7 days, writes to `Calendar/Reviews/`.

### Not yet
- Windows Task Scheduler backend (Backlog).
- Frontmatter-driven `schedule:` field (auto-register schedules from skill files).
- Obsidian-CLI vault writes from within skills (recommended pattern, not enforced).
- Pre-Planner / Daily-Brief as built-in commands (kept external as skills).
