# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio

from qwenpaw.agentdesk import task_workspace_sync
from qwenpaw.agentdesk.store import AgentDeskStore


def test_sync_task_workspace_persists_task_metadata(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(task_workspace_sync, "store", store)
    workspace = tmp_path / "agent-workspace"
    workspace.mkdir()

    task_workspace_sync.sync_task_workspace(
        "task-1",
        "agent-1",
        workspace,
        employee_name="Alice",
    )

    task = store.get_by_key("tasks", "id", "task-1")
    assert task is not None
    assert task["agent_id"] == "agent-1"
    assert task["employee_name"] == "Alice"
    assert task["workspace_dir"] == str(workspace.resolve())


def test_schedule_sync_task_workspace_dispatches_to_router_sync(
    tmp_path,
    monkeypatch,
) -> None:
    calls: list[tuple] = []

    def fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))

        async def _noop() -> None:
            return None

        return _noop()

    spawned: list[object] = []
    monkeypatch.setattr(task_workspace_sync.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(task_workspace_sync, "spawn_background", spawned.append)

    assert task_workspace_sync.schedule_sync_task_workspace(
        "task-1",
        "agent-1",
        tmp_path,
        employee_name="Alice",
    ) is None

    assert calls == [
        (
            task_workspace_sync.sync_task_workspace,
            ("task-1", "agent-1", tmp_path),
            {"employee_name": "Alice"},
        ),
    ]
    assert len(spawned) == 1
    assert asyncio.iscoroutine(spawned[0])
    spawned[0].close()
