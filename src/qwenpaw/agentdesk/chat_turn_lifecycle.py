# -*- coding: utf-8 -*-
"""Lifecycle helpers for AgentDesk chat turns."""

from __future__ import annotations

from .run_status import RUN_STATUS_IDLE, commit_task_run_status
from .task_store import task_store


async def finalize_failed_turn(
    task_id: str,
    *,
    sender: str,
    content: str,
    stream_turn_started: bool,
) -> None:
    """Close the assistant placeholder after a pre-stream or mid-stream failure."""
    if stream_turn_started:
        await task_store.finalize_assistant_message(task_id, content=content)
    else:
        await task_store.begin_assistant_message(task_id, sender=sender)
        await task_store.finalize_assistant_message(task_id, content=content)
    commit_task_run_status(task_id, RUN_STATUS_IDLE)
