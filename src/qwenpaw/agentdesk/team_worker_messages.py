# -*- coding: utf-8 -*-
"""Worker assistant message helpers for AgentDesk team mode."""

from __future__ import annotations

from typing import Any

from .task_store import task_store
from .team_sessions import team_member_session_id


async def begin_worker_assistant_message(
    task_id: str,
    member_name: str,
) -> dict[str, Any]:
    """Open a detached worker bubble keyed by roster name + member session id."""
    return await task_store.begin_assistant_message(
        task_id,
        sender=member_name,
        set_streaming=False,
        session_id=team_member_session_id(task_id, member_name),
    )


async def resolve_member_watch_message_id(
    task_id: str,
    member_name: str,
) -> str | None:
    """Find the member bubble to attach bus content to."""
    existing = await task_store.get_assistant_messages_by_sender(task_id, member_name)
    return reusable_member_message_id(existing)


def reusable_member_message_id(messages: list[dict[str, Any]]) -> str | None:
    """Return the newest streaming or empty assistant message id."""
    for msg in reversed(messages):
        message_id = str(msg.get("id") or "").strip()
        if not message_id:
            continue
        if msg.get("streaming"):
            return message_id
        if not str(msg.get("content") or "").strip():
            return message_id
    return None
