"""Telegram bot — entry point.

Commands:
  /start                                 — welcome + status
  /skills                                — list discoverable skills
  /run <skill> [prompt...]               — run skill once via `claude -p`
  /schedule <skill> <HH:MM> [days] [...] — schedule (e.g. 'daily-brief 05:55 mo-fr')
  /schedules                             — list active schedules
  /unschedule <id-prefix>                — remove a schedule
"""
from __future__ import annotations

import asyncio
import logging
import shlex

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from pathlib import Path

from . import config, scheduler, skill_runner

logger = logging.getLogger("anker-mini")


def _authorize(update: Update) -> bool:
    allowed = config.allowed_user_ids()
    if not allowed:
        return True  # No whitelist → open (dev mode). README warns.
    user = update.effective_user
    return user is not None and user.id in allowed


async def _deny(update: Update) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("Zugriff verweigert.")


async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorize(update):
        await _deny(update)
        return
    skills = skill_runner.discover_skills()
    schedules = scheduler.list_schedules()
    lines = [
        "*anker-mini* online.",
        f"Skills entdeckt: {len(skills)}",
        f"Aktive Schedules: {len(schedules)}",
        "",
        "Befehle: /skills /run /schedule /schedules /unschedule",
    ]
    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_skills(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorize(update):
        await _deny(update)
        return
    skills = skill_runner.discover_skills()
    if not skills:
        await update.effective_message.reply_text(
            "Keine Skills gefunden. Pruefe SKILL_PATHS in .env."
        )
        return
    lines = ["*Verfuegbare Skills:*"]
    for s in skills:
        first_line = s.description.splitlines()[0][:120] if s.description else ""
        desc = f" — {first_line}" if first_line else ""
        lines.append(f"• `{s.id}`{desc}")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_run(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorize(update):
        await _deny(update)
        return
    if not ctx.args:
        await update.effective_message.reply_text("Usage: /run <skill> [prompt...]")
        return
    skill_id = ctx.args[0]
    skill = skill_runner.find_skill(skill_id)
    if skill is None:
        await update.effective_message.reply_text(f"Skill nicht gefunden: {skill_id}")
        return
    prompt = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else None
    await update.effective_message.reply_text(
        f"⏳ Starte `{skill.id}` …", parse_mode="Markdown"
    )
    # Run blocking subprocess in a thread to avoid blocking the event loop.
    rc = await asyncio.to_thread(skill_runner.run_skill, skill, prompt)
    msg = "✅ erledigt" if rc == 0 else f"⚠️ Exit-Code {rc} (Log: {config.log_dir() / (skill.id + '.log')})"
    await update.effective_message.reply_text(f"`{skill.id}` — {msg}", parse_mode="Markdown")


async def cmd_schedule(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorize(update):
        await _deny(update)
        return
    if len(ctx.args) < 2:
        await update.effective_message.reply_text(
            "Usage: /schedule <skill> <HH:MM> [days]\n"
            "Beispiele:\n"
            "  /schedule daily-brief 05:55 mo-fr\n"
            "  /schedule weekly-review 18:00 fr\n"
            "  /schedule pre-planner 07:00 daily"
        )
        return
    skill_id = ctx.args[0]
    skill = skill_runner.find_skill(skill_id)
    if skill is None:
        await update.effective_message.reply_text(f"Skill nicht gefunden: {skill_id}")
        return
    spec = " ".join(ctx.args[1:])
    try:
        hour, minute, weekdays, source = scheduler.parse_schedule_spec_with_ai_fallback(spec)
    except ValueError as e:
        await update.effective_message.reply_text(
            f"Spec konnte weder direkt geparst noch via AI normalisiert werden: {e}"
        )
        return
    days_label = "daily" if not weekdays else ",".join(_wd_label(w) for w in weekdays)
    canonical = f"{hour:02d}:{minute:02d} {days_label.lower()}"
    if source == "ai":
        await update.effective_message.reply_text(
            f"AI normalisiert: '{spec}' → {canonical}"
        )
    # Write to the skill file (SSOT) + reconcile
    try:
        skill_runner.set_skill_cron(skill.path, canonical)
    except OSError as e:
        await update.effective_message.reply_text(f"Konnte Skill-Datei nicht schreiben: {e}")
        return
    result = scheduler.reconcile_from_skills()
    await update.effective_message.reply_text(
        f"✅ anker_cron in {skill.path.name} gesetzt: {canonical}\n"
        f"Reconcile: +{len(result['added'])} ~{len(result['updated'])} -{len(result['removed'])}"
    )


async def cmd_schedules(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorize(update):
        await _deny(update)
        return
    items = scheduler.list_schedules()
    if not items:
        await update.effective_message.reply_text("Keine aktiven Schedules.")
        return
    lines = ["*Aktive Schedules:*"]
    for s in items:
        days = "daily" if not s.weekdays else ",".join(_wd_label(w) for w in s.weekdays)
        next_run = s.next_run_at().strftime("%a %d.%m %H:%M")
        lines.append(
            f"• `{s.id[:8]}` — {s.skill_id} @ {s.hour:02d}:{s.minute:02d} ({days})\n"
            f"    naechster Lauf: {next_run}"
        )
    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_unschedule(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorize(update):
        await _deny(update)
        return
    if not ctx.args:
        await update.effective_message.reply_text("Usage: /unschedule <skill-id-or-prefix>")
        return
    target = ctx.args[0]
    # Resolve to a skill (preferred — SSOT)
    skill = skill_runner.find_skill(target)
    if skill is not None and skill.anker_cron:
        try:
            skill_runner.set_skill_cron(skill.path, None)
        except OSError as e:
            await update.effective_message.reply_text(f"Konnte Skill-Datei nicht schreiben: {e}")
            return
        result = scheduler.reconcile_from_skills()
        await update.effective_message.reply_text(
            f"🗑 anker_cron aus {skill.path.name} entfernt.\n"
            f"Reconcile: +{len(result['added'])} ~{len(result['updated'])} -{len(result['removed'])}"
        )
        return
    # Fallback: direct schedule-id removal (legacy / orphans)
    removed = scheduler.remove_schedule(target)
    if removed is None:
        await update.effective_message.reply_text(
            f"Weder Skill noch Schedule-Id gefunden: {target}"
        )
        return
    await update.effective_message.reply_text(f"🗑 Schedule entfernt: {removed.id[:8]} ({removed.skill_id})")


async def cmd_reconcile(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually reconcile schedules from skills (SSOT)."""
    if not _authorize(update):
        await _deny(update)
        return
    result = scheduler.reconcile_from_skills()
    lines = ["Reconcile complete:"]
    for k, v in result.items():
        lines.append(f"  {k}: {len(v)}" + (f" ({', '.join(v[:5])})" if v else ""))
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_preview(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Dry-run /schedule — zeigt die plist, die generiert wuerde, ohne sie zu installieren."""
    if not _authorize(update):
        await _deny(update)
        return
    if len(ctx.args) < 2:
        await update.effective_message.reply_text(
            "Usage: /preview <skill> <HH:MM> [days]\nZeigt die plist OHNE zu installieren."
        )
        return
    skill_id = ctx.args[0]
    skill = skill_runner.find_skill(skill_id)
    if skill is None:
        await update.effective_message.reply_text(f"Skill nicht gefunden: {skill_id}")
        return
    spec = " ".join(ctx.args[1:])
    try:
        hour, minute, weekdays = scheduler.parse_schedule_spec(spec)
    except ValueError as e:
        await update.effective_message.reply_text(f"Spec ungueltig: {e}")
        return
    import uuid as _uuid
    dummy = scheduler.Schedule(
        id=_uuid.uuid4().hex,
        skill_id=skill.id,
        prompt=skill.default_prompt,
        hour=hour,
        minute=minute,
        weekdays=weekdays,
    )
    body = dummy.to_plist()
    # Telegram message limit safety
    body = body if len(body) < 3500 else body[:3500] + "\n... (gekuerzt)"
    await update.effective_message.reply_text(f"```xml\n{body}\n```", parse_mode="Markdown")


async def cmd_logs(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Zeigt die letzten ~30 Zeilen aus dem Skill-Log."""
    if not _authorize(update):
        await _deny(update)
        return
    if not ctx.args:
        await update.effective_message.reply_text("Usage: /logs <skill> [n_lines]")
        return
    skill_id = ctx.args[0]
    n = 30
    if len(ctx.args) > 1 and ctx.args[1].isdigit():
        n = max(1, min(200, int(ctx.args[1])))
    log_path = config.log_dir() / f"{skill_id}.log"
    if not log_path.exists():
        await update.effective_message.reply_text(f"Kein Log fuer: {skill_id}")
        return
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = "\n".join(lines[-n:])
    if not tail.strip():
        tail = "(leer)"
    if len(tail) > 3500:
        tail = "... (gekuerzt) ...\n" + tail[-3500:]
    await update.effective_message.reply_text(
        f"*{skill_id}* letzte {n} Zeilen:\n```\n{tail}\n```",
        parse_mode="Markdown",
    )


async def cmd_sources(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """List all skill source folders currently active."""
    if not _authorize(update):
        await _deny(update)
        return
    paths = config.skill_paths()
    vault = config.default_vault()
    lines: list[str] = []
    if vault:
        lines.append(f"Default vault: {vault}")
    else:
        lines.append("Default vault: (not set — /setvault <path>)")
    lines.append("")
    if not paths:
        lines.append("Keine Skill-Sources. /addsource <pfad> zum Hinzufuegen.")
    else:
        lines.append("Skill-Sources:")
        for p in paths:
            exists = "✓" if p.exists() else "✗"
            skill_count = len(list(p.glob("*.md"))) if p.exists() else 0
            lines.append(f"  {exists} {p} ({skill_count} skills)")
    # Plain text — no Markdown to avoid path-character parse errors.
    await update.effective_message.reply_text("\n".join(lines))


async def cmd_addsource(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a folder to the user-managed skill-source list.

    Accepts absolute paths OR vault-relative paths (resolved against default_vault).
    Example: /addsource AIOS/Skills  → <default_vault>/AIOS/Skills
    """
    if not _authorize(update):
        await _deny(update)
        return
    if not ctx.args:
        await update.effective_message.reply_text(
            "Usage: /addsource <pfad>\n"
            "  • Absoluter Pfad: /addsource /Users/jochen/obsidianvaults/.../AIOS/Skills\n"
            "  • Vault-relativ (braucht default_vault): /addsource AIOS/Skills"
        )
        return
    raw = " ".join(ctx.args)
    try:
        path = config.resolve_vault_path(raw)
    except ValueError as e:
        await update.effective_message.reply_text(f"Fehler: {e}")
        return
    if not path.exists():
        await update.effective_message.reply_text(
            f"⚠️ Pfad existiert nicht: {path}\nWird trotzdem hinzugefuegt — bitte verifizieren."
        )
    added = config.add_user_skill_path(path)
    if not added:
        await update.effective_message.reply_text(f"Schon hinzugefuegt: {path}")
        return
    new_total = len(skill_runner.discover_skills())
    await update.effective_message.reply_text(
        f"✅ Source hinzugefuegt: {path}\nGesamt Skills jetzt: {new_total}"
    )


async def cmd_removesource(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a user-added skill-source folder."""
    if not _authorize(update):
        await _deny(update)
        return
    if not ctx.args:
        await update.effective_message.reply_text("Usage: /removesource <pfad-oder-prefix>")
        return
    target = " ".join(ctx.args)
    # If the user typed a relative path, resolve it too
    try:
        if not Path(target).is_absolute() and config.default_vault():
            target = str(config.resolve_vault_path(target))
    except Exception:
        pass
    removed = config.remove_user_skill_path(target)
    if removed is None:
        await update.effective_message.reply_text(f"Pfad nicht gefunden: {target}")
        return
    new_total = len(skill_runner.discover_skills())
    await update.effective_message.reply_text(
        f"🗑 Entfernt: {removed}\nGesamt Skills jetzt: {new_total}"
    )


async def cmd_vault(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the current default vault."""
    if not _authorize(update):
        await _deny(update)
        return
    v = config.default_vault()
    if v is None:
        await update.effective_message.reply_text(
            "Kein default vault gesetzt.\nSetze mit /setvault <absoluter-pfad>"
        )
        return
    exists = "✓" if v.exists() else "✗ (Pfad existiert nicht)"
    await update.effective_message.reply_text(f"Default vault: {v}  {exists}")


async def cmd_setvault(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the default vault path (absolute)."""
    if not _authorize(update):
        await _deny(update)
        return
    if not ctx.args:
        await update.effective_message.reply_text(
            "Usage: /setvault <absoluter-pfad>\n"
            "Beispiel: /setvault /Users/jochen/obsidianvaults/LYAI Pilot Test Vault"
        )
        return
    raw = " ".join(ctx.args)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        await update.effective_message.reply_text(f"Pfad muss absolut sein: {path}")
        return
    config.set_default_vault(path)
    note = "" if path.exists() else "  ⚠️ (Pfad existiert nicht — bitte verifizieren)"
    await update.effective_message.reply_text(f"✅ Default vault gesetzt: {path}{note}")


async def cmd_check(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Validate a skill file — frontmatter, triggers, parsability."""
    if not _authorize(update):
        await _deny(update)
        return
    if not ctx.args:
        await update.effective_message.reply_text("Usage: /check <skill>")
        return
    skill_id = ctx.args[0]
    skill = skill_runner.find_skill(skill_id)
    if skill is None:
        await update.effective_message.reply_text(
            f"❌ Skill nicht gefunden: {skill_id}\n"
            f"   Pruefe SKILL_PATHS und dass die Datei `{skill_id}.md` heisst."
        )
        return
    issues: list[str] = []
    if not skill.triggers:
        issues.append(
            "⚠️ Keine `triggers:` im Frontmatter — Default-Prompt wird `run <skill>` sein. "
            "Empfohlen: mind. 1 natuerlichsprachiger Trigger."
        )
    if not skill.description:
        issues.append("⚠️ Keine `description:` — erscheint nicht in /skills Listings.")
    body_size = skill.path.stat().st_size
    if body_size < 200:
        issues.append(f"⚠️ Skill-Body sehr klein ({body_size} bytes) — fehlt evtl. die Anleitung?")
    lines = [
        f"*Skill: `{skill.id}`*",
        f"Pfad: `{skill.path}`",
        f"Name: {skill.name}",
        f"Triggers: {len(skill.triggers)} ({', '.join(skill.triggers[:3])})",
        f"Description: {len(skill.description)} Zeichen",
        f"File-Size: {body_size} bytes",
        "",
    ]
    if issues:
        lines.append("*Findings:*")
        lines.extend(issues)
    else:
        lines.append("✅ Alles OK — Skill ist anker-mini-tauglich.")
    await update.effective_message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_help(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorize(update):
        await _deny(update)
        return
    await update.effective_message.reply_text(
        "*anker-mini* — Telegram-Skill-Scheduler\n\n"
        "/start — Status\n"
        "/skills — Skills auflisten\n"
        "/run <skill> [prompt] — sofort ausfuehren\n"
        "/schedule <skill> <HH:MM> [days] — schedulen\n"
        "/preview <skill> <HH:MM> [days] — plist anschauen ohne installieren\n"
        "/schedules — aktive Schedules\n"
        "/unschedule <id> — entfernen\n"
        "/logs <skill> [n] — letzte Skill-Output-Zeilen\n"
        "/check <skill> — validiert Frontmatter & Body",
        parse_mode="Markdown",
    )


async def fallback(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorize(update):
        await _deny(update)
        return
    await update.effective_message.reply_text(
        "Unbekannter Befehl. /help fuer Liste.",
    )


async def plain_text(update: Update, _ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Plain text → forward to claude -p as the prompt.
    If a skill trigger phrase is detected in the text, run that skill with the
    full text as the prompt. Otherwise just run claude -p directly with the
    text (no skill bound)."""
    if not _authorize(update):
        await _deny(update)
        return
    text = update.effective_message.text or ""
    if not text.strip():
        return
    skills = skill_runner.discover_skills()
    matched: skill_runner.Skill | None = None
    lower = text.lower()
    for s in skills:
        for trig in s.triggers:
            if trig.lower() in lower:
                matched = s
                break
        if matched:
            break

    if matched:
        await update.effective_message.reply_text(f"→ Skill trigger erkannt: {matched.id}")
        rc = await asyncio.to_thread(skill_runner.run_skill, matched, text)
    else:
        # Direct claude -p call with the user's text as prompt
        await update.effective_message.reply_text("→ Sende an claude -p …")
        rc = await asyncio.to_thread(_run_claude_direct, text)

    log_path = config.log_dir() / ((matched.id if matched else "_chat") + ".log")
    tail = _read_log_tail(log_path, 30)
    if rc == 0 and tail:
        # Telegram message limit safety
        if len(tail) > 3500:
            tail = "... (gekuerzt) ...\n" + tail[-3500:]
        await update.effective_message.reply_text(tail)
    elif rc == 0:
        await update.effective_message.reply_text("✅ done (kein Output)")
    else:
        await update.effective_message.reply_text(f"⚠️ Exit-Code {rc} — siehe Log: {log_path}")


def _run_claude_direct(prompt: str) -> int:
    """Bare `claude -p <prompt>` invocation (no skill context)."""
    import subprocess as _sp
    from datetime import datetime as _dt
    log_path = config.log_dir() / "_chat.log"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n=== _chat @ {_dt.now().isoformat(timespec='seconds')} ===\nprompt: {prompt}\n")
        proc = _sp.run(
            [config.claude_bin(), "-p", prompt],
            cwd=str(config.claude_cwd()),
            stdout=fh,
            stderr=_sp.STDOUT,
            text=True,
        )
        fh.write(f"=== exit {proc.returncode} ===\n")
    return proc.returncode


def _read_log_tail(path: Path, n_lines: int = 30) -> str:
    """Return the body of the most recent invocation in a skill log.
    Tries to extract just between the last '=== ... ===' boundary pair."""
    if not path.exists():
        return ""
    try:
        all_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    # Walk back from the end to find the most recent boundary pair
    last_idx = None
    for i in range(len(all_lines) - 1, -1, -1):
        if all_lines[i].startswith("=== ") and not all_lines[i].startswith("=== exit "):
            last_idx = i
            break
    if last_idx is None:
        return "\n".join(all_lines[-n_lines:])
    body = all_lines[last_idx + 2:]  # skip the boundary line and the 'prompt:' line
    # Drop trailing '=== exit X ===' if present
    if body and body[-1].startswith("=== exit "):
        body = body[:-1]
    return "\n".join(body).strip()


def _wd_label(w: int) -> str:
    names = {1: "Mo", 2: "Di", 3: "Mi", 4: "Do", 5: "Fr", 6: "Sa", 7: "So"}
    return names.get(w, str(w))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    config.load_dotenv()
    token = config.bot_token()

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("skills", cmd_skills))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("schedule", cmd_schedule))
    app.add_handler(CommandHandler("schedules", cmd_schedules))
    app.add_handler(CommandHandler("unschedule", cmd_unschedule))
    app.add_handler(CommandHandler("reconcile", cmd_reconcile))
    app.add_handler(CommandHandler("preview", cmd_preview))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(CommandHandler("sources", cmd_sources))
    app.add_handler(CommandHandler("addsource", cmd_addsource))
    app.add_handler(CommandHandler("removesource", cmd_removesource))
    app.add_handler(CommandHandler("vault", cmd_vault))
    app.add_handler(CommandHandler("setvault", cmd_setvault))
    app.add_handler(MessageHandler(filters.COMMAND, fallback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, plain_text))

    logger.info("anker-mini gestartet")
    # Startup-Reconcile: skill .md anker_cron entries are the SSOT.
    try:
        result = scheduler.reconcile_from_skills()
        logger.info(
            "startup reconcile: +%d ~%d -%d",
            len(result["added"]), len(result["updated"]), len(result["removed"]),
        )
    except Exception as e:
        logger.warning("startup reconcile failed: %s", e)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
