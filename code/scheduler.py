"""Cross-platform scheduling for skills.

A scheduled job:
  - id: stable identifier (uuid)
  - skill_id: which skill to invoke
  - prompt: the prompt passed to `claude -p` (defaults to skill's first trigger)
  - hour, minute: local time of day
  - weekdays: list of weekday ints (1=Mon ... 7=Sun, ISO format); empty = every day
  - created_at: ISO timestamp

State lives in data/schedules.json. The backend artefact (plist on macOS,
crontab entry on Linux) is generated deterministically from this state —
schedules.json is the source of truth.

Backend dispatch by `platform.system()`:
  - "Darwin"  → launchd plist + launchctl bootstrap/bootout
  - "Linux"   → crontab entry via `crontab -l` / `crontab -`
  - other     → NotImplementedError
"""
from __future__ import annotations

import json
import platform
import shlex
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import config

LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
LABEL_PREFIX = "com.anker.skill-"
CRON_MARKER = "ANKER_MINI"

PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{claude_bin}</string>
        <string>-p</string>
        <string>{prompt}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{cwd}</string>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
    <key>StartCalendarInterval</key>
    <array>
{calendar_entries}
    </array>
</dict>
</plist>
"""

CALENDAR_ENTRY = """        <dict>
            <key>Hour</key>
            <integer>{hour}</integer>
            <key>Minute</key>
            <integer>{minute}</integer>{weekday_block}
        </dict>"""

WEEKDAY_BLOCK = """
            <key>Weekday</key>
            <integer>{weekday}</integer>"""


@dataclass
class Schedule:
    id: str
    skill_id: str
    prompt: str
    hour: int
    minute: int
    weekdays: list[int] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @property
    def label(self) -> str:
        return f"{LABEL_PREFIX}{self.skill_id}-{self.id[:8]}"

    @property
    def plist_path(self) -> Path:
        return LAUNCH_AGENTS_DIR / f"{self.label}.plist"

    def to_cron_line(self) -> str:
        """Generate a crontab line. ISO weekdays (1-7, Mon=1, Sun=7) get
        translated to cron weekdays (0-6, Sun=0, Mon=1). The line carries a
        trailing comment marker `# ANKER_MINI[<id>]` so we can find/remove it."""
        # Cron uses 0=Sunday, 1=Monday, ..., 6=Saturday.
        if self.weekdays:
            cron_days = sorted({0 if w == 7 else w for w in self.weekdays})
            days_field = ",".join(str(d) for d in cron_days)
        else:
            days_field = "*"
        log_path = config.log_dir() / f"{self.skill_id}.log"
        # Build the command — shlex.quote handles embedded quotes / shell metachars.
        command = (
            f"cd {shlex.quote(str(config.claude_cwd()))} && "
            f"{shlex.quote(config.claude_bin())} -p {shlex.quote(self.prompt)} "
            f">> {shlex.quote(str(log_path))} 2>&1"
        )
        return (
            f"{self.minute} {self.hour} * * {days_field} {command}  # {CRON_MARKER}[{self.id}]"
        )

    def next_run_at(self, now: datetime | None = None) -> datetime:
        """Compute the next time this schedule will fire (local time)."""
        from datetime import timedelta
        now = now or datetime.now()
        # launchd weekday: 1=Mon ... 7=Sun. Python isoweekday(): 1=Mon ... 7=Sun. Compatible.
        candidates: list[datetime] = []
        for day_offset in range(0, 8):  # next 8 days to cover wrap
            d = now + timedelta(days=day_offset)
            candidate = d.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
            if candidate <= now:
                continue
            if self.weekdays and candidate.isoweekday() not in self.weekdays:
                continue
            candidates.append(candidate)
        return min(candidates) if candidates else now

    def to_plist(self) -> str:
        if self.weekdays:
            entries = "\n".join(
                CALENDAR_ENTRY.format(
                    hour=self.hour,
                    minute=self.minute,
                    weekday_block=WEEKDAY_BLOCK.format(weekday=w),
                )
                for w in sorted(self.weekdays)
            )
        else:
            entries = CALENDAR_ENTRY.format(
                hour=self.hour, minute=self.minute, weekday_block=""
            )
        log_path = config.log_dir() / f"{self.skill_id}.log"
        return PLIST_TEMPLATE.format(
            label=self.label,
            claude_bin=config.claude_bin(),
            prompt=_xml_escape(self.prompt),
            cwd=str(config.claude_cwd()),
            log_path=str(log_path),
            calendar_entries=entries,
        )


def _xml_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _load_state() -> list[Schedule]:
    f = config.schedules_file()
    if not f.exists():
        return []
    raw = json.loads(f.read_text(encoding="utf-8"))
    return [Schedule(**item) for item in raw]


def _save_state(schedules: list[Schedule]) -> None:
    f = config.schedules_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(
        json.dumps([asdict(s) for s in schedules], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def list_schedules() -> list[Schedule]:
    return _load_state()


def get_schedule(schedule_id: str) -> Schedule | None:
    return next((s for s in _load_state() if s.id == schedule_id or s.id.startswith(schedule_id)), None)


def add_schedule(
    skill_id: str,
    prompt: str,
    hour: int,
    minute: int,
    weekdays: list[int] | None = None,
) -> Schedule:
    schedule = Schedule(
        id=uuid.uuid4().hex,
        skill_id=skill_id,
        prompt=prompt,
        hour=hour,
        minute=minute,
        weekdays=weekdays or [],
    )
    state = _load_state()
    state.append(schedule)
    _save_state(state)
    _install(schedule)
    return schedule


def remove_schedule(schedule_id: str) -> Schedule | None:
    state = _load_state()
    sched = next((s for s in state if s.id == schedule_id or s.id.startswith(schedule_id)), None)
    if sched is None:
        return None
    _uninstall(sched)
    state = [s for s in state if s.id != sched.id]
    _save_state(state)
    return sched


def reinstall_all() -> None:
    """Re-write + reload all backend artefacts from schedules.json. For recovery / migration."""
    for s in _load_state():
        _install(s)


def reconcile_from_skills() -> dict[str, list[str]]:
    """Reconcile installed schedules with skill files' `anker_cron` declarations.
    Skill .md files are the Source of Truth.

    Returns a dict with three lists: 'added', 'updated', 'removed' (each list of skill_ids).
    """
    # Late import to avoid circular dep
    from . import skill_runner

    desired: dict[str, tuple[int, int, list[int], str]] = {}  # skill_id → (h,m,wd,spec_str)
    skills_by_id: dict[str, "skill_runner.Skill"] = {}
    for skill in skill_runner.discover_skills():
        if not skill.anker_cron:
            continue
        try:
            h, m, w = parse_schedule_spec(skill.anker_cron)
        except ValueError:
            # Bad spec in file — skip but log via stderr
            import sys
            print(
                f"WARN: skill '{skill.id}' has invalid anker_cron='{skill.anker_cron}' — skipping",
                file=sys.stderr,
            )
            continue
        desired[skill.id] = (h, m, w, skill.anker_cron)
        skills_by_id[skill.id] = skill

    current_by_skill: dict[str, Schedule] = {}
    for s in _load_state():
        # If multiple schedules exist for same skill, keep the first; others get removed below
        current_by_skill.setdefault(s.skill_id, s)

    added: list[str] = []
    updated: list[str] = []
    removed: list[str] = []

    # Add or update
    for skill_id, (h, m, w, spec_str) in desired.items():
        cur = current_by_skill.get(skill_id)
        if cur is None:
            # New schedule
            skill = skills_by_id[skill_id]
            add_schedule(skill_id, skill.default_prompt, h, m, w)
            added.append(skill_id)
        elif (cur.hour, cur.minute, sorted(cur.weekdays)) != (h, m, sorted(w)):
            # Spec changed — replace
            remove_schedule(cur.id)
            skill = skills_by_id[skill_id]
            add_schedule(skill_id, skill.default_prompt, h, m, w)
            updated.append(skill_id)

    # Remove orphans (schedules whose skill no longer declares anker_cron)
    for skill_id, sched in current_by_skill.items():
        if skill_id not in desired:
            remove_schedule(sched.id)
            removed.append(skill_id)

    return {"added": added, "updated": updated, "removed": removed}


def _install(s: Schedule) -> None:
    """Backend-dispatched install."""
    system = platform.system()
    if system == "Darwin":
        _install_plist(s)
    elif system == "Linux":
        _install_cron(s)
    else:
        raise NotImplementedError(
            f"Scheduling auf {system} ist nicht unterstuetzt. Aktuell: Darwin (macOS) + Linux."
        )


def _uninstall(s: Schedule) -> None:
    system = platform.system()
    if system == "Darwin":
        _uninstall_plist(s)
    elif system == "Linux":
        _uninstall_cron(s)
    else:
        raise NotImplementedError(f"Scheduling auf {system} nicht unterstuetzt.")


# --- macOS (launchd) ---

def _install_plist(s: Schedule) -> None:
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    s.plist_path.write_text(s.to_plist(), encoding="utf-8")
    uid = _gui_uid()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}", str(s.plist_path)],
        capture_output=True,
        check=False,
    )
    subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(s.plist_path)],
        capture_output=True,
        check=False,
    )


def _uninstall_plist(s: Schedule) -> None:
    uid = _gui_uid()
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}", str(s.plist_path)],
        capture_output=True,
        check=False,
    )
    if s.plist_path.exists():
        s.plist_path.unlink()


def _gui_uid() -> int:
    import os
    return os.getuid()


# --- Linux (crontab) ---

def _read_crontab() -> list[str]:
    """Read user crontab. Returns list of lines. Empty list if crontab has no jobs."""
    proc = subprocess.run(
        ["crontab", "-l"], capture_output=True, text=True, check=False
    )
    # `crontab -l` exits 1 when no crontab — treat as empty.
    if proc.returncode != 0:
        return []
    return proc.stdout.splitlines()


def _write_crontab(lines: list[str]) -> None:
    body = "\n".join(lines) + ("\n" if lines else "")
    proc = subprocess.run(["crontab", "-"], input=body, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"crontab -: {proc.stderr.strip()}")


def _install_cron(s: Schedule) -> None:
    existing = _read_crontab()
    # Remove any old line for this schedule id (re-install pattern)
    marker = f"# {CRON_MARKER}[{s.id}]"
    filtered = [line for line in existing if marker not in line]
    filtered.append(s.to_cron_line())
    _write_crontab(filtered)


def _uninstall_cron(s: Schedule) -> None:
    existing = _read_crontab()
    marker = f"# {CRON_MARKER}[{s.id}]"
    filtered = [line for line in existing if marker not in line]
    _write_crontab(filtered)


# Convenience: parse human-friendly schedule strings like "07:30 mo-fr" or "05:55 daily"
WEEKDAY_NAMES = {
    "mo": 1, "di": 2, "mi": 3, "do": 4, "fr": 5, "sa": 6, "so": 7,
    "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 7,
}


def parse_schedule_spec_with_ai_fallback(spec: str) -> tuple[int, int, list[int], str]:
    """Try strict parser first. On failure, ask `claude -p` to normalize.
    Returns (hour, minute, weekdays, source) where source is 'direct' or 'ai'."""
    try:
        h, m, w = parse_schedule_spec(spec)
        return h, m, w, "direct"
    except ValueError:
        pass
    normalized = _ai_normalize_spec(spec)
    h, m, w = parse_schedule_spec(normalized)
    return h, m, w, "ai"


def _ai_normalize_spec(natural_text: str) -> str:
    """Call `claude -p` with a strict prompt to convert NL → HH:MM <days> format.
    Raises ValueError if AI output doesn't parse."""
    prompt = (
        "You are a scheduler. Convert the user's natural-language schedule to EXACTLY "
        "this format on a single line:\n"
        "  HH:MM <days>\n"
        "Where:\n"
        "  HH:MM is 24-hour local time (zero-padded).\n"
        "  <days> is one of:\n"
        "    - 'daily'\n"
        "    - a comma-separated list from: mo,di,mi,do,fr,sa,so\n"
        "    - a range like 'mo-fr'\n"
        "Output ONLY the formatted line, no prose, no quotes, no markdown.\n"
        f"User input: {natural_text}"
    )
    try:
        result = subprocess.run(
            [config.claude_bin(), "-p", prompt],
            cwd=str(config.claude_cwd()),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise ValueError(f"AI-Normalisierung fehlgeschlagen: {e}")
    if result.returncode != 0:
        raise ValueError(f"AI-Normalisierung fehlgeschlagen (exit {result.returncode})")
    line = result.stdout.strip().split("\n")[-1].strip().strip("`").strip('"').strip("'")
    if not line:
        raise ValueError("AI lieferte leere Antwort")
    # Validate it parses
    parse_schedule_spec(line)
    return line


def parse_schedule_spec(spec: str) -> tuple[int, int, list[int]]:
    """Parse '07:30 mo-fr', '05:55 daily', '14:00 sa,so' into (hour, minute, weekdays)."""
    parts = spec.strip().lower().split(maxsplit=1)
    if not parts:
        raise ValueError("leerer Schedule-Spec")
    time_part = parts[0]
    days_part = parts[1] if len(parts) > 1 else "daily"
    if ":" not in time_part:
        raise ValueError(f"Zeit muss HH:MM sein, bekam: {time_part}")
    h_str, m_str = time_part.split(":", 1)
    hour, minute = int(h_str), int(m_str)
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"ungueltige Zeit: {time_part}")
    weekdays: list[int] = []
    if days_part in ("daily", "every", "*", ""):
        weekdays = []
    elif "-" in days_part:
        start_str, end_str = days_part.split("-", 1)
        start = WEEKDAY_NAMES.get(start_str.strip())
        end = WEEKDAY_NAMES.get(end_str.strip())
        if start is None or end is None:
            raise ValueError(f"unbekannter Wochentag in: {days_part}")
        weekdays = list(range(start, end + 1))
    else:
        for token in days_part.replace(" ", "").split(","):
            wd = WEEKDAY_NAMES.get(token)
            if wd is None:
                raise ValueError(f"unbekannter Wochentag: {token}")
            weekdays.append(wd)
    return hour, minute, sorted(set(weekdays))
