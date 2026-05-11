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
        hour, minute, weekdays = scheduler.parse_schedule_spec(spec)
    except ValueError as e:
        await update.effective_message.reply_text(f"Spec ungueltig: {e}")
        return
    sched = scheduler.add_schedule(
        skill_id=skill.id,
        prompt=skill.default_prompt,
        hour=hour,
        minute=minute,
        weekdays=weekdays,
    )
    days_label = "daily" if not weekdays else ",".join(_wd_label(w) for w in weekdays)
    await update.effective_message.reply_text(
        f"✅ Schedule angelegt:\n"
        f"  Skill:    `{skill.id}`\n"
        f"  Zeit:     {hour:02d}:{minute:02d}\n"
        f"  Tage:     {days_label}\n"
        f"  Id:       `{sched.id[:8]}`",
        parse_mode="Markdown",
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
        await update.effective_message.reply_text("Usage: /unschedule <id-prefix>")
        return
    removed = scheduler.remove_schedule(ctx.args[0])
    if removed is None:
        await update.effective_message.reply_text(f"Schedule nicht gefunden: {ctx.args[0]}")
        return
    await update.effective_message.reply_text(
        f"🗑 Entfernt: `{removed.id[:8]}` ({removed.skill_id})",
        parse_mode="Markdown",
    )


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
    app.add_handler(CommandHandler("preview", cmd_preview))
    app.add_handler(CommandHandler("logs", cmd_logs))
    app.add_handler(CommandHandler("check", cmd_check))
    app.add_handler(MessageHandler(filters.COMMAND, fallback))

    logger.info("anker-mini gestartet")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
