# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.agentdesk.run_status import (
    RUN_STATUS_IDLE,
    RUN_STATUS_RUNNING,
    RUN_STATUS_STOPPED,
    _bump_run_status_seq,
    commit_task_run_status,
    is_task_running,
    set_task_run_status,
    task_run_status,
)
from qwenpaw.agentdesk.store import AgentDeskStore


def test_commit_task_run_status_persists_product_status(tmp_path) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    store.ensure_task("task-1")

    commit_task_run_status("task-1", RUN_STATUS_RUNNING, persistent_store=store)

    task = store.get_by_key("tasks", "id", "task-1")
    assert task is not None
    assert task["runStatus"] == RUN_STATUS_RUNNING
    assert task_run_status("task-1", persistent_store=store) == RUN_STATUS_RUNNING
    assert is_task_running("task-1", persistent_store=store)


def test_default_store_is_resolved_at_call_time(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr("qwenpaw.agentdesk.run_status.store", store)

    commit_task_run_status("task-1", RUN_STATUS_RUNNING)

    task = store.get_by_key("tasks", "id", "task-1")
    assert task is not None
    assert task["runStatus"] == RUN_STATUS_RUNNING
    assert task_run_status("task-1") == RUN_STATUS_RUNNING
    assert is_task_running("task-1")


def test_stale_run_status_write_cannot_overwrite_terminal_status(tmp_path) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    store.ensure_task("task-1")
    stale_seq = _bump_run_status_seq("task-1")

    commit_task_run_status("task-1", RUN_STATUS_STOPPED, persistent_store=store)
    set_task_run_status(
        "task-1",
        RUN_STATUS_RUNNING,
        seq=stale_seq,
        persistent_store=store,
    )

    assert task_run_status("task-1", persistent_store=store) == RUN_STATUS_STOPPED
    assert not is_task_running("task-1", persistent_store=store)


def test_task_run_status_defaults_to_idle(tmp_path) -> None:
    store = AgentDeskStore(tmp_path / "store.json")

    assert task_run_status("missing", persistent_store=store) == RUN_STATUS_IDLE
