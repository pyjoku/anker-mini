---
name: daily-brief
description: |
  Daily brief — reads today's calendars and inbox, writes an HTML-formatted
  daily-brief note into the vault. Designed to run before you wake.
  Output: AIOS/History/YYYY-MM-DD Daily Brief.md.
triggers:
  - daily brief
  - run my daily brief
  - generate today's brief
  - morning briefing
dependencies:
  - Google Calendar
  - Gmail
  - Obsidian CLI
created: 2026-05-11
status: Example
---

# Daily Brief (example skill)

Working document. Built before you wake. Annotated at your desk.

## Output

`AIOS/History/YYYY-MM-DD Daily Brief.md` in the vault. If a file already
exists for today: ask before overwriting, and preserve any prior remarks
under `# Prior Remarks` at the bottom.

## Inputs

Weight equally — read all before generating:

- **Calendar** (Google Calendar MCP):
  - your primary calendar
  - your work calendar(s)
  - any subscribed calendars you actually use
  - explicitly omit: other people's calendars and management calendars (unless asked)
- **Mail** (Gmail MCP, plus IMAP via himalaya if you have a non-Gmail account):
  - last 24 hours
  - filter newsletters via the `List-Unsubscribe` header
  - filter notifications via a sender whitelist
- **Weather** (optional): WebFetch a real source (e.g. weather.gov) — never
  estimate, never fabricate. Omit if no real source is available.

## Brief structure

```markdown
---
up: ["[[YYYY-MM-DD]]"]
created: YYYY-MM-DD
---

Today is **[Day] [Date], [Year].**

In [City], Low–High [L–H]°C. [Conditions].

## 🔥 Today's calendar
- [time] [event] (cal: [calendar name])

## 📬 Inbox status
- **Gmail** — [verdict]
  - Top 3-5 waiting threads with context
- **IMAP / other** — [verdict]
  - same

## ⚡ What you might be forgetting
- Time-sensitive items pulled from calendar + mail
- Projects with no activity in 3+ days

## 🧭 What's next
- 2-4 concrete actions for today
```

## Annotations (by the user during the day)

- `User: [remark]` — a note
- `{verb argument}` — action marker, e.g. `{draft email to Kim}`

## Edge cases

- No mail / calendar outage: note it, keep going.
- First run ever: skip "yesterday" references.
- Weekend / travel: same template.

## Voice

- Second-person for the opening line.
- Neutral and terse for lists and statuses.

---

*This is an example skill for anker-mini, modeled after the AIOS daily-brief
pattern. Customize before live use.*
