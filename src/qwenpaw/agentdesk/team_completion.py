# -*- coding: utf-8 -*-
"""AgentDesk team-mode terminal event snapshots."""

from __future__ import annotations

from typing import Any

from .task_store import task_store
from .trace_events import task_events_snapshot


async def build_team_done_event(task_id: str, *, finalize: bool = True) -> dict[str, Any]:
    """Authoritative terminal snapshot for team-mode turns."""
    if finalize:
        await task_store.finalize_all_streaming_assistant_messages(task_id)
    return {
        "type": "done",
        "messages": await task_store.get_messages(task_id),
        "events": await task_events_snapshot(task_id),
    }
