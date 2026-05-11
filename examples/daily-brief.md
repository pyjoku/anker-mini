---
name: daily-brief
description: |
  Tagesbrief — liest die Kalender und Mails des Tages, schreibt eine
  HTML-formatierte Daily-Brief-Note in den Vault. Soll morgens vor dem Wachwerden
  durchlaufen. Output: AIOS/History/YYYY-MM-DD Daily Brief.md.
triggers:
  - daily brief
  - run my daily brief
  - generate today's brief
  - was passiert heute
  - tagesbrief
  - morgens-briefing
dependencies:
  - Google Calendar
  - Gmail
  - Obsidian CLI
created: 2026-05-11
status: Example
---

# Daily Brief (Example Skill)

Working document. Built before you wake. Annotated at your desk.

## Output

`AIOS/History/YYYY-MM-DD Daily Brief.md` im Vault. Wenn vorhandene Datei
existiert: vor dem Ueberschreiben fragen, prior remarks unter `# Prior Remarks`
am Ende erhalten.

## Inputs

Aequivalent gewichten — alle lesen vor Generation:

- **Kalender** (Google Calendar MCP):
  - Primary (`jochen.kulow@gmail.com`)
  - Praxis (Dr. Kulow Arbeitskalender)
  - LYT-Abos (LYT Workshop, Community, Knowledge Accelerator, WOW Synced Sprint)
  - NICHT: Hencks, Kerkmann, vedentis Management (ausser explizit gefragt)
- **Mails** (Gmail MCP + ggf. vedentis-IMAP via himalaya):
  - Letzte 24h
  - Filter Newsletter via `List-Unsubscribe`-Header
  - Filter Notifications via Sender-Whitelist
- **Wetter** (optional): WebFetch eine reale Quelle (weather.gov etc.) — nie schaetzen, nie fabrizieren

## Struktur des Briefs

```markdown
---
up: ["[[YYYY-MM-DD]]"]
created: YYYY-MM-DD
---

Today is **[Day] [Date], [Year].**

In [City], Low–High [L–H]°C. [Conditions].

## 🔥 Today's Calendar
- [time] [event] (cal: [calendar name])

## 📬 Inbox Status
- **Gmail** — [verdict]
  - Top 3-5 wartende Threads mit Kontext
- **Vedentis-IMAP** — [verdict]
  - dito

## ⚡ Was du vergessen koenntest
- Time-sensitive items aus Kalender + Mails
- Projekte ohne Activity in 3+ Tagen

## 🧭 What's next
- 2-4 konkrete Aktionen fuer heute
```

## Annotations (durch User waehrend des Tages)

- `User: [bemerkung]` — Notiz
- `{verb argument}` — Action marker, z.B. `{draft email to Kim}`

## Edge Cases

- Keine Mails / Kalender-Ausfall: notieren, weitermachen.
- Erste Ausfuehrung: keine "yesterday"-Referenzen.
- Wochenende/Reise: gleiches Template.

## Voice

- Zweite Person fuer Opening.
- Neutral terse fuer Lists und Statuses.

---

*Dies ist ein Beispiel-Skill fuer anker-mini, modelliert nach Nick Milos
daily-brief.md aus dem LYAI-Pilot. Anpassen vor Live-Use.*
