# Examples

Pre-built skill files you can drop into `~/.claude/skills/` or your
vault's skill folder.

| File | Purpose | Activation |
|---|---|---|
| `daily-brief.md` | Morning daily brief with calendar + mail | `/schedule daily-brief 05:55 mo-fr` |
| `weekly-review.md` | Sunday-evening weekly review from daily notes | `/schedule weekly-review 18:00 so` |

## Install

```bash
# Copy into your user skill directory
cp examples/daily-brief.md ~/.claude/skills/

# Or into your vault (if that's where your skills live):
cp examples/daily-brief.md "~/path/to/your/vault/AIOS/Skills/"
```

Make sure `SKILL_PATHS` in your `.env` includes that folder. The skill will
then show up in `/skills` and can be scheduled via `/schedule`.

## Building your own skills

Minimum frontmatter for an anker-mini-compatible skill:

```yaml
---
name: my-skill
description: What it does (one line).
triggers:
  - my trigger phrase
  - alternative phrasing
anker_cron: "07:00 daily"   # optional — adds a recurring schedule
---

# Skill body starts here ...
```

The first `triggers:` entry becomes the default prompt passed to `claude -p`
when the skill is run. You can also override it on `/run`:

```
/run my-skill use this prompt text instead
```

Plain-text Telegram messages to the bot are also scanned for trigger phrases
— if a phrase from any skill appears in the message, that skill is invoked
with the full message as the prompt.
