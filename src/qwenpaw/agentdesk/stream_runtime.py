# -*- coding: utf-8 -*-
"""Shared AgentDesk streaming runtime helpers."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any, AsyncGenerator, AsyncIterator

from ..app.approvals import get_approval_service

HEARTBEAT_INTERVAL_S = 25.0
# Short poll while waiting for native queue chunks (approval + heartbeat side work).
APPROVAL_POLL_S = 0.05


def tag_turn_event(
    evt: dict[str, Any],
    *,
    sender: str,
    message_id: str | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """Attach speaker + draft id so the client never opens a default-brand shell."""
    tagged = dict(evt)
    if sender and not str(tagged.get("sender") or "").strip():
        tagged["sender"] = sender
    if agent_id and not str(tagged.get("actor_id") or "").strip():
        tagged["actor_id"] = agent_id
    if message_id and not str(tagged.get("message_id") or "").strip():
        tagged["message_id"] = message_id
    return tagged


async def iter_with_heartbeat(
    stream_it: AsyncIterator[str],
    *,
    interval_s: float = HEARTBEAT_INTERVAL_S,
) -> AsyncGenerator[str | None, None]:
    """Yield QwenPaw SSE chunks; yield ``None`` when a heartbeat tick is due."""
    pending: asyncio.Task | None = asyncio.create_task(stream_it.__anext__())
    try:
        while pending is not None:
            done, _ = await asyncio.wait({pending}, timeout=interval_s)
            if pending in done:
                try:
                    yield pending.result()
                except StopAsyncIteration:
                    break
                pending = asyncio.create_task(stream_it.__anext__())
            else:
                yield None
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            with suppress(asyncio.CancelledError):
                await pending


async def pending_approval_event(task_id: str) -> dict | None:
    """Return a AgentDesk ``approval_required`` event when a tool awaits approval."""

    if not task_id:
        return None
    svc = get_approval_service()
    pending = await svc.get_pending_by_session(task_id)
    if pending is None:
        pending_list = await svc.get_pending_by_root_session(task_id)
        pending = pending_list[0] if pending_list else None
    if pending is None or pending.status != "pending":
        return None
    return {
        "type": "approval_required",
        "task_id": task_id,
        "request_id": pending.request_id,
        "tool_name": pending.tool_name,
        "severity": pending.severity,
        "detail": pending.result_summary,
    }
