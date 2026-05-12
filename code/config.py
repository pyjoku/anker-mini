"""Config — reads from ~/.ankermini/config.json (the source of truth).

Layout:
    ~/.ankermini/
    ├── config.json       — telegram + skills + claude (this file)
    ├── schedules.json    — active schedules (managed by scheduler.py)
    └── logs/             — per-skill output logs (default LOG_DIR)

config.json shape:
{
  "telegram": {"bot_token": "...", "allowed_users": [123, 456]},
  "skills":   {"paths": ["/abs/path/one", "/abs/path/two"]},
  "claude":   {"cwd": "/abs/path", "bin": "claude"}
}

Migration: on first access, if ~/.ankermini/config.json is missing AND
PROJECT_ROOT/.env exists, values are migrated from .env into the JSON.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
USER_STATE_DIR = Path.home() / ".ankermini"


def state_dir() -> Path:
    USER_STATE_DIR.mkdir(parents=True, exist_ok=True)
    return USER_STATE_DIR


def config_file() -> Path:
    return state_dir() / "config.json"


def schedules_file() -> Path:
    return state_dir() / "schedules.json"


def log_dir() -> Path:
    raw = _read().get("log_dir")
    p = Path(raw).expanduser() if raw else state_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


# --- internal: read + write ---


_DEFAULT_CONFIG: dict = {
    "telegram": {"bot_token": "", "allowed_users": []},
    "skills":   {"paths": [], "default_vault": ""},
    "claude":   {"cwd": str(Path.home()), "bin": "claude"},
}


def _read() -> dict:
    f = config_file()
    if not f.exists():
        migrated = _migrate_from_env_if_present()
        if migrated:
            return migrated
        return _DEFAULT_CONFIG.copy()
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _DEFAULT_CONFIG.copy()
    # Merge with defaults so missing keys don't crash callers
    merged = _DEFAULT_CONFIG.copy()
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    return merged


def _write(data: dict) -> None:
    f = config_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass


def _migrate_from_env_if_present() -> dict | None:
    """One-shot migration from PROJECT_ROOT/.env on first run."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return None
    env: dict[str, str] = {}
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    data = _DEFAULT_CONFIG.copy()
    data["telegram"] = {
        "bot_token": env.get("TELEGRAM_BOT_TOKEN", ""),
        "allowed_users": [int(x) for x in env.get("TELEGRAM_ALLOWED_USERS", "").split(",") if x.strip().isdigit()],
    }
    data["skills"] = {
        "paths": [p for p in env.get("SKILL_PATHS", "").split(":") if p.strip()],
    }
    data["claude"] = {
        "cwd": env.get("CLAUDE_CWD", str(Path.home())),
        "bin": env.get("CLAUDE_BIN", "claude"),
    }
    if env.get("LOG_DIR"):
        data["log_dir"] = env["LOG_DIR"]
    _write(data)
    return data


# --- public api: getters ---


def load_dotenv(path: Path | None = None) -> None:
    """Compatibility shim. Old code called this — now reading is lazy and
    config-file-driven. Triggers migration from .env on first run."""
    _read()


def bot_token() -> str:
    val = _read().get("telegram", {}).get("bot_token", "")
    if not val:
        raise RuntimeError("ERROR: telegram.bot_token is missing in ~/.ankermini/config.json")
    return val


def allowed_user_ids() -> set[int]:
    raw = _read().get("telegram", {}).get("allowed_users", [])
    return {int(x) for x in raw if isinstance(x, (int, str)) and str(x).strip().lstrip("-").isdigit()}


def skill_paths() -> list[Path]:
    raw = _read().get("skills", {}).get("paths", [])
    seen: set[str] = set()
    out: list[Path] = []
    for s in raw:
        p = Path(str(s)).expanduser()
        key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def claude_cwd() -> Path:
    return Path(_read().get("claude", {}).get("cwd", str(Path.home()))).expanduser()


def default_vault() -> Path | None:
    raw = _read().get("skills", {}).get("default_vault", "")
    if not raw:
        return None
    return Path(str(raw)).expanduser()


def resolve_vault_path(user_input: str) -> Path:
    """Resolve a user-supplied path. Absolute → as-is. Relative → joined to default_vault.
    If no default_vault is set and the path is relative, raises ValueError."""
    p = Path(user_input).expanduser()
    if p.is_absolute():
        return p
    vault = default_vault()
    if vault is None:
        raise ValueError(
            "Relativer Pfad gegeben, aber kein default_vault gesetzt. "
            "Setze einen mit /setvault <pfad> oder gib einen absoluten Pfad an."
        )
    return (vault / p).resolve()


def set_default_vault(path: Path) -> None:
    data = _read()
    data.setdefault("skills", {})["default_vault"] = str(path.expanduser())
    _write(data)


def claude_bin() -> str:
    return _read().get("claude", {}).get("bin", "claude")


# Back-compat for older callers
def get(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"ERROR: env var {name} is missing.")
    return val or ""


# --- public api: mutators ---


def add_user_skill_path(path: Path) -> bool:
    """Add a path to skills.paths. Returns True if newly added."""
    data = _read()
    paths = list(data.get("skills", {}).get("paths", []))
    new_str = str(path.expanduser())
    if new_str in paths:
        return False
    paths.append(new_str)
    data.setdefault("skills", {})["paths"] = paths
    _write(data)
    return True


def remove_user_skill_path(path_prefix: str) -> Path | None:
    """Remove a path by exact match or prefix. Returns the removed Path or None."""
    data = _read()
    paths = list(data.get("skills", {}).get("paths", []))
    match: str | None = None
    for p in paths:
        if str(p) == path_prefix or str(p).startswith(path_prefix):
            match = str(p)
            break
    if match is None:
        return None
    paths = [p for p in paths if str(p) != match]
    data.setdefault("skills", {})["paths"] = paths
    _write(data)
    return Path(match)


def set_telegram_token(token: str) -> None:
    data = _read()
    data.setdefault("telegram", {})["bot_token"] = token
    _write(data)


def set_allowed_users(user_ids: list[int]) -> None:
    data = _read()
    data.setdefault("telegram", {})["allowed_users"] = list(user_ids)
    _write(data)


def set_claude_cwd(path: Path) -> None:
    data = _read()
    data.setdefault("claude", {})["cwd"] = str(path)
    _write(data)


def show() -> dict:
    """Return the current config (sanitized — token is masked)."""
    data = _read()
    safe = json.loads(json.dumps(data))
    tok = safe.get("telegram", {}).get("bot_token", "")
    if tok:
        safe["telegram"]["bot_token"] = tok[:8] + "…" + tok[-4:] if len(tok) > 12 else "***"
    return safe
