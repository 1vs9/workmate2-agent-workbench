# -*- coding: utf-8 -*-
"""AgentDesk product run-status adapter.

This is display/session metadata, not the runtime source of truth. QwenPaw's
TaskTracker owns live execution state; AgentDesk stores a small projected status
so the product sidebar and reconnect UI can render quickly during migration.
"""

from __future__ import annotations

from .store import AgentDeskStore, store

RUN_STATUS_IDLE = "idle"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_STOPPED = "stopped"

# Guards against stale ``running`` writes arriving after a synchronous terminal
# commit when a stream ends quickly.
_run_status_seq: dict[str, int] = {}


def _persistent_store(persistent_store: AgentDeskStore | None = None) -> AgentDeskStore:
    return persistent_store or store


def _bump_run_status_seq(task_id: str) -> int:
    seq = _run_status_seq.get(task_id, 0) + 1
    _run_status_seq[task_id] = seq
    return seq


def set_task_run_status(
    task_id: str,
    status: str,
    *,
    seq: int | None = None,
    persistent_store: AgentDeskStore | None = None,
) -> None:
    if seq is not None and seq != _run_status_seq.get(task_id):
        return
    target_store = _persistent_store(persistent_store)
    task = target_store.get_by_key("tasks", "id", task_id)
    if task is None:
        task = target_store.ensure_task(task_id)
    task["runStatus"] = status
    target_store.upsert_by_key("tasks", "id", task_id, task)


def commit_task_run_status(
    task_id: str,
    status: str,
    *,
    persistent_store: AgentDeskStore | None = None,
) -> None:
    """Synchronously persist runStatus and invalidate stale scheduled writes."""
    seq = _bump_run_status_seq(task_id)
    set_task_run_status(
        task_id,
        status,
        seq=seq,
        persistent_store=persistent_store,
    )


def task_run_status(
    task_id: str,
    *,
    persistent_store: AgentDeskStore | None = None,
) -> str:
    task = _persistent_store(persistent_store).get_by_key("tasks", "id", task_id) or {}
    return str(task.get("runStatus") or RUN_STATUS_IDLE)


def is_task_running(
    task_id: str,
    *,
    persistent_store: AgentDeskStore | None = None,
) -> bool:
    return task_run_status(task_id, persistent_store=persistent_store) == RUN_STATUS_RUNNING
