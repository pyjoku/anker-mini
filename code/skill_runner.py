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

    @property
    def default_prompt(self) -> str:
        return self.triggers[0] if self.triggers else f"run {self.id}"


def _parse_frontmatter(text: str) -> dict[str, object]:
    """Tiny YAML-ish parser — handles flat key/value and simple list items (`- foo`)."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    body = m.group(1)
    out: dict[str, object] = {}
    current_key: str | None = None
    for raw in body.splitlines():
        if not raw.strip():
            continue
        if raw.startswith(" ") or raw.startswith("\t"):
            # List item under current key
            item = raw.strip().lstrip("- ").strip().strip('"').strip("'")
            if current_key is None:
                continue
            existing = out.get(current_key)
            if isinstance(existing, list):
                existing.append(item)
            else:
                out[current_key] = [item]
            continue
        # New top-level key
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        key = key.strip()
        value = value.strip()
        current_key = key
        if value:
            out[key] = value.strip('"').strip("'")
        else:
            out[key] = []
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
    description = str(description_raw).split("\n")[0].strip()[:200]
    triggers_raw = fm.get("triggers") or []
    triggers: list[str] = triggers_raw if isinstance(triggers_raw, list) else [str(triggers_raw)]
    return Skill(id=skill_id, path=path, name=name, description=description, triggers=triggers)


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
