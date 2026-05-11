# Examples

Vorgefertigte Skill-Files, die du nach `~/.claude/skills/` oder in deinen
Vault-Skills-Ordner kopieren kannst.

| File | Zweck | Aktivierung |
|---|---|---|
| `daily-brief.md` | Morgendlicher Tagesbrief mit Kalender + Mails | `/schedule daily-brief 05:55 mo-fr` |

## Installation

```bash
# Kopiere ins User-Skills-Verzeichnis
cp examples/daily-brief.md ~/.claude/skills/

# Oder in den Vault (wenn du dort deine Skills hast):
cp examples/daily-brief.md "~/path/to/your/vault/AIOS/Skills/"
```

Stell sicher dass `SKILL_PATHS` in deiner `.env` den entsprechenden Ordner enthaelt,
dann erscheint der Skill in `/skills` und kann ueber `/schedule` automatisiert werden.

## Eigene Skills bauen

Minimum-Frontmatter fuer einen anker-mini-kompatiblen Skill:

```yaml
---
name: my-skill
description: Was es tut (eine Zeile).
triggers:
  - mein trigger
  - alternative formulierung
---

# Skill-Inhalt ab hier ...
```

Der erste `triggers:`-Eintrag wird zum Default-Prompt fuer `claude -p`. Du kannst
beim `/run` aber auch einen anderen Prompt mitgeben:

```
/run my-skill mit anderem prompt-text
```
