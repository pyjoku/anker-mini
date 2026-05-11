"""launchd-based scheduling for skills.

A scheduled job:
  - id: stable identifier (uuid)
  - skill_id: which skill to invoke
  - prompt: the prompt passed to `claude -p` (defaults to skill's first trigger)
  - hour, minute: local time of day
  - weekdays: list of launchd weekday ints (1=Mon ... 7=Sun); empty = every day
  - created_at: ISO timestamp

State lives in data/schedules.json. The plist is generated deterministically
from this state — schedules.json is the source of truth.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import config

LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"
LABEL_PREFIX = "com.anker.skill-"

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
    _install_plist(schedule)
    return schedule


def remove_schedule(schedule_id: str) -> Schedule | None:
    state = _load_state()
    sched = next((s for s in state if s.id == schedule_id or s.id.startswith(schedule_id)), None)
    if sched is None:
        return None
    _uninstall_plist(sched)
    state = [s for s in state if s.id != sched.id]
    _save_state(state)
    return sched


def reinstall_all() -> None:
    """Re-write + reload all plists from schedules.json. For recovery / migration."""
    for s in _load_state():
        _install_plist(s)


def _install_plist(s: Schedule) -> None:
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    s.plist_path.write_text(s.to_plist(), encoding="utf-8")
    # bootout if already loaded (ignore errors), then bootstrap
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


# Convenience: parse human-friendly schedule strings like "07:30 mo-fr" or "05:55 daily"
WEEKDAY_NAMES = {
    "mo": 1, "di": 2, "mi": 3, "do": 4, "fr": 5, "sa": 6, "so": 7,
    "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 7,
}


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
