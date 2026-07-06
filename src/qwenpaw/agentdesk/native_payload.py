# -*- coding: utf-8 -*-
"""AgentDesk native console payload construction."""

from __future__ import annotations

from qwenpaw.schemas import ContentType, TextContent

from .session_bridge import AGENTDESK_SESSION_CHANNEL, AGENTDESK_SESSION_USER_ID


def build_agentdesk_native_payload(
    *,
    task_id: str,
    message: str,
    agent_id: str,
) -> dict:
    content_parts = [TextContent(type=ContentType.TEXT, text=message)]
    return {
        "channel_id": AGENTDESK_SESSION_CHANNEL,
        "sender_id": AGENTDESK_SESSION_USER_ID,
        "content_parts": content_parts,
        "meta": {
            "session_id": task_id,
            "user_id": AGENTDESK_SESSION_USER_ID,
            "agent_id": agent_id,
        },
    }
