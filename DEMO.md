# anker-mini — Demo Walkthrough

A 5-minute demo suitable for showing to other AI-Operator / AIOS users
(LYAI pilot testers, AI Operator Bootcamp attendees, anyone who wants a
local skill scheduler).

## What you're showing

A lean owner-path alternative to cloud-hosted AIOS stacks:
- Markdown skills (same frontmatter pattern as e.g. Nick Milo's AIOS)
- Scheduling via `launchctl` — cron in the filesystem, no cloud state
- `claude -p` as the skill executor — works anywhere Claude Code is installed
- No external database, no GraphRAG, no frontend dependency
- ~950 lines of Python total

## 90-second setup

```bash
git clone https://github.com/pyjoku/anker-mini ~/projects/anker-mini
cd ~/projects/anker-mini
cp .env.example .env
$EDITOR .env  # set TELEGRAM_BOT_TOKEN, SKILL_PATHS
uv sync
./scripts/install_bot.sh
```

The bot now runs as a macOS LaunchAgent (`com.anker.mini`). Logs in
`~/Library/Logs/anker-mini/bot.log`.

## Telegram walkthrough

**1. Status check:**
```
You: /start
Bot: anker-mini online.
     Skills discovered: 15
     Active schedules: 0
     Commands: /skills /run /schedule /schedules /unschedule
```

**2. List skills:**
```
You: /skills
Bot: Available skills:
     • daily-brief — daily brief with calendar + mail
     • pre-planner — break an activity into time blocks ...
     • weekly-review
     ... (more)
```

**3. Run a skill ad-hoc:**
```
You: /run pre-planner when do I have to leave for the dentist at 14:30 in Lindau
Bot: ⏳ Starting pre-planner …
Bot: pre-planner — ✅ done
```
(Behind the scenes: `claude -p "when do I have to leave for the dentist at 14:30 in Lindau"`
is invoked from the configured working directory; output goes to
`~/Library/Logs/anker-mini/pre-planner.log`.)

**4. Preview a schedule (safe — no install):**
```
You: /preview daily-brief 05:55 mo-fr
Bot: ```xml
     <?xml version="1.0" ...
     ... full plist that would be installed ...
     ```
```

**5. Install a schedule:**
```
You: /schedule daily-brief 05:55 mo-fr
Bot: ✅ anker_cron set in daily-brief.md: 05:55 mo-fr
     Reconcile: +1 ~0 -0
```

In the filesystem you now have a real launchd plist:
`~/Library/LaunchAgents/com.anker.skill-daily-brief-a3f7e2c1.plist`.
Apple's launchd takes over from here — no scheduler daemon of our own.

**6. View the schedule's log (after first run):**
```
You: /logs daily-brief 20
Bot: daily-brief last 20 lines:
     === daily-brief @ 2026-05-12T05:55:01 ===
     prompt: daily brief
     ... claude -p output ...
     === exit 0 ===
```

## Natural-language scheduling

`/schedule` accepts free-text descriptions and falls back to an AI normalizer
(`claude -p` with a strict format prompt) if the strict parser doesn't recognize
the input:

```
You: /schedule weekly-review every Sunday at 6pm
Bot: AI normalized: 'every Sunday at 6pm' → 18:00 so
     ✅ anker_cron set in weekly-review.md: 18:00 so
```

## CLI alternative (no Telegram needed)

```bash
anker-mini-cli skills
anker-mini-cli run pre-planner
anker-mini-cli schedule daily-brief "05:55 mo-fr"
anker-mini-cli schedules
anker-mini-cli unschedule a3f7e2c1
anker-mini-cli preview daily-brief "05:55 mo-fr"
anker-mini-cli verify-env
```

## macOS menubar (optional)

```bash
uv sync --extra mac
anker-mini-menu
```

Click ⚓ in the menu bar → Skills, Sources, Schedules, Vault, Bot — everything
in one place, native folder pickers, native input dialogs.

## What anker-mini deliberately doesn't do

- **No cloud state.** Schedules live in skill `.md` files + macOS launchd. Nothing in an Anthropic workspace, nothing in a third-party DB.
- **No memory layer.** anker-mini only executes — the skill (or Claude Code beneath it) is responsible for writing to the vault. Separation of concerns.
- **No own LLM binding.** `claude -p` is the bridge. Bring your own Claude Code. If you want a different stack: a three-line wrapper.
- **No skill-discovery magic.** Plain `glob *.md` over configured paths — you see exactly what it finds.
- **No frontend.** Telegram + CLI + menubar are enough. Want a web UI? Fork it or build `anker-mini-web`.

## Comparison to cloud-hosted AIOS

| | Cloud AIOS (e.g. LYAI on Cowork) | anker-mini |
|---|---|---|
| Skill format | Markdown with frontmatter | same pattern, compatible |
| Skill storage | Vault | vault + optional `~/.claude/skills/` |
| Scheduling | Cowork UI (cloud) | launchd plist / crontab (local) |
| Memory layer | Cowork-internal | none — skill + vault are responsible |
| Bootstrap | `me-builder` skill | (planned — same pattern, runs locally) |
| Vault write surface | Cowork raw file write | recommended: Obsidian CLI for consistency |
| LLM | Anthropic-only via Cowork | swappable via the `claude` CLI backend |

## The strategic point

**Owner path instead of cloud convenience.** With a cloud AIOS you rent
orchestration and scheduling. With anker-mini you own them. The tradeoff is UX
(no web frontend, Markdown-CLI setup instead of a click flow) against
sovereignty (no lock-in, everything local, everything inspectable).

You can have both: anker-mini and a cloud AIOS can share the same skill folder
because the frontmatter convention is identical. Use the cloud product for the
UI, anker-mini for robust local execution — and pull the plug on either at
any time.
