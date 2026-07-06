# -*- coding: utf-8 -*-
"""AgentDesk team timeline SSE projection helpers."""

from __future__ import annotations

import logging
from typing import Any

from .sse import sse_line
from .stream_protocol import StreamEventSequencer
from .task_store import task_store
from .team_timeline import TeamTimelineWriter

logger = logging.getLogger(__name__)


async def timeline_sse_from_entry(
    *,
    task_id: str,
    entry: dict[str, Any],
    sequencer: StreamEventSequencer,
) -> str:
    try:
        persisted = await task_store.append_team_timeline_entry(task_id, entry)
    except Exception:
        logger.warning(
            "Failed to persist team timeline for task %s",
            task_id,
            exc_info=True,
        )
        persisted = entry
    return sse_line(sequencer.wrap({"type": "timeline_entry", **persisted}, source="team"))


async def timeline_sse_lines_for_event(
    *,
    task_id: str,
    timeline_writer: TeamTimelineWriter | None,
    mapped_evt: dict[str, Any],
    sequencer: StreamEventSequencer,
    leader_message_id: str | None = None,
    worker_message_ids: dict[str, str] | None = None,
    resolve_actor: Any = None,
) -> list[str]:
    if timeline_writer is None:
        return []
    entry = timeline_writer.entry_from_mapped_event(
        mapped_evt,
        leader_message_id=leader_message_id,
        worker_message_ids=worker_message_ids,
        resolve_actor=resolve_actor,
    )
    if entry is None:
        return []
    return [
        await timeline_sse_from_entry(
            task_id=task_id,
            entry=entry,
            sequencer=sequencer,
        ),
    ]
