# -*- coding: utf-8 -*-
"""Mount embedded AgentDesk frontend when AgentDesk mode is enabled."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .settings import get_frontend_dir, get_next_frontend_dir

logger = logging.getLogger(__name__)

# QwenPaw Console SPA top-level routes — redirect to AgentDesk `/` when embedded.
_LEGACY_QWENPAW_UI_PREFIXES = (
    "chat",
    "coding",
    "channels",
    "sessions",
    "inbox",
    "cron-jobs",
    "heartbeat",
    "skills",
    "skill-pool",
    "market",
    "tools",
    "mcp",
    "acp",
    "workspace",
    "agents",
    "models",
    "environments",
    "agent-config",
    "security",
    "token-usage",
    "agent-stats",
    "voice-transcription",
    "debug",
    "backups",
    "plugin-manager",
    "login",
)


def _redirect_to_agentdesk_root() -> RedirectResponse:
    return RedirectResponse("/", status_code=302)


def register_legacy_qwenpaw_ui_redirects(app: FastAPI) -> None:
    """Send old QwenPaw Console bookmarks to the AgentDesk homepage."""
    for prefix in _LEGACY_QWENPAW_UI_PREFIXES:
        app.add_api_route(
            f"/{prefix}",
            _redirect_to_agentdesk_root,
            methods=["GET"],
            include_in_schema=False,
        )
        app.add_api_route(
            f"/{prefix}/{{_rest:path}}",
            _redirect_to_agentdesk_root,
            methods=["GET"],
            include_in_schema=False,
        )


class SPAStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for client-side routes."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


def mount_agentdesk_frontend(app: FastAPI) -> bool:
    """Mount AgentDesk static frontend at `/` if configured.

    Returns True when mounted (caller should skip QwenPaw console SPA).
    """
    from .frontend_build import ensure_frontend_built

    ensure_frontend_built()
    next_dir = get_next_frontend_dir()
    frontend_dir = next_dir or get_frontend_dir()
    if frontend_dir is None:
        return False

    index = frontend_dir / "index.html"
    if not index.is_file():
        logger.warning(
            "AgentDesk frontend dir %s has no index.html; skip mount",
            frontend_dir,
        )
        return False

    register_legacy_qwenpaw_ui_redirects(app)
    if next_dir is not None:
        app.mount(
            "/",
            SPAStaticFiles(directory=str(frontend_dir), html=True),
            name="agentdesk_frontend",
        )
        logger.info("AgentDesk React frontend mounted from %s", frontend_dir)
    else:
        app.mount(
            "/",
            StaticFiles(directory=str(frontend_dir), html=True),
            name="agentdesk_frontend",
        )
        logger.info("AgentDesk frontend mounted from %s", frontend_dir)
    return True
