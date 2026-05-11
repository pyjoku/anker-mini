"""Config loader — reads .env from project root (no python-dotenv dependency)."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path = PROJECT_ROOT / ".env") -> None:
    """Minimal .env loader. Project-local .env wins over shell env."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def get(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"FEHLER: ENV-Variable {name} fehlt (siehe .env.example).")
    return val or ""


def skill_paths() -> list[Path]:
    raw = get("SKILL_PATHS", "")
    return [Path(p).expanduser() for p in raw.split(":") if p.strip()]


def allowed_user_ids() -> set[int]:
    raw = get("TELEGRAM_ALLOWED_USERS", "")
    return {int(x) for x in raw.split(",") if x.strip().isdigit()}


def claude_cwd() -> Path:
    return Path(get("CLAUDE_CWD", str(Path.home()))).expanduser()


def claude_bin() -> str:
    return get("CLAUDE_BIN", "claude")


def log_dir() -> Path:
    p = Path(get("LOG_DIR", str(Path.home() / "Library" / "Logs" / "anker-mini"))).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def schedules_file() -> Path:
    return PROJECT_ROOT / "data" / "schedules.json"


def bot_token() -> str:
    return get("TELEGRAM_BOT_TOKEN", required=True)
