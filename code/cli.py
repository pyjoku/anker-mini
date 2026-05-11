"""Command-line interface — same functionality as the Telegram bot, but local.

Useful before the bot is set up, for headless servers, or for ops:

    anker-mini-cli skills
    anker-mini-cli run daily-brief
    anker-mini-cli schedule daily-brief "05:55 mo-fr"
    anker-mini-cli schedules
    anker-mini-cli unschedule <id-prefix>
    anker-mini-cli preview daily-brief "05:55 mo-fr"
    anker-mini-cli reinstall
"""
from __future__ import annotations

import argparse
import sys

from . import config, scheduler, skill_runner


def _list_skills(_args) -> int:
    skills = skill_runner.discover_skills()
    if not skills:
        print("Keine Skills gefunden. SKILL_PATHS pruefen.", file=sys.stderr)
        return 1
    for s in skills:
        first_line = s.description.splitlines()[0][:120] if s.description else ""
        desc = f"  — {first_line}" if first_line else ""
        print(f"{s.id}{desc}")
    return 0


def _run(args) -> int:
    skill = skill_runner.find_skill(args.skill)
    if skill is None:
        print(f"Skill nicht gefunden: {args.skill}", file=sys.stderr)
        return 2
    prompt = " ".join(args.prompt) if args.prompt else None
    rc = skill_runner.run_skill(skill, prompt)
    log_path = config.log_dir() / f"{skill.id}.log"
    print(f"Exit {rc}. Log: {log_path}")
    return rc


def _schedule(args) -> int:
    skill = skill_runner.find_skill(args.skill)
    if skill is None:
        print(f"Skill nicht gefunden: {args.skill}", file=sys.stderr)
        return 2
    try:
        hour, minute, weekdays = scheduler.parse_schedule_spec(args.spec)
    except ValueError as e:
        print(f"Spec ungueltig: {e}", file=sys.stderr)
        return 3
    sched = scheduler.add_schedule(
        skill_id=skill.id,
        prompt=skill.default_prompt,
        hour=hour,
        minute=minute,
        weekdays=weekdays,
    )
    days = "daily" if not weekdays else ",".join(str(w) for w in weekdays)
    print(f"OK: {sched.id[:8]} — {skill.id} @ {hour:02d}:{minute:02d} ({days})")
    print(f"     plist: {sched.plist_path}")
    return 0


def _schedules(_args) -> int:
    items = scheduler.list_schedules()
    if not items:
        print("(keine)")
        return 0
    for s in items:
        days = "daily" if not s.weekdays else ",".join(str(w) for w in s.weekdays)
        print(f"{s.id[:8]}  {s.skill_id:<25}  {s.hour:02d}:{s.minute:02d}  {days}")
    return 0


def _unschedule(args) -> int:
    removed = scheduler.remove_schedule(args.id_prefix)
    if removed is None:
        print(f"Schedule nicht gefunden: {args.id_prefix}", file=sys.stderr)
        return 2
    print(f"Entfernt: {removed.id[:8]} ({removed.skill_id})")
    return 0


def _preview(args) -> int:
    skill = skill_runner.find_skill(args.skill)
    if skill is None:
        print(f"Skill nicht gefunden: {args.skill}", file=sys.stderr)
        return 2
    try:
        hour, minute, weekdays = scheduler.parse_schedule_spec(args.spec)
    except ValueError as e:
        print(f"Spec ungueltig: {e}", file=sys.stderr)
        return 3
    import uuid as _uuid
    dummy = scheduler.Schedule(
        id=_uuid.uuid4().hex,
        skill_id=skill.id,
        prompt=skill.default_prompt,
        hour=hour,
        minute=minute,
        weekdays=weekdays,
    )
    print(dummy.to_plist())
    return 0


def _reinstall(_args) -> int:
    scheduler.reinstall_all()
    print(f"Re-installed {len(scheduler.list_schedules())} schedules.")
    return 0


def main(argv: list[str] | None = None) -> int:
    config.load_dotenv()
    parser = argparse.ArgumentParser(prog="anker-mini-cli", description="anker-mini local CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("skills", help="list skills").set_defaults(func=_list_skills)

    p_run = sub.add_parser("run", help="run a skill via claude -p")
    p_run.add_argument("skill")
    p_run.add_argument("prompt", nargs="*", help="optional prompt override")
    p_run.set_defaults(func=_run)

    p_sched = sub.add_parser("schedule", help="add a schedule")
    p_sched.add_argument("skill")
    p_sched.add_argument("spec", help="e.g. '05:55 mo-fr' or '07:00 daily'")
    p_sched.set_defaults(func=_schedule)

    sub.add_parser("schedules", help="list active schedules").set_defaults(func=_schedules)

    p_un = sub.add_parser("unschedule", help="remove a schedule")
    p_un.add_argument("id_prefix")
    p_un.set_defaults(func=_unschedule)

    p_pre = sub.add_parser("preview", help="dry-run schedule (show plist)")
    p_pre.add_argument("skill")
    p_pre.add_argument("spec")
    p_pre.set_defaults(func=_preview)

    sub.add_parser("reinstall", help="re-install all plists from schedules.json").set_defaults(func=_reinstall)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
