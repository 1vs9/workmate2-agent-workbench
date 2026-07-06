# -*- coding: utf-8 -*-
"""Persist the task-level chat target selected by a AgentDesk chat turn."""

from __future__ import annotations

import asyncio

from .background_tasks import spawn_background
from .models import ChatRequest
from .session_routing import apply_chat_routing_to_task
from .store import store as agentdesk_store


def persist_task_chat_target(payload: ChatRequest) -> None:
    """Persist task chat routing metadata for reload/reconnect."""
    task = agentdesk_store.get_by_key("tasks", "id", payload.task_id) or agentdesk_store.ensure_task(
        payload.task_id,
    )
    task = apply_chat_routing_to_task(task, payload)
    agentdesk_store.upsert_by_key("tasks", "id", payload.task_id, task)


def schedule_task_chat_target(payload: ChatRequest) -> None:
    spawn_background(asyncio.to_thread(persist_task_chat_target, payload))
