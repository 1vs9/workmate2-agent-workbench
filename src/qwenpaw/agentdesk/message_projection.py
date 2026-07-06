# -*- coding: utf-8 -*-
"""AgentDesk message projection helpers.

AgentDesk's current branch still keeps a display cache of task messages while
the replatform moves canonical history back toward QwenPaw sessions. Keep UI
projection rules here so TaskStore can shrink toward "cache + write pointer"
instead of owning presentation semantics.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .user_message_display import display_user_message_content

_LEADER_SUFFIX_SEPARATORS = {"\u00b7", " ", "-", "_"}


def _is_hidden_leader_sender(sender_key: str, leader_key: str) -> bool:
    if not sender_key:
        return False
    if sender_key == leader_key:
        return True
    if not sender_key.endswith("leader"):
        return False
    prefix = sender_key[: -len("leader")]
    return bool(prefix) and prefix[-1] in _LEADER_SUFFIX_SEPARATORS


def message_for_client(msg: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(msg)
    if out.get("role") == "user":
        out["content"] = display_user_message_content(str(out.get("content") or ""))
    return out


def messages_for_client(messages: list[Any]) -> list[dict[str, Any]]:
    return [message_for_client(msg) for msg in messages if isinstance(msg, dict)]


def assistant_messages_by_sender(
    messages: list[dict[str, Any]],
    sender: str,
) -> list[dict[str, Any]]:
    target_key = str(sender or "").strip().lower()
    if not target_key:
        return []
    return [
        message_for_client(msg)
        for msg in messages
        if msg.get("role") == "assistant"
        and str(msg.get("sender") or "").strip().lower() == target_key
    ]


def streaming_member_assistant_messages(
    messages: list[dict[str, Any]],
    *,
    leader_sender: str,
) -> list[dict[str, Any]]:
    leader_key = str(leader_sender or "").strip().lower()
    out: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("role") != "assistant" or not msg.get("streaming"):
            continue
        sender_key = str(msg.get("sender") or "").strip().lower()
        if _is_hidden_leader_sender(sender_key, leader_key):
            continue
        out.append(deepcopy(msg))
    return out
