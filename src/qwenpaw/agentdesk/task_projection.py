# -*- coding: utf-8 -*-
"""AgentDesk task record projection helpers."""

from __future__ import annotations

from typing import Any

from .message_projection import messages_for_client


def task_sort_key(task: dict[str, Any]) -> float:
    for field in ("created_at", "updated_at"):
        value = task.get(field)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def task_for_client(task: dict[str, Any]) -> dict[str, Any]:
    out = dict(task)
    messages = task.get("messages")
    out["messages"] = messages_for_client(messages if isinstance(messages, list) else [])
    created_at = task.get("created_at")
    if created_at is not None:
        out["createdAt"] = created_at
    return out
