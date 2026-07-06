# -*- coding: utf-8 -*-
"""Team leader native chat resolution helpers."""

from __future__ import annotations

from typing import Any

from ..app.agent_context import get_agent_for_request
from ..app.routers.console import _extract_placeholder_name
from .native_payload import build_agentdesk_native_payload
from .session_bridge import AGENTDESK_SESSION_CHANNEL
from .team_sessions import TEAM_LEADER_SESSION_SUFFIX, team_session_id


async def resolve_team_leader_chat(
    *,
    task_id: str,
    request: Any,
    leader_agent_id: str,
) -> tuple[Any, str] | None:
    """Return ``(workspace, chat_id)`` for the team leader native session."""
    request.state.agent_id = leader_agent_id
    workspace = await get_agent_for_request(request, agent_id=leader_agent_id)
    console_channel = await workspace.channel_manager.get_channel(AGENTDESK_SESSION_CHANNEL)
    if console_channel is None:
        return None
    session_id = team_session_id(task_id, TEAM_LEADER_SESSION_SUFFIX)
    native_payload = build_agentdesk_native_payload(
        task_id=session_id,
        message="",
        agent_id=leader_agent_id,
    )
    resolved = console_channel.resolve_session_id(
        sender_id=native_payload["sender_id"],
        channel_meta=native_payload["meta"],
    )
    name, _first_text = _extract_placeholder_name(native_payload["content_parts"])
    chat = await workspace.chat_manager.get_or_create_chat(
        resolved,
        native_payload["sender_id"],
        native_payload["channel_id"],
        name=name or "AgentDesk",
    )
    return workspace, chat.id
