# -*- coding: utf-8 -*-
"""Build AgentDesk React frontend when ``static_next`` is missing or stale."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_PKG_DIR = Path(__file__).resolve().parent
_WEB_DIR = _PKG_DIR / "web"
_STATIC_NEXT_DIR = _PKG_DIR / "static_next"
_SOURCE_ROOTS = (
    "src",
    "public",
    "index.html",
    "vite.config.ts",
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "tsconfig.app.json",
    "tsconfig.node.json",
)


def _env_is_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_is_falsy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"0", "false", "no", "off"}


def newest_source_mtime(
    web_dir: Path | None = None,
    *,
    source_roots: tuple[str, ...] = _SOURCE_ROOTS,
) -> float:
    """Return the newest modification time among tracked frontend source inputs."""
    root = web_dir or _WEB_DIR
    newest = 0.0
    for rel in source_roots:
        path = root / rel
        if path.is_file():
            newest = max(newest, path.stat().st_mtime)
            continue
        if not path.is_dir():
            continue
        for file_path in path.rglob("*"):
            if file_path.is_file():
                newest = max(newest, file_path.stat().st_mtime)
    return newest


def should_build_frontend(
    *,
    web_dir: Path | None = None,
    output_dir: Path | None = None,
) -> bool:
    """Return True when ``static_next`` is missing or older than web sources."""
    if _env_is_falsy("AGENTDESK_FRONTEND_NEXT"):
        return False
    if _env_is_truthy("AGENTDESK_SKIP_FRONTEND_BUILD"):
        return False
    if os.environ.get("AGENTDESK_FRONTEND_DIR", "").strip():
        return False

    out = output_dir or _STATIC_NEXT_DIR
    index = out / "index.html"
    if not index.is_file():
        return True

    build_mtime = index.stat().st_mtime
    return newest_source_mtime(web_dir) > build_mtime


def _find_npm() -> str | None:
    return shutil.which("npm")


def _run_npm(npm: str, args: list[str], *, cwd: Path) -> None:
    cmd = [npm, *args]
    logger.info("Running %s (cwd=%s)", " ".join(cmd), cwd)
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(
            f"npm {' '.join(args)} failed with exit code {completed.returncode}"
            + (f":\n{detail}" if detail else ""),
        )


def ensure_frontend_built(*, force: bool = False) -> bool:
    """Build ``static_next`` when needed.

    Returns True when a usable build exists (built now or already fresh).
    Returns False when build is required but could not be completed.
    """
    if _env_is_falsy("AGENTDESK_FRONTEND_NEXT"):
        return True
    if os.environ.get("AGENTDESK_FRONTEND_DIR", "").strip():
        return True
    if _env_is_truthy("AGENTDESK_SKIP_FRONTEND_BUILD"):
        return (_STATIC_NEXT_DIR / "index.html").is_file()

    if not force and not should_build_frontend():
        logger.info(
            "AgentDesk React frontend is up to date at %s (skip build)",
            _STATIC_NEXT_DIR,
        )
        return True

    npm = _find_npm()
    if npm is None:
        logger.error(
            "AgentDesk React frontend is missing or outdated at %s, but npm was "
            "not found on PATH. Install Node.js from https://nodejs.org/ , then "
            "run: cd src/qwenpaw/agentdesk/web && npm ci && npm run build . "
            "Or set AGENTDESK_SKIP_FRONTEND_BUILD=1 to use the legacy static UI.",
            _STATIC_NEXT_DIR,
        )
        return (_STATIC_NEXT_DIR / "index.html").is_file()

    package_json = _WEB_DIR / "package.json"
    if not package_json.is_file():
        logger.error("AgentDesk frontend package.json not found at %s", package_json)
        return False

    try:
        if not (_WEB_DIR / "node_modules").is_dir():
            logger.info("Installing AgentDesk frontend dependencies (npm ci)...")
            _run_npm(npm, ["ci"], cwd=_WEB_DIR)

        logger.info("Building AgentDesk React frontend (npm run build)...")
        _run_npm(npm, ["run", "build"], cwd=_WEB_DIR)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return (_STATIC_NEXT_DIR / "index.html").is_file()

    if not (_STATIC_NEXT_DIR / "index.html").is_file():
        logger.error(
            "Frontend build finished but %s/index.html is still missing",
            _STATIC_NEXT_DIR,
        )
        return False

    logger.info("AgentDesk React frontend build ready at %s", _STATIC_NEXT_DIR)
    return True
