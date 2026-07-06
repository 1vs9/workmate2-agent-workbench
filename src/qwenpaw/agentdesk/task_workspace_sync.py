# -*- coding: utf-8 -*-
"""AgentDesk task workspace sync scheduling."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .background_tasks import spawn_background
from .store import store


def sync_task_workspace(
    task_id: str,
    agent_id: str,
    workspace_dir: Path | str,
    *,
    employee_name: str | None = None,
) -> None:
    """Persist agent workspace metadata on a task for artifact preview APIs."""

    task = store.ensure_task(task_id)
    resolved = str(Path(workspace_dir).expanduser().resolve())
    updates: dict[str, Any] = {}
    if str(task.get("workspace_dir") or "") != resolved:
        updates["workspace_dir"] = resolved
    if str(task.get("agent_id") or "") != agent_id:
        updates["agent_id"] = agent_id
    if employee_name and str(task.get("employee_name") or "") != employee_name:
        updates["employee_name"] = employee_name
    if updates:
        store.upsert_by_key("tasks", "id", task_id, {**task, **updates})


def schedule_sync_task_workspace(
    task_id: str,
    agent_id: str,
    workspace_dir: Path,
    *,
    employee_name: str | None = None,
) -> None:
    spawn_background(
        asyncio.to_thread(
            sync_task_workspace,
            task_id,
            agent_id,
            workspace_dir,
            employee_name=employee_name,
        ),
    )
