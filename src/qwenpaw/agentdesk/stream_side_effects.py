# -*- coding: utf-8 -*-
"""Shared AgentDesk stream side effects."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from .background_tasks import spawn_background
from .run_status import (
    RUN_STATUS_IDLE,
    RUN_STATUS_RUNNING,
    commit_task_run_status,
)
from .task_store import task_store

RUN_WATCH_POLL_S = 0.25
RUN_WATCH_STALE_S = 10 * 60


def schedule_append_assistant_delta(
    task_id: str,
    delta: str,
    *,
    message_id: str | None = None,
) -> None:
    """Persist assistant text without blocking the SSE consumer loop."""

    if not delta:
        return
    spawn_background(
        task_store.append_assistant_delta(task_id, delta, message_id=message_id),
    )


async def wait_tracker_idle(
    tracker: Any,
    run_key: str,
    *,
    stale_after_s: float | None = RUN_WATCH_STALE_S,
) -> bool:
    """Block until TaskTracker reports idle; return False when stale."""

    started_at = time.monotonic()
    while await tracker.get_status(run_key) == RUN_STATUS_RUNNING:
        if stale_after_s is not None and time.monotonic() - started_at >= stale_after_s:
            return False
        await asyncio.sleep(RUN_WATCH_POLL_S)
    return True


def schedule_run_finalize_watch(
    *,
    task_id: str,
    run_key: str,
    tracker: Any,
    commit_run_status: bool = True,
    finalize_message: bool = True,
    stale_after_s: float | None = RUN_WATCH_STALE_S,
) -> asyncio.Task[Any]:
    """Finalize persisted messages when the tracker run ends or goes stale."""

    async def _watch() -> None:
        try:
            await wait_tracker_idle(
                tracker,
                run_key,
                stale_after_s=stale_after_s,
            )
        except asyncio.CancelledError:
            return
        if finalize_message:
            finalize_all = getattr(
                task_store,
                "finalize_all_streaming_assistant_messages",
                None,
            )
            if callable(finalize_all):
                await finalize_all(task_id)
            else:  # pragma: no cover - compatibility for tiny test doubles
                await task_store.finalize_assistant_message(task_id)
        if commit_run_status:
            commit_task_run_status(task_id, RUN_STATUS_IDLE)

    return spawn_background(_watch())
