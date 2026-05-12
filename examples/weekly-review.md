---
name: weekly-review
description: |
  Weekly review — reads all daily notes from the last 7 days, summarizes
  what happened, lists open commitments, and suggests 3-5 focus points for
  the week ahead. Writes the result to
  Calendar/Reviews/YYYY-MM-DD Weekly Review.md.
triggers:
  - weekly review
  - run my weekly review
  - what happened this week
  - end-of-week recap
dependencies:
  - Obsidian CLI (for consistent markdown read + write)
created: 2026-05-11
status: Example
---

# Weekly Review (example skill)

Weekly review. Sunday evening or late Friday as a closing ritual.

## When to use

- **Scheduled:** typically Sun 18:00 or Fri 17:00 — `/schedule weekly-review 18:00 so`.
- **Ad-hoc:** when the week tips and you need re-orientation.

## Inputs

All from the vault, read via Obsidian CLI for markdown consistency:

- **Daily notes** for the last 7 days (`Calendar/Days/YYYY-MM-DD.md`)
- **Daily logs** for the last 7 days (`AIOS/History/YYYY-MM-DD Daily Log.md`)
- **Daily briefs** for the last 7 days — especially the `User:` annotations and `{action markers}`
- **Active projects** (`Efforts/Projects/Active/`) with their last-modified date
- **Open commitments** from prior briefs

## Output

`Calendar/Reviews/YYYY-MM-DD Weekly Review.md` — a note, not an email, not an
external store. Lives in the vault, linked to the daily notes.

## Structure

```markdown
---
up: ["[[Calendar/Reviews]]"]
period: YYYY-MM-DD to YYYY-MM-DD
created: YYYY-MM-DD
---

# Weekly Review — week XX

## 🎯 What happened
- [section for projects with movement]
- [section for human events]

## ✅ What got closed
- Concrete closures from daily logs, max 7-10 items

## ⏸ What stayed open
- Open commitments from prior briefs without closure
- Required: every item with a *"what's the next step"*

## 🔍 Patterns I see
- 2-3 observations across the week
- Energy, mood, recurring themes

## 🧭 Next week
- 3-5 focus points
- Required: each one with a first step + a day

## Footer
*Generated YYYY-MM-DD by anker-mini weekly-review skill.*
```

## Rules

- **Data from the vault, not from memory.** Never fabricate, never infer from generic patterns.
- **Quote user annotations.** `User: ...` bullets from daily briefs preserved verbatim.
- **Track action markers.** If `{schedule X for Tuesday}` was in a brief and didn't get done — it belongs under "What stayed open".
- **Pattern honesty.** *"You wrote three briefs in a row saying you wanted to schedule the workout block and didn't"* belongs here.
- **No sugar-coating.** If the week was dark, say so. No toxic optimism.

## Voice

- Second person, sober, direct-friendly.
- No coach-speak ("you've got this"). Observation + suggestion only.

## Edge cases

- **No daily notes available:** say "no PKM material found" + offer to write an open-questions list instead of a review.
- **Daily brief exists but is empty:** mark it as "no content", not as "nothing happened".
- **First run (no prior reviews):** no comparison section, just what the week showed.

## Activation

Manual:
```
/run weekly-review
```

Scheduled (every Sunday 18:00):
```
/schedule weekly-review 18:00 so
```

Or by editing the skill file directly and adding `anker_cron: "18:00 so"` to
the frontmatter (SSOT — the bot will pick it up on the next reconcile).

---

*Modeled after closing rituals in LYT and the daily-trident logic (human writes,
AI summarizes).*
