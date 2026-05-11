---
name: weekly-review
description: |
  Wochenrueckblick — liest alle Daily Notes der letzten 7 Tage, fasst zusammen
  was passiert ist, welche Versprechen offen geblieben sind, und schlaegt 3-5
  Fokuspunkte fuer die kommende Woche vor. Schreibt das Ergebnis nach
  Calendar/Reviews/YYYY-MM-DD Weekly Review.md.
triggers:
  - weekly review
  - wochenrueckblick
  - run my weekly review
  - was war diese woche
  - rueckblick erstellen
dependencies:
  - Obsidian CLI (lesen + schreiben fuer Konsistenz)
created: 2026-05-11
status: Example
---

# Weekly Review (Example Skill)

Wochenrueckblick. Sonntag abends oder Freitag spaet als Closing-Ritual.

## When to use

- **Scheduled:** typisch So 18:00 oder Fr 17:00 — *„`/schedule weekly-review 18:00 so`"*.
- **Ad-hoc:** wenn die Woche kippt und du Re-Orientierung brauchst.

## Inputs

Alle aus dem Vault, gelesen via Obsidian CLI fuer Markdown-Konsistenz:

- **Daily Notes** der letzten 7 Tage (`Calendar/Days/YYYY-MM-DD.md`)
- **Daily Logs** der letzten 7 Tage (`AIOS/History/YYYY-MM-DD Daily Log.md`)
- **Daily Briefs** der letzten 7 Tage — speziell die `User:` annotations und `{action markers}`
- **Active Projects** (`Efforts/Projects/Active/`) mit ihrem Last-Modified-Datum
- **Open commitments** aus prior Briefs

## Output

`Calendar/Reviews/YYYY-MM-DD Weekly Review.md` — eine Note, kein Email, kein
externer Speicher. Bleibt im Vault, ist verlinkt mit den Daily-Notes.

## Structure

```markdown
---
up: ["[[Calendar/Reviews]]"]
period: YYYY-MM-DD bis YYYY-MM-DD
created: YYYY-MM-DD
---

# Weekly Review — KW XX

## 🎯 Was passiert ist
- [Sektion fuer Projekte mit Bewegung]
- [Sektion fuer Mensch-Events]

## ✅ Was erledigt wurde
- Konkrete Closures aus Daily Logs, max 7-10 Items

## ⏸ Was offen geblieben ist
- Open commitments aus prior Briefs ohne Closure
- Pflicht: jeder Punkt mit *„was ist der Naechste Schritt"*

## 🔍 Patterns die ich sehe
- 2-3 Beobachtungen ueber die Woche
- Energie, Mood, Themen-Wiederkehr

## 🧭 Naechste Woche
- 3-5 Fokuspunkte
- Pflicht: jeder mit erstem Schritt + Tag

## Footer
*Generated YYYY-MM-DD by anker-mini weekly-review skill.*
```

## Rules

- **Daten aus Vault, nicht Memory.** Nie fabrizieren, nie aus generischen Mustern erfinden.
- **Quote der User-Annotations.** *„User: ..."* Bullets aus den Daily Briefs wortwoertlich erhalten.
- **Action-Markers tracken.** Wenn `{schedule X for Tuesday}` in einem Brief stand und nicht erledigt wurde → in „Was offen geblieben ist".
- **Patterns ehrlich.** *„Du hast 3 Briefe in Folge geschrieben dass du den Sport-Block einplanen willst und es nicht gemacht"* gehoert dazu.
- **Keine Beschoenigung.** Wenn die Woche dunkel war, sag es. Kein toxischer Optimismus.

## Voice

- Zweite Person, nuechtern, freundlich-direkt.
- Keine Coach-Sprache („du schaffst das"). Nur Beobachtung + Vorschlag.

## Edge Cases

- **Keine Daily Notes vorhanden:** sag „kein PKM-Material gefunden" + biete an, statt Review eine offene Frage-Liste zu schreiben.
- **Daily Brief existiert aber leer:** als „inhaltlich leer" markieren, nicht als „nichts passiert".
- **Erster Lauf (keine prior reviews):** keine Vergleichs-Sektion, einfach was die Woche zeigte.

## Aktivierung

Manuell:
```
/run weekly-review
```

Scheduled (jeden Sonntag 18:00):
```
/schedule weekly-review 18:00 so
```

Oder direkt aus crontab/launchd nach erstem `/schedule`-Lauf.

---

*Modelliert nach den Closing-Rituals aus LYT (Wochenende-MOC) und der
Daily-Trident-Logik (Mensch schreibt, AI fasst zusammen).*
