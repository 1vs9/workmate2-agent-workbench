# -*- coding: utf-8 -*-
"""Read AgentDesk display messages from QwenPaw session history."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app.inbox_trace_store import flatten_session_messages
from ..app.runner.utils import session_state_to_messages
from ..schemas import Message
from .message_projection import messages_for_client
from .session_bridge import (
    AGENTDESK_SESSION_CHANNEL,
    AGENTDESK_SESSION_USER_ID,
    build_agentdesk_session,
)

def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                    continue
                nested = item.get("content")
                if isinstance(nested, str):
                    parts.append(nested)
                    continue
            text = getattr(item, "text", None)
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)
    return str(content)


def _value_as_str(value: Any) -> str:
    if value is None:
        return ""
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    return str(value)


def _runtime_content_to_text(content: list[Any]) -> str:
    parts: list[str] = []
    for item in content:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            parts.append(text)
            continue
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _runtime_message_to_task_message(
    session_id: str,
    index: int,
    msg: Message,
) -> dict[str, Any] | None:
    content = _runtime_content_to_text(list(msg.content or []))
    if not content:
        return None

    metadata = msg.metadata if isinstance(msg.metadata, dict) else {}
    nested_metadata = metadata.get("metadata")
    if not isinstance(nested_metadata, dict):
        nested_metadata = {}
    sender = metadata.get("original_name") or nested_metadata.get("sender")
    message_id = metadata.get("original_id") or msg.id or f"{session_id}:{index}"

    out: dict[str, Any] = {
        "id": str(message_id),
        "role": _value_as_str(msg.role) or "assistant",
        "content": content,
        "streaming": False,
        "artifacts": [],
    }
    timestamp = metadata.get("timestamp")
    if timestamp is not None:
        out["updatedAt"] = timestamp
    if sender:
        out["sender"] = str(sender)
    return out


def _raw_session_message_to_task_message(
    session_id: str,
    index: int,
    msg: dict[str, Any],
) -> dict[str, Any] | None:
    role = str(msg.get("role") or "").strip() or "assistant"
    content = _content_to_text(msg.get("content"))
    if not content:
        return None

    metadata = msg.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    nested_metadata = metadata.get("metadata")
    if not isinstance(nested_metadata, dict):
        nested_metadata = {}

    sender = (
        msg.get("sender")
        or msg.get("name")
        or metadata.get("original_name")
        or nested_metadata.get("sender")
    )
    message_id = msg.get("id") or metadata.get("original_id") or f"{session_id}:{index}"

    out: dict[str, Any] = {
        "id": str(message_id),
        "role": role,
        "content": content,
        "streaming": False,
        "artifacts": [],
    }
    timestamp = msg.get("timestamp") or metadata.get("timestamp")
    if timestamp is not None:
        out["updatedAt"] = timestamp
    if sender:
        out["sender"] = str(sender)
    return out


async def read_agentdesk_session_messages(
    session_id: str,
    *,
    working_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Project QwenPaw shared session history into AgentDesk task messages."""

    session = build_agentdesk_session(working_dir=working_dir)
    state = await session.get_session_state_dict(
        session_id=session_id,
        user_id=AGENTDESK_SESSION_USER_ID,
        channel=AGENTDESK_SESSION_CHANNEL,
        allow_not_exist=True,
    )
    agent_state = state.get("agent")
    if not isinstance(agent_state, dict):
        return []

    task_messages: list[dict[str, Any]] = []
    for index, msg in enumerate(session_state_to_messages(state)):
        task_msg = _runtime_message_to_task_message(session_id, index, msg)
        if task_msg is not None:
            task_messages.append(task_msg)
    if task_messages:
        return messages_for_client(task_messages)

    raw_state = agent_state.get("state")
    if not isinstance(raw_state, dict):
        return []
    for index, msg in enumerate(flatten_session_messages(raw_state.get("context"))):
        task_msg = _raw_session_message_to_task_message(session_id, index, msg)
        if task_msg is not None:
            task_messages.append(task_msg)
    return messages_for_client(task_messages)
