# -*- coding: utf-8 -*-
"""Persist AgentDesk data-directory preferences for next-process bootstrap."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BOOTSTRAP_DIR = Path.home() / ".agentdesk"
PATHS_FILE = BOOTSTRAP_DIR / "paths.json"


def suggest_paths() -> tuple[str, str]:
    """Return platform-friendly default working/secret directory paths."""
    if sys.platform == "win32" and Path("D:/").exists():
        return r"D:\agentdesk", r"D:\agentdesk.secret"
    home = Path.home() / "agentdesk"
    return str(home), f"{home}.secret"


def upgrade_legacy_saved_paths() -> bool:
    """Rewrite saved ``qwenpaw`` placeholder defaults to ``agentdesk`` paths."""
    if not PATHS_FILE.is_file():
        return False
    saved = load_saved_paths()
    if not saved:
        return False
    working_dir = Path(saved["working_dir"])
    if working_dir.name.lower() != "qwenpaw":
        return False
    allowed_parents = {Path("D:/").resolve(), Path.home().resolve()}
    if working_dir.parent.resolve() not in allowed_parents:
        return False
    new_working_dir, new_secret_dir = suggest_paths()
    save_paths(new_working_dir, new_secret_dir)
    return True


def ensure_default_paths_file() -> bool:
    """Create ``paths.json`` with AgentDesk defaults when nothing is configured yet."""
    if PATHS_FILE.is_file():
        return False
    if Path("~/.copaw").expanduser().exists():
        return False
    working_dir, secret_dir = suggest_paths()
    save_paths(working_dir, secret_dir)
    return True


def load_saved_paths() -> dict[str, str] | None:
    """Read UI-saved paths; returns None when unset or invalid."""
    if not PATHS_FILE.is_file():
        return None
    try:
        raw = json.loads(PATHS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    working_dir = str(raw.get("working_dir") or "").strip()
    if not working_dir:
        return None
    secret_dir = str(raw.get("secret_dir") or "").strip()
    if not secret_dir:
        secret_dir = f"{working_dir}.secret"
    return {"working_dir": working_dir, "secret_dir": secret_dir}


def sync_windows_user_environment(working_dir: str, secret_dir: str) -> None:
    """Persist paths to the Windows user environment for new terminals."""
    if sys.platform != "win32":
        return
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        "Environment",
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(
            key,
            "QWENPAW_WORKING_DIR",
            0,
            winreg.REG_EXPAND_SZ,
            working_dir,
        )
        winreg.SetValueEx(
            key,
            "QWENPAW_SECRET_DIR",
            0,
            winreg.REG_EXPAND_SZ,
            secret_dir,
        )


def save_paths(working_dir: str, secret_dir: str) -> dict[str, str]:
    """Validate, create directories, and persist paths for the next restart."""
    wd, sd = _normalize_pair(working_dir, secret_dir)
    wd.mkdir(parents=True, exist_ok=True)
    sd.mkdir(parents=True, exist_ok=True)
    BOOTSTRAP_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"working_dir": str(wd), "secret_dir": str(sd)}
    PATHS_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sync_windows_user_environment(payload["working_dir"], payload["secret_dir"])
    return payload


def _normalize_pair(working_dir: str, secret_dir: str) -> tuple[Path, Path]:
    wd_text = str(working_dir or "").strip()
    if not wd_text:
        raise ValueError("working_dir is required")
    wd = Path(wd_text).expanduser()
    if not wd.is_absolute():
        raise ValueError("working_dir must be an absolute path")
    sd_text = str(secret_dir or "").strip()
    if not sd_text:
        sd_text = f"{wd}.secret"
    sd = Path(sd_text).expanduser()
    if not sd.is_absolute():
        raise ValueError("secret_dir must be an absolute path")
    return wd.resolve(), sd.resolve()
