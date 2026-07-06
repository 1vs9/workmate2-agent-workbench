# -*- coding: utf-8 -*-
"""Abort runs and remove persisted data when a AgentDesk task is deleted."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from ..app.runner.session import sanitize_filename
from ..constant import WORKING_DIR
from .agent_workspace import (
    agent_workspace_dir as _agent_workspace_dir,
    resolve_active_agentdesk_agent_id,
)
from .agents import resolve_agent_id
from .session_bridge import AGENTDESK_SESSION_CHANNEL, AGENTDESK_SESSION_USER_ID
from .store import store
from .task_store import task_store

logger = logging.getLogger(__name__)

_AGENTDESK_USER_ID = AGENTDESK_SESSION_USER_ID
_AGENTDESK_CHANNEL = AGENTDESK_SESSION_CHANNEL


def _resolve_task_agent_id(task_id: str, task: dict[str, Any]) -> str:
    agent_id = str(task.get("agent_id") or "").strip()
    if agent_id:
        return agent_id
    employee_name = str(task.get("employee_name") or "").strip()
    if employee_name:
        return resolve_agent_id(employee_name)
    return resolve_active_agentdesk_agent_id()


def collect_agent_ids(task_id: str, task: dict[str, Any]) -> list[str]:
    """Agent workspaces that may hold session files for this task."""
    seen: set[str] = set()
    ids: list[str] = []

    def add(agent_id: str) -> None:
        aid = str(agent_id or "").strip()
        if aid and aid not in seen:
            seen.add(aid)
            ids.append(aid)

    add(str(task.get("agent_id") or ""))
    employee_name = str(task.get("employee_name") or "").strip()
    if employee_name:
        try:
            add(resolve_agent_id(employee_name))
        except Exception:  # noqa: BLE001
            pass

    team_id = str(task.get("team_id") or "").strip()
    if team_id:
        team = store.get_by_key("teams", "id", team_id) or {}
        add(str(team.get("leader_agent_id") or ""))
        from .employee_agents import ensure_employee_agent_profile

        members = team.get("members") or []
        if isinstance(members, list):
            for member_name in members:
                name = str(member_name or "").strip()
                if not name:
                    continue
                try:
                    add(ensure_employee_agent_profile(name))
                except Exception:  # noqa: BLE001
                    pass

    if not ids:
        add(_resolve_task_agent_id(task_id, task))
    return ids


def _session_matches_task(session_id: str, task_id: str) -> bool:
    sid = str(session_id or "").strip()
    if not sid:
        return False
    if sid == task_id:
        return True
    return sid.startswith(f"{task_id}:team:")


async def _task_chats_for_workspace(workspace: Any, task_id: str) -> list[Any]:
    chat_manager = workspace.chat_manager
    lock = getattr(chat_manager, "_lock", None)
    repo = getattr(chat_manager, "_repo", None)
    if repo is None:
        return []
    if lock is not None:
        async with lock:
            chats = await repo.filter_chats(channel=_AGENTDESK_CHANNEL)
    else:
        chats = await repo.filter_chats(channel=_AGENTDESK_CHANNEL)
    return [chat for chat in chats if _session_matches_task(chat.session_id, task_id)]


async def abort_task_runs(
    task_id: str,
    task: dict[str, Any],
    request: Request | None,
) -> bool:
    """Cancel active streams and clear queued messages for a task."""
    if request is None or not hasattr(request.app.state, "multi_agent_manager"):
        return False

    manager = request.app.state.multi_agent_manager
    stopped = False
    for agent_id in collect_agent_ids(task_id, task):
        try:
            workspace = await manager.get_agent(agent_id)
        except Exception:  # noqa: BLE001
            logger.debug("Skip abort for agent %s (unavailable)", agent_id, exc_info=True)
            continue

        tracker = workspace.task_tracker
        chat_manager = workspace.chat_manager
        channel_manager = workspace.channel_manager
        matched = await _task_chats_for_workspace(workspace, task_id)

        chat_id = await chat_manager.get_chat_id_by_session(task_id, _AGENTDESK_CHANNEL)
        if chat_id and all(chat.id != chat_id for chat in matched):
            placeholder = type("Chat", (), {"id": chat_id, "session_id": task_id})()
            matched.append(placeholder)

        seen_chat_ids: set[str] = set()
        for chat in matched:
            cid = str(getattr(chat, "id", "") or "")
            if not cid or cid in seen_chat_ids:
                continue
            seen_chat_ids.add(cid)
            if await tracker.request_stop(cid):
                stopped = True
            if await chat_manager.delete_chats([cid]):
                stopped = True

        for chat in matched:
            session_id = str(getattr(chat, "session_id", "") or task_id)
            try:
                cleared = await channel_manager.clear_queue(
                    _AGENTDESK_CHANNEL,
                    session_id,
                    20,
                )
            except Exception:  # noqa: BLE001
                cleared = 0
            if cleared > 0:
                stopped = True

    return stopped


def remove_task_session_files(task_id: str, task: dict[str, Any]) -> list[str]:
    """Delete JSON session state files associated with the task."""
    removed: list[str] = []
    safe_task = sanitize_filename(task_id)
    filename_prefix = f"{sanitize_filename(_AGENTDESK_USER_ID)}_{safe_task}"

    for agent_id in collect_agent_ids(task_id, task):
        try:
            workspace_dir = _agent_workspace_dir(agent_id, create=False)
        except HTTPException:
            continue

        sessions_root = workspace_dir / "sessions"
        search_dirs = [sessions_root / _AGENTDESK_CHANNEL, sessions_root]
        for search_dir in search_dirs:
            if not search_dir.is_dir():
                continue
            for path in search_dir.glob(f"{filename_prefix}*.json"):
                try:
                    path.unlink()
                    removed.append(str(path))
                except OSError:
                    logger.warning("Failed to delete session file %s", path, exc_info=True)

            legacy = search_dir / f"{safe_task}.json"
            if legacy.is_file() and task_id in legacy.name:
                try:
                    legacy.unlink()
                    removed.append(str(legacy))
                except OSError:
                    logger.warning("Failed to delete legacy session file %s", legacy, exc_info=True)

    return removed


def remove_task_workspace_dirs(task_id: str, task: dict[str, Any]) -> list[str]:
    """Remove only AgentDesk-owned task-scoped workspace directories."""

    removed: list[str] = []
    owned_root = (
        Path(WORKING_DIR)
        / "agentdesk"
        / "task-workspaces"
        / sanitize_filename(task_id)
    )
    try:
        resolved = owned_root.expanduser().resolve()
        allowed_parent = (
            Path(WORKING_DIR) / "agentdesk" / "task-workspaces"
        ).expanduser().resolve()
        resolved.relative_to(allowed_parent)
    except (OSError, ValueError):
        logger.warning("Refusing to delete unsafe task workspace %s", owned_root)
        return removed
    if not resolved.exists():
        return removed
    try:
        if resolved.is_dir():
            shutil.rmtree(resolved)
        else:
            resolved.unlink()
        removed.append(str(resolved))
    except OSError:
        logger.warning("Failed to delete task workspace %s", resolved, exc_info=True)
    return removed


async def cleanup_task(task_id: str, request: Request | None = None) -> dict[str, Any]:
    """Abort runs, delete persisted files, and remove the task record."""
    task = store.get_by_key("tasks", "id", task_id) or {}
    aborted = await abort_task_runs(task_id, task, request)
    files_removed: list[str] = []
    files_removed.extend(remove_task_session_files(task_id, task))
    files_removed.extend(remove_task_workspace_dirs(task_id, task))
    await task_store.remove_task(task_id)
    deleted = store.delete_by_key("tasks", "id", task_id)
    return {
        "deleted": deleted,
        "id": task_id,
        "aborted": aborted,
        "files_removed": files_removed,
    }
