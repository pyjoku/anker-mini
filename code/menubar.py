"""macOS menubar app — drives anker-mini from the menu bar.

Menu structure:
  ⚓ anker-mini
  ├─ Skills (count)
  │   └─ <each skill> → Run / Schedule / Preview
  ├─ Sources
  │   ├─ <each source path> (count)
  │   └─ + Add Source… (folder picker)
  ├─ Schedules
  │   ├─ <each schedule> → Remove
  │   └─ Reinstall all
  ├─ Default Vault
  │   ├─ Current: <path>
  │   └─ Change… (folder picker)
  ├─ Bot
  │   ├─ Status (running pid X)
  │   ├─ Start
  │   ├─ Stop
  │   └─ Tail Log
  ├─ Refresh
  └─ Quit

Native folder picker via AppleScript (`osascript`) — no NSOpenPanel boilerplate.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
from pathlib import Path

try:
    import rumps
except ImportError:
    print("FEHLER: rumps fehlt. Installiere via `uv sync --extra mac`.", file=sys.stderr)
    sys.exit(1)

from . import config, scheduler, skill_runner


def _pick_folder(prompt: str = "Choose a folder") -> Path | None:
    """Native macOS folder picker via osascript. Returns None on cancel."""
    script = f'POSIX path of (choose folder with prompt "{prompt}")'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    chosen = result.stdout.strip()
    if not chosen:
        return None
    return Path(chosen)


def _ask_text(prompt: str, default: str = "") -> str | None:
    """Native macOS text-input dialog via osascript. Returns None on cancel."""
    safe_prompt = prompt.replace('"', '\\"').replace("\n", "\\n")
    safe_default = default.replace('"', '\\"')
    script = (
        f'display dialog "{safe_prompt}" default answer "{safe_default}" '
        f'with title "anker-mini" buttons {{"Cancel", "OK"}} default button "OK"'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    # osascript returns: "button returned:OK, text returned:08:00 daily"
    out = result.stdout.strip()
    if "text returned:" not in out:
        return None
    return out.split("text returned:", 1)[1].strip()


def _notify(title: str, msg: str) -> None:
    """Best-effort notification — never crashes a callback if the
    notification center isn't available (e.g. venv without Info.plist)."""
    try:
        rumps.notification(title="anker-mini", subtitle=title, message=msg)
    except Exception:
        # Fall back to stdout so info is still visible in bot.log if running detached.
        print(f"[anker-mini] {title}: {msg}")


def _bot_pid() -> int | None:
    try:
        out = subprocess.run(
            ["pgrep", "-f", "python.*code\\.bot"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in out.stdout.splitlines():
            pid = line.strip()
            if pid.isdigit():
                return int(pid)
    except OSError:
        pass
    return None


def _start_bot() -> int | None:
    """Spawn anker-mini bot detached. Returns pid or None on failure."""
    project_root = Path(__file__).resolve().parent.parent
    venv_py = project_root / ".venv" / "bin" / "python"
    if not venv_py.exists():
        return None
    log_path = config.log_dir() / "bot.log"
    log_fh = open(log_path, "a")
    proc = subprocess.Popen(
        [str(venv_py), "-m", "code.bot"],
        cwd=str(project_root),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return proc.pid


def _stop_bot() -> bool:
    pid = _bot_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 9)
        return True
    except OSError:
        return False


class AnkerMiniApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("⚓", quit_button=None)
        self.refresh()

    # --- top-level builders ---

    def refresh(self, _sender=None) -> None:
        self.menu.clear()
        self.menu = [
            self._skills_menu(),
            self._sources_menu(),
            self._schedules_menu(),
            self._vault_menu(),
            None,
            self._bot_menu(),
            None,
            rumps.MenuItem("Refresh", callback=self.refresh),
            rumps.MenuItem("Quit", callback=self._quit),
        ]

    def _skills_menu(self) -> rumps.MenuItem:
        skills = skill_runner.discover_skills()
        m = rumps.MenuItem(f"Skills ({len(skills)})")
        if not skills:
            m.add(rumps.MenuItem("(none — add a source folder)"))
            return m
        for s in skills:
            label = f"{s.id}  ⏰ {s.anker_cron}" if s.anker_cron else s.id
            sub = rumps.MenuItem(label)
            sub.add(rumps.MenuItem("Run now", callback=self._make_run(s)))
            schedule_label = "Change schedule…" if s.anker_cron else "Schedule…"
            sub.add(rumps.MenuItem(schedule_label, callback=self._make_preview(s)))
            if s.anker_cron:
                sub.add(rumps.MenuItem("Remove schedule", callback=self._make_unschedule(s)))
            sub.add(rumps.MenuItem(f"Reveal source: {s.path.name}", callback=self._make_reveal(s.path)))
            m.add(sub)
        return m

    def _make_unschedule(self, skill: skill_runner.Skill):
        def _cb(_):
            ok = rumps.alert(
                "Remove schedule?",
                f"{skill.id} is currently scheduled as: {skill.anker_cron}",
                ok="Remove",
                cancel="Cancel",
            )
            if ok != 1:
                return
            def worker() -> None:
                try:
                    skill_runner.set_skill_cron(skill.path, None)
                    result = scheduler.reconcile_from_skills()
                    _notify("Schedule removed", f"{skill.id}  (-{len(result['removed'])})")
                except Exception as e:
                    _notify("Remove failed", str(e))
                self._schedule_refresh()
            threading.Thread(target=worker, daemon=True).start()
        return _cb

    def _sources_menu(self) -> rumps.MenuItem:
        paths = config.skill_paths()
        m = rumps.MenuItem(f"Sources ({len(paths)})")
        for p in paths:
            exists = "✓" if p.exists() else "✗"
            count = len(list(p.glob("*.md"))) if p.exists() else 0
            label = f"{exists} {p.name} ({count})"
            sub = rumps.MenuItem(label)
            sub.add(rumps.MenuItem(f"Path: {p}"))
            sub.add(rumps.MenuItem("Remove from sources", callback=self._make_remove_source(p)))
            sub.add(rumps.MenuItem("Reveal in Finder", callback=self._make_reveal(p)))
            m.add(sub)
        m.add(None)
        m.add(rumps.MenuItem("Add Source…", callback=self._add_source))
        return m

    def _schedules_menu(self) -> rumps.MenuItem:
        items = scheduler.list_schedules()
        m = rumps.MenuItem(f"Schedules ({len(items)})")
        if not items:
            m.add(rumps.MenuItem("(none)"))
        else:
            for s in items:
                days = "daily" if not s.weekdays else ",".join(str(d) for d in s.weekdays)
                label = f"{s.skill_id} @ {s.hour:02d}:{s.minute:02d} ({days})"
                sub = rumps.MenuItem(label)
                next_run = s.next_run_at().strftime("%a %d %b %H:%M")
                sub.add(rumps.MenuItem(f"Next run: {next_run}"))
                sub.add(rumps.MenuItem(f"ID: {s.id[:8]}"))
                sub.add(rumps.MenuItem("Remove", callback=self._make_remove_schedule(s)))
                m.add(sub)
        m.add(None)
        m.add(rumps.MenuItem("Reconcile from skills (SSOT)", callback=self._reconcile_from_skills))
        m.add(rumps.MenuItem("Reinstall all", callback=self._reinstall_schedules))
        return m

    def _reconcile_from_skills(self, _) -> None:
        _notify("Reconciling…", "")
        def worker() -> None:
            try:
                result = scheduler.reconcile_from_skills()
                _notify(
                    "Reconcile complete",
                    f"+{len(result['added'])} ~{len(result['updated'])} -{len(result['removed'])}"
                )
            except Exception as e:
                _notify("Reconcile failed", str(e))
            self._schedule_refresh()
        threading.Thread(target=worker, daemon=True).start()

    def _vault_menu(self) -> rumps.MenuItem:
        v = config.default_vault()
        label = f"Vault: {v.name if v else '(not set)'}"
        m = rumps.MenuItem(label)
        if v:
            m.add(rumps.MenuItem(f"Path: {v}"))
            m.add(rumps.MenuItem("Reveal in Finder", callback=self._make_reveal(v)))
        m.add(rumps.MenuItem("Change vault…", callback=self._set_vault))
        return m

    def _bot_menu(self) -> rumps.MenuItem:
        pid = _bot_pid()
        status = f"Bot: running (pid {pid})" if pid else "Bot: stopped"
        m = rumps.MenuItem(status)
        if pid:
            m.add(rumps.MenuItem("Stop bot", callback=self._stop_bot_action))
        else:
            m.add(rumps.MenuItem("Start bot", callback=self._start_bot_action))
        m.add(rumps.MenuItem("Tail bot log…", callback=self._tail_bot_log))
        return m

    # --- actions ---

    def _make_run(self, skill: skill_runner.Skill):
        def _cb(_):
            def worker() -> None:
                skill_runner.run_skill(skill)
                _notify("Skill finished", f"{skill.id} done — see log")
            threading.Thread(target=worker, daemon=True).start()
            _notify("Skill started", f"{skill.id}")
        return _cb

    def _make_preview(self, skill: skill_runner.Skill):
        def _cb(_):
            text = _ask_text(
                f"Schedule {skill.id} — when?\\n"
                "Examples: '05:55 mo-fr'  '09:00 daily'  'every weekday at 7'  "
                "'jeden Sonntag abend um 18'  (AI normalizes natural language)",
                default=skill.anker_cron or "08:00 daily",
            )
            if text is None or not text.strip():
                return
            # Push everything heavy (AI call + reconcile) into a background thread
            # so the menubar stays responsive.
            _notify("Scheduling…", f"{skill.id}: '{text}'")
            def worker() -> None:
                try:
                    hour, minute, weekdays, source = scheduler.parse_schedule_spec_with_ai_fallback(text)
                except ValueError as e:
                    _notify("Couldn't parse", str(e))
                    return
                days_str = "daily" if not weekdays else ",".join(
                    ["mo","di","mi","do","fr","sa","so"][w-1] for w in weekdays
                )
                canonical = f"{hour:02d}:{minute:02d} {days_str}"
                try:
                    skill_runner.set_skill_cron(skill.path, canonical)
                except OSError as e:
                    _notify("File write failed", str(e))
                    return
                try:
                    result = scheduler.reconcile_from_skills()
                except Exception as e:
                    _notify("Reconcile failed", str(e))
                    return
                _notify(
                    f"Scheduled: {skill.id}",
                    f"{canonical} (+{len(result['added'])} ~{len(result['updated'])})"
                )
                # rumps.Timer fires its callback on the main thread.
                self._schedule_refresh()
            threading.Thread(target=worker, daemon=True).start()
        return _cb

    def _schedule_refresh(self) -> None:
        """Trigger refresh() on the main thread from any thread."""
        t = rumps.Timer(callback=lambda _: (self.refresh(), t.stop()), interval=0.05)
        t.start()

    def _make_reveal(self, path: Path):
        def _cb(_):
            if path.exists():
                subprocess.run(["open", "-R", str(path)], check=False)
            else:
                subprocess.run(["open", str(path.parent)], check=False)
        return _cb

    def _make_remove_source(self, path: Path):
        def _cb(_):
            ok = rumps.alert("Remove source?", str(path), ok="Remove", cancel="Cancel")
            if ok == 1:
                removed = config.remove_user_skill_path(str(path))
                if removed:
                    _notify("Source removed", str(removed))
                else:
                    _notify("Not found", "Path was not in user-managed list")
                self.refresh()
        return _cb

    def _make_remove_schedule(self, sched):
        def _cb(_):
            ok = rumps.alert(
                "Remove schedule?",
                f"{sched.skill_id} @ {sched.hour:02d}:{sched.minute:02d}",
                ok="Remove",
                cancel="Cancel",
            )
            if ok == 1:
                scheduler.remove_schedule(sched.id)
                _notify("Schedule removed", sched.skill_id)
                self.refresh()
        return _cb

    def _add_source(self, _) -> None:
        chosen = _pick_folder("Choose a skills folder to add")
        if chosen is None:
            return
        added = config.add_user_skill_path(chosen)
        if added:
            _notify("Source added", str(chosen))
        else:
            _notify("Already present", str(chosen))
        self.refresh()

    def _set_vault(self, _) -> None:
        chosen = _pick_folder("Choose your default vault root")
        if chosen is None:
            return
        config.set_default_vault(chosen)
        _notify("Default vault set", str(chosen))
        self.refresh()

    def _reinstall_schedules(self, _) -> None:
        scheduler.reinstall_all()
        _notify("Schedules", f"Re-installed {len(scheduler.list_schedules())}")

    def _start_bot_action(self, _) -> None:
        pid = _start_bot()
        if pid:
            _notify("Bot started", f"pid {pid}")
        else:
            rumps.alert("Bot failed to start", "Check .venv exists and config.json has telegram.bot_token.")
        self.refresh()

    def _stop_bot_action(self, _) -> None:
        if _stop_bot():
            _notify("Bot stopped", "")
        else:
            _notify("Bot not running", "")
        self.refresh()

    def _tail_bot_log(self, _) -> None:
        log_path = config.log_dir() / "bot.log"
        if log_path.exists():
            subprocess.run(["open", "-a", "Console", str(log_path)], check=False)
        else:
            rumps.alert("No log yet", str(log_path))

    def _quit(self, _) -> None:
        rumps.quit_application()


def main() -> None:
    config.load_dotenv()  # triggers config migration if needed
    AnkerMiniApp().run()


if __name__ == "__main__":
    main()
