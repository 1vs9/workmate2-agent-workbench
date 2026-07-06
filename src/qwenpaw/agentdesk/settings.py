# -*- coding: utf-8 -*-
"""AgentDesk mode configuration."""

from __future__ import annotations

import os
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
_BUNDLED_STATIC_DIR = _PKG_DIR / "static"
_BUNDLED_STATIC_NEXT_DIR = _PKG_DIR / "static_next"


def get_bundled_frontend_dir() -> Path | None:
    """Embedded AgentDesk UI shipped with the agentdesk package."""
    if _BUNDLED_STATIC_DIR.is_dir() and (_BUNDLED_STATIC_DIR / "index.html").is_file():
        return _BUNDLED_STATIC_DIR
    return None


def get_next_frontend_dir() -> Path | None:
    """New React (Vite) build.

    Served by default whenever the ``static_next`` build is present. Set
    ``AGENTDESK_FRONTEND_NEXT`` to a falsy value (``0``/``false``/``no``/``off``)
    to fall back to the legacy vanilla-JS frontend.
    """
    raw = os.environ.get("AGENTDESK_FRONTEND_NEXT", "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return None
    if (
        _BUNDLED_STATIC_NEXT_DIR.is_dir()
        and (_BUNDLED_STATIC_NEXT_DIR / "index.html").is_file()
    ):
        return _BUNDLED_STATIC_NEXT_DIR
    return None


def is_agentdesk_enabled() -> bool:
    raw = os.environ.get("AGENTDESK_ENABLED", "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    if os.environ.get("AGENTDESK_FRONTEND_DIR", "").strip():
        return True
    # Bundled frontend → AgentDesk mode by default in WorkBuddy builds.
    return get_bundled_frontend_dir() is not None


def get_frontend_dir() -> Path | None:
    raw = os.environ.get("AGENTDESK_FRONTEND_DIR", "").strip()
    if raw:
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            return path
        return None
    return get_bundled_frontend_dir()
