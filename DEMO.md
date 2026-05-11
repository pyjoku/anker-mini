# anker-mini — Demo Walkthrough

5-Minuten-Demo, geeignet zum Vorzeigen (z.B. an Nick Milo, andere LYAI-Pilot-Tester,
oder AI-Operator-Bootcamp-Teilnehmer).

## Was du zeigst

Eine schlanke Owner-Pfad-Alternative zu Cowork-basierten AIOS-Stacks:
- Markdown-Skills (selber Pattern wie LYAI AIOS)
- Schedule via `launchctl` — Cron im File-System, kein Cloud-State
- `claude -p` als Skill-Executor — funktioniert ueberall wo Claude Code installiert ist
- Keine externe Datenbank, keine GraphRAG, keine Frontend-Abhaengigkeit
- ~700 Zeilen Python total

## Setup in 90 Sekunden

```bash
git clone https://github.com/pyjoku/anker-mini ~/projects/anker-mini
cd ~/projects/anker-mini
cp .env.example .env
$EDITOR .env  # TELEGRAM_BOT_TOKEN, SKILL_PATHS einsetzen
uv sync
./scripts/install_bot.sh
```

Der Bot laeuft jetzt als macOS LaunchAgent (`com.anker.mini`). Logs in
`~/Library/Logs/anker-mini/bot.log`.

## Telegram-Walkthrough

**1. Status pruefen:**
```
You: /start
Bot: anker-mini online.
     Skills entdeckt: 15
     Aktive Schedules: 0
     Befehle: /skills /run /schedule /schedules /unschedule
```

**2. Skills auflisten:**
```
You: /skills
Bot: Verfuegbare Skills:
     • daily-brief — Tagesbrief mit Kalender + Mails
     • pre-planner — Zerlegt eine Aktivitaet in Zeitbloecke ...
     • anker-wartung
     ... (weitere)
```

**3. Skill spontan ausfuehren:**
```
You: /run pre-planner wann muss ich los zum Zahnarzt 14:30 in Lindau
Bot: ⏳ Starte pre-planner …
Bot: pre-planner — ✅ erledigt
```
(Im Hintergrund: `claude -p "wann muss ich los zum Zahnarzt 14:30 in Lindau"`
wird aus dem konfigurierten Working Directory aufgerufen, Output in
`~/Library/Logs/anker-mini/pre-planner.log`.)

**4. Schedule preview (sicher):**
```
You: /preview daily-brief 05:55 mo-fr
Bot: ```xml
     <?xml version="1.0" ...
     ... komplette plist die installiert wuerde ...
     ```
```

**5. Schedule installieren:**
```
You: /schedule daily-brief 05:55 mo-fr
Bot: ✅ Schedule angelegt:
       Skill: daily-brief
       Zeit:  05:55
       Tage:  Mo,Di,Mi,Do,Fr
       Id:    a3f7e2c1
```

Im File-System ist jetzt eine echte launchd-plist:
`~/Library/LaunchAgents/com.anker.skill-daily-brief-a3f7e2c1.plist`.
Apple's launchd uebernimmt von hier — kein eigener Scheduler-Daemon noetig.

**6. Schedule-Log anschauen (nach erster Ausfuehrung):**
```
You: /logs daily-brief 20
Bot: daily-brief letzte 20 Zeilen:
     === daily-brief @ 2026-05-12T05:55:01 ===
     prompt: daily brief
     ... claude -p output ...
     === exit 0 ===
```

## CLI als Alternative (ohne Telegram)

Falls Telegram nicht eingerichtet ist:

```bash
anker-mini-cli skills
anker-mini-cli run pre-planner
anker-mini-cli schedule daily-brief "05:55 mo-fr"
anker-mini-cli schedules
anker-mini-cli unschedule a3f7e2c1
anker-mini-cli preview daily-brief "05:55 mo-fr"
```

## Was anker-mini bewusst NICHT macht

- **Kein Cloud-State.** Schedules leben in `data/schedules.json` + macOS launchd. Nichts in Anthropic-Workspaces, nichts in fremder DB.
- **Keine Memory-Schicht.** anker-mini fuehrt nur aus; das Skill (oder Claude Code dahinter) schreibt selbst in den Vault. Trennung von Concerns.
- **Keine eigene LLM-Anbindung.** `claude -p` ist die Bruecke — bring your own Claude Code. Wer einen anderen Stack will: ein Drei-Zeilen-Wrapper.
- **Keine Skill-Discovery-Magie.** Plain `glob *.md` ueber konfigurierte Pfade — du siehst genau was er findet.
- **Kein Frontend.** Telegram + CLI reichen. Wer ein Web-UI will: forken oder eigenes anker-mini-web bauen.

## Vergleich zum LYAI-AIOS-Pattern

| | LYAI AIOS (Cowork) | anker-mini |
|---|---|---|
| Skill-Format | Markdown mit Frontmatter | gleiches Pattern, kompatibel |
| Skill-Storage | Vault | Vault + optional `~/.claude/skills/` |
| Scheduling | Cowork-UI (cloud) | launchd plist (lokal) |
| Memory-Layer | Cowork-intern | gar nicht — Skill+Vault sind verantwortlich |
| Bootstrap | `me-builder` Skill (autobuilder-dossier) | (geplant — derselbe Pattern, lokaler Lauf) |
| Vault-Schreibinstanz | Cowork raw File-Write | empfohlen: Obsidian CLI fuer Konsistenz |
| LLM | Anthropic-only via Cowork | beliebig via `claude` CLI Backend-Switch |

## Strategischer Punkt

**Owner-Pfad statt Cowork-Convenience.** Bei Cowork mietest du Orchestrierung
und Schedule — bei anker-mini gehoeren sie dir. Trade-off ist UX (kein
Web-Frontend, Markdown-CLI-Setup statt Klick) gegen Sovereignty (kein
Lock-in, alles lokal, alles inspizierbar).

Wer beides will: anker-mini und Cowork koennen denselben Skill-Folder benutzen,
weil die Frontmatter-Konvention identisch ist. Dann hast du Cowork als UI und
anker-mini als robuste lokale Ausfuehrung — und kannst jederzeit eine Seite
ziehen.
