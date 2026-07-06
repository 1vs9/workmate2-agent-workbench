# -*- coding: utf-8 -*-
"""AgentDesk task workspace endpoint orchestration helpers."""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .task_workspace_files import (
    resolve_task_workspace_file,
    task_workspace_roots,
    task_workspace_tree_files,
)


def reveal_path_in_os(path: Path) -> None:
    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise HTTPException(status_code=404, detail="File not found")
    system = platform.system()
    try:
        if system == "Windows":
            if resolved.is_dir():
                subprocess.run(["explorer", str(resolved)], check=False)
            else:
                subprocess.run(
                    ["explorer", f"/select,{resolved}"],
                    check=False,
                )
        elif system == "Darwin":
            subprocess.run(["open", "-R", str(resolved)], check=False)
        else:
            target = resolved if resolved.is_dir() else resolved.parent
            subprocess.run(["xdg-open", str(target)], check=False)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reveal path: {exc}",
        ) from exc


def task_workspace_tree_payload(task_id: str) -> dict[str, Any]:
    return {"files": task_workspace_tree_files(task_id)}


def task_workspace_file_payload(task_id: str, path: str) -> dict[str, Any]:
    file_path = resolve_task_workspace_file(task_id, path)
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"path": path, "content": "", "lines": [], "binary": True}
    return {
        "path": path,
        "content": content,
        "lines": content.splitlines(),
        "binary": False,
    }


def reveal_task_workspace_payload(
    task_id: str,
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    rel_path = str(dict(body or {}).get("path") or "").strip()
    if not rel_path:
        raise HTTPException(status_code=400, detail="path is required")
    try:
        file_path = resolve_task_workspace_file(task_id, rel_path)
        reveal_path_in_os(file_path)
        return {"ok": True, "path": file_path.as_posix()}
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        roots = task_workspace_roots(task_id, persist_fallback=True)
        if not roots:
            raise
        reveal_path_in_os(roots[0])
        return {"ok": True, "path": str(roots[0]), "revealed": "folder"}
