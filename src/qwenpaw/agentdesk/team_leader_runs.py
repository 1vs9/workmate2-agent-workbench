# -*- coding: utf-8 -*-
"""Team leader native-run lifecycle helpers."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .run_status import RUN_STATUS_RUNNING
from .stream_side_effects import schedule_run_finalize_watch

logger = logging.getLogger(__name__)

# Time to wait after a leader turn's stream ends for the lingering native
# tracker run to be released before forcing an explicit stop.
TEAM_LEADER_TRACKER_RELEASE_WAIT_S = 2.0

# Per-task leader run-finalize watches. Each leader turn reuses the same native
# leader chat, so the previous watch must be cancelled before the next round can
# reopen the leader message safely.
_leader_finalize_watches: dict[str, "asyncio.Task[Any]"] = {}


def cancel_leader_finalize_watch(task_id: str) -> None:
    """Drop any in-flight leader finalize watch without running its tail."""
    prev = _leader_finalize_watches.pop(task_id, None)
    if prev is not None and not prev.done():
        prev.cancel()


def arm_leader_finalize_watch(*, task_id: str, run_key: str, tracker: Any) -> None:
    """Arm a producer-tied watch for a team leader native run."""
    cancel_leader_finalize_watch(task_id)
    watch = schedule_run_finalize_watch(
        task_id=task_id,
        run_key=run_key,
        tracker=tracker,
    )
    if watch is None:
        return
    _leader_finalize_watches[task_id] = watch

    def _discard(done_task: "asyncio.Task[Any]") -> None:
        if _leader_finalize_watches.get(task_id) is done_task:
            _leader_finalize_watches.pop(task_id, None)

    watch.add_done_callback(_discard)


async def release_leader_tracker_run(tracker: Any, run_key: str) -> None:
    """Request stop if a leader tracker run is still active after stream end."""
    try:
        if await tracker.get_status(run_key) != RUN_STATUS_RUNNING:
            return
    except Exception:  # noqa: BLE001 - status probe is best-effort
        return
    request_stop = getattr(tracker, "request_stop", None)
    if request_stop is None:
        return
    logger.warning(
        "Leader tracker run %s still RUNNING after stream end; requesting "
        "explicit stop to release it for the next round.",
        run_key,
    )
    try:
        await request_stop(run_key)
    except Exception:  # noqa: BLE001 - release is best-effort
        logger.warning(
            "Failed to release lingering leader tracker run %s",
            run_key,
            exc_info=True,
        )
        return
    deadline = time.monotonic() + TEAM_LEADER_TRACKER_RELEASE_WAIT_S
    while time.monotonic() < deadline:
        try:
            if await tracker.get_status(run_key) != RUN_STATUS_RUNNING:
                return
        except Exception:  # noqa: BLE001
            return
        await asyncio.sleep(0.05)
    logger.error(
        "Leader tracker run %s did not release after explicit stop; the next "
        "round may attach to a stale run.",
        run_key,
    )
