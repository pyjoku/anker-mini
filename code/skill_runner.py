"""Skill discovery + execution via `claude -p`.

A skill is a Markdown file with YAML frontmatter. We care about:
  - filename (without .md) → canonical skill id
  - frontmatter `name:` (optional override of id)
  - frontmatter `triggers:` (list of natural-language phrases; first one is the default prompt)
  - frontmatter `description:` (shown in /skills listing)
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import config

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass(frozen=True)
class Skill:
    id: str
    path: Path
    name: str
    description: str
    triggers: list[str]
    anker_cron: str = ""  # SSOT for scheduling — e.g. "05:55 mo-fr" or "daily 07:00"

    @property
    def default_prompt(self) -> str:
        return self.triggers[0] if self.triggers else f"run {self.id}"


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Tiny YAML-ish parser. Handles:
       - flat key/value:    `name: foo`
       - list items:        `triggers:` followed by indented `- item` lines
       - literal block:     `description: |` followed by indented content lines (joined as one string)
    """
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    body = m.group(1)
    out: dict[str, object] = {}
    current_key: str | None = None
    block_mode: str | None = None  # None, "list", or "scalar"
    scalar_lines: list[str] = []

    def _flush_scalar() -> None:
        nonlocal scalar_lines, current_key
        if current_key is not None and scalar_lines:
            out[current_key] = "\n".join(scalar_lines).strip()
        scalar_lines = []

    for raw in body.splitlines():
        if not raw.strip():
            if block_mode == "scalar":
                scalar_lines.append("")
            continue
        if raw.startswith(" ") or raw.startswith("\t"):
            stripped = raw.strip()
            if block_mode == "scalar":
                scalar_lines.append(stripped)
                continue
            if block_mode == "list" or stripped.startswith("- "):
                item = stripped.lstrip("- ").strip().strip('"').strip("'")
                if current_key is None:
                    continue
                existing = out.get(current_key)
                if isinstance(existing, list):
                    existing.append(item)
                else:
                    out[current_key] = [item]
                block_mode = "list"
                continue
            # Indented but neither list nor scalar — ignore (best-effort)
            continue
        # New top-level key — flush any open scalar
        _flush_scalar()
        block_mode = None
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        key = key.strip()
        value = value.strip()
        current_key = key
        if value == "|" or value == ">":
            block_mode = "scalar"
            scalar_lines = []
            out[key] = ""
        elif value:
            out[key] = value.strip('"').strip("'")
        else:
            out[key] = []
            block_mode = "list"
    _flush_scalar()
    return out


def parse_skill(path: Path) -> Skill | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    fm = _parse_frontmatter(text)
    skill_id = path.stem
    name = str(fm.get("name") or skill_id)
    description_raw = fm.get("description") or ""
    description = str(description_raw).strip()
    triggers_raw = fm.get("triggers") or []
    triggers: list[str] = triggers_raw if isinstance(triggers_raw, list) else [str(triggers_raw)]
    anker_cron = str(fm.get("anker_cron") or "").strip()
    return Skill(
        id=skill_id, path=path, name=name, description=description,
        triggers=triggers, anker_cron=anker_cron,
    )


def set_skill_cron(skill_path: Path, cron_spec: str | None) -> None:
    """Write or remove `anker_cron` in a skill's YAML frontmatter.
    cron_spec=None → remove the line. Otherwise → set/replace.
    Preserves everything else in the file as-is."""
    if not skill_path.exists():
        raise FileNotFoundError(skill_path)
    text = skill_path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        # No frontmatter at all — synthesize a minimal one
        if cron_spec is None:
            return
        new_fm = f"---\nanker_cron: {cron_spec!r}\n---\n\n"
        skill_path.write_text(new_fm + text, encoding="utf-8")
        return
    fm_body = m.group(1)
    fm_lines = fm_body.split("\n")
    new_lines: list[str] = []
    found = False
    for line in fm_lines:
        if line.strip().startswith("anker_cron:"):
            found = True
            if cron_spec is not None:
                new_lines.append(f"anker_cron: {cron_spec!r}")
            # if cron_spec is None, drop the line (don't append)
        else:
            new_lines.append(line)
    if not found and cron_spec is not None:
        # Insert before any trailing blanks
        while new_lines and not new_lines[-1].strip():
            new_lines.pop()
        new_lines.append(f"anker_cron: {cron_spec!r}")
    new_fm_body = "\n".join(new_lines)
    new_text = f"---\n{new_fm_body}\n---\n" + text[m.end():]
    skill_path.write_text(new_text, encoding="utf-8")


def discover_skills(paths: Iterable[Path] | None = None) -> list[Skill]:
    paths = list(paths) if paths is not None else config.skill_paths()
    seen: dict[str, Skill] = {}
    for root in paths:
        if not root.exists():
            continue
        for md in sorted(root.glob("*.md")):
            skill = parse_skill(md)
            if skill is None:
                continue
            # Later paths override earlier ones, so user vault wins over global.
            seen[skill.id] = skill
    return sorted(seen.values(), key=lambda s: s.id)


def find_skill(skill_id: str) -> Skill | None:
    for s in discover_skills():
        if s.id == skill_id or s.name.lower() == skill_id.lower():
            return s
    return None


def run_skill(skill: Skill, prompt: str | None = None, log_file: Path | None = None) -> int:
    """Invoke `claude -p <prompt>` from configured CWD. Returns subprocess returncode."""
    cmd = [config.claude_bin(), "-p", prompt or skill.default_prompt]
    log = log_file or (config.log_dir() / f"{skill.id}.log")
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"\n=== {skill.id} @ {_now()} ===\nprompt: {cmd[-1]}\n")
        proc = subprocess.run(
            cmd,
            cwd=str(config.claude_cwd()),
            stdout=fh,
            stderr=subprocess.STDOUT,
            text=True,
        )
        fh.write(f"=== exit {proc.returncode} ===\n")
    return proc.returncode


def _now() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")
