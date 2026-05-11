"""Smoke tests — stdlib only. Run via: python -m unittest tests.test_smoke"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from code import scheduler, skill_runner


class TestScheduleSpecParser(unittest.TestCase):
    def test_daily(self):
        self.assertEqual(scheduler.parse_schedule_spec("07:30 daily"), (7, 30, []))

    def test_implicit_daily(self):
        self.assertEqual(scheduler.parse_schedule_spec("23:00"), (23, 0, []))

    def test_weekday_range(self):
        self.assertEqual(scheduler.parse_schedule_spec("05:55 mo-fr"), (5, 55, [1, 2, 3, 4, 5]))

    def test_weekday_list(self):
        self.assertEqual(scheduler.parse_schedule_spec("14:00 sa,so"), (14, 0, [6, 7]))

    def test_english_names(self):
        self.assertEqual(scheduler.parse_schedule_spec("09:00 mon-fri"), (9, 0, [1, 2, 3, 4, 5]))

    def test_invalid_time(self):
        with self.assertRaises(ValueError):
            scheduler.parse_schedule_spec("25:99 daily")

    def test_bad_format(self):
        with self.assertRaises(ValueError):
            scheduler.parse_schedule_spec("morgen daily")


class TestPlistGeneration(unittest.TestCase):
    def setUp(self):
        self.sched = scheduler.Schedule(
            id="abcd" * 8,
            skill_id="daily-brief",
            prompt="run my daily brief",
            hour=5,
            minute=55,
            weekdays=[1, 2, 3, 4, 5],
        )

    def test_label(self):
        self.assertTrue(self.sched.label.startswith("com.anker.skill-daily-brief-"))

    def test_plist_is_well_formed(self):
        plist = self.sched.to_plist()
        self.assertIn("<?xml", plist)
        self.assertIn("<key>Label</key>", plist)
        self.assertIn("<string>com.anker.skill-daily-brief-", plist)
        # Five weekday entries
        self.assertEqual(plist.count("<key>Weekday</key>"), 5)

    def test_daily_plist_has_no_weekday(self):
        s = scheduler.Schedule(
            id="x" * 32, skill_id="x", prompt="x", hour=7, minute=0, weekdays=[]
        )
        plist = s.to_plist()
        self.assertIn("<key>Hour</key>", plist)
        self.assertNotIn("<key>Weekday</key>", plist)

    def test_xml_escape_prompt(self):
        s = scheduler.Schedule(
            id="x" * 32,
            skill_id="x",
            prompt='run "skill" & escape <these> chars',
            hour=7,
            minute=0,
        )
        plist = s.to_plist()
        self.assertIn("&amp;", plist)
        self.assertIn("&lt;", plist)
        self.assertIn("&quot;", plist)

    def test_plist_round_trips_through_plistlib(self):
        """Output must parse as a valid macOS plist."""
        import plistlib
        parsed = plistlib.loads(self.sched.to_plist().encode())
        self.assertEqual(parsed["ProgramArguments"][1], "-p")
        self.assertEqual(parsed["ProgramArguments"][2], "run my daily brief")
        self.assertEqual(len(parsed["StartCalendarInterval"]), 5)
        entry = parsed["StartCalendarInterval"][0]
        self.assertEqual(entry["Hour"], 5)
        self.assertEqual(entry["Minute"], 55)
        self.assertEqual(entry["Weekday"], 1)

    def test_next_run_daily(self):
        from datetime import datetime
        s = scheduler.Schedule(id="a" * 32, skill_id="x", prompt="x", hour=7, minute=0, weekdays=[])
        # Reference: Monday 2026-05-11 06:00 — should fire same day 07:00
        ref = datetime(2026, 5, 11, 6, 0)
        nxt = s.next_run_at(now=ref)
        self.assertEqual(nxt, datetime(2026, 5, 11, 7, 0))
        # Reference: same day 08:00 — should fire next day 07:00
        ref = datetime(2026, 5, 11, 8, 0)
        nxt = s.next_run_at(now=ref)
        self.assertEqual(nxt, datetime(2026, 5, 12, 7, 0))

    def test_next_run_weekdays_only(self):
        from datetime import datetime
        s = scheduler.Schedule(
            id="b" * 32, skill_id="x", prompt="x", hour=7, minute=0, weekdays=[1, 2, 3, 4, 5]
        )
        # Reference: Friday 2026-05-15 09:00 — next fire is Mon 2026-05-18 07:00
        ref = datetime(2026, 5, 15, 9, 0)
        nxt = s.next_run_at(now=ref)
        self.assertEqual(nxt, datetime(2026, 5, 18, 7, 0))

    def test_plist_round_trips_with_escaped_prompt(self):
        """XML-escaped prompts must decode back to the original string."""
        import plistlib
        original = 'run "x" & <y>'
        s = scheduler.Schedule(
            id="z" * 32, skill_id="z", prompt=original, hour=1, minute=2
        )
        parsed = plistlib.loads(s.to_plist().encode())
        self.assertEqual(parsed["ProgramArguments"][2], original)


class TestCronLineGeneration(unittest.TestCase):
    def test_daily_cron_line(self):
        s = scheduler.Schedule(
            id="abc12345abcdefabcdefabcdefabcdef",
            skill_id="daily-brief",
            prompt="run my daily brief",
            hour=5,
            minute=55,
        )
        line = s.to_cron_line()
        self.assertTrue(line.startswith("55 5 * * * "))
        self.assertIn("-p", line)
        self.assertIn("run my daily brief", line)
        self.assertIn("# ANKER_MINI[abc12345", line)

    def test_weekdays_mo_fr(self):
        s = scheduler.Schedule(
            id="x" * 32,
            skill_id="x",
            prompt="x",
            hour=7,
            minute=30,
            weekdays=[1, 2, 3, 4, 5],
        )
        line = s.to_cron_line()
        # Cron: 1,2,3,4,5 (Mon-Fri), no remapping needed
        self.assertIn("* * 1,2,3,4,5 ", line)

    def test_weekend_sunday_remap(self):
        """ISO weekday 7 (Sunday) must remap to cron 0."""
        s = scheduler.Schedule(
            id="x" * 32, skill_id="x", prompt="x", hour=9, minute=0, weekdays=[6, 7]
        )
        line = s.to_cron_line()
        # 6 (Sat) stays 6, 7 (Sun) becomes 0
        self.assertIn("* * 0,6 ", line)

    def test_shell_quoting_in_prompt(self):
        """Prompt with shell metacharacters must be shell-quoted."""
        s = scheduler.Schedule(
            id="x" * 32,
            skill_id="x",
            prompt="run with $VAR and `cmd` and 'quote' problems",
            hour=9,
            minute=0,
        )
        line = s.to_cron_line()
        # shlex.quote wraps in single quotes and escapes embedded ones
        self.assertIn("$VAR", line)  # not expanded
        self.assertIn("`cmd`", line)


class TestSkillFrontmatter(unittest.TestCase):
    def test_parses_triggers_and_description(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.md"
            path.write_text(
                "---\n"
                'name: demo\n'
                'description: a demo skill\n'
                "triggers:\n"
                "  - hello\n"
                "  - hi there\n"
                "---\n\n"
                "# Body\n",
                encoding="utf-8",
            )
            skill = skill_runner.parse_skill(path)
            self.assertIsNotNone(skill)
            assert skill is not None
            self.assertEqual(skill.id, "demo")
            self.assertEqual(skill.name, "demo")
            self.assertEqual(skill.description, "a demo skill")
            self.assertEqual(skill.triggers, ["hello", "hi there"])
            self.assertEqual(skill.default_prompt, "hello")

    def test_skill_without_frontmatter(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "bare.md"
            path.write_text("# Just a body\nno frontmatter here\n", encoding="utf-8")
            skill = skill_runner.parse_skill(path)
            assert skill is not None
            self.assertEqual(skill.id, "bare")
            self.assertEqual(skill.triggers, [])
            # Default prompt falls back to "run bare"
            self.assertEqual(skill.default_prompt, "run bare")

    def test_parses_literal_block_description(self):
        """description: | followed by indented lines should join into a string."""
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "block.md"
            path.write_text(
                "---\n"
                "name: block\n"
                "description: |\n"
                "  line one\n"
                "  line two continues\n"
                "triggers:\n"
                "  - trig\n"
                "---\n",
                encoding="utf-8",
            )
            skill = skill_runner.parse_skill(path)
            assert skill is not None
            self.assertIn("line one", skill.description)
            self.assertIn("line two", skill.description)
            self.assertEqual(skill.triggers, ["trig"])

    def test_discover_dedupes_across_paths(self):
        with TemporaryDirectory() as t1, TemporaryDirectory() as t2:
            # Same skill id in both — later path should win
            (Path(t1) / "foo.md").write_text(
                "---\nname: foo\ndescription: from t1\n---\n", encoding="utf-8"
            )
            (Path(t2) / "foo.md").write_text(
                "---\nname: foo\ndescription: from t2\n---\n", encoding="utf-8"
            )
            skills = skill_runner.discover_skills([Path(t1), Path(t2)])
            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0].description, "from t2")


if __name__ == "__main__":
    unittest.main()
