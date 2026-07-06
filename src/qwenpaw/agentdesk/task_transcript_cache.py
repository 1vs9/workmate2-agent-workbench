# -*- coding: utf-8 -*-
"""Temporary AgentDesk transcript cache boundary.

This wraps the current JSON-backed task transcript reads/writes. It is not the
target source of truth; it exists so TaskStore no longer reaches directly into
AgentDeskStore for every message persistence operation while we migrate toward
QwenPaw session history as canonical runtime state.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from .store import AgentDeskStore, store


class TaskTranscriptCache:
    def __init__(self, persistent_store: AgentDeskStore | None = None) -> None:
        self._store = persistent_store or store

    async def load_task(self, task_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._store.get_by_key, "tasks", "id", task_id)

    async def ensure_task(self, task_id: str, *, title: str | None = None) -> None:
        await asyncio.to_thread(self._store.ensure_task, task_id, title=title)

    async def replace_messages(
        self,
        task_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        await asyncio.to_thread(
            self._store.replace_task_messages,
            task_id,
            deepcopy(messages),
        )

    async def replace_team_timeline(
        self,
        task_id: str,
        timeline: list[dict[str, Any]],
    ) -> None:
        await asyncio.to_thread(
            self._store.replace_team_timeline,
            task_id,
            deepcopy(timeline),
        )

    async def get_team_timeline(self, task_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._store.get_team_timeline, task_id)
