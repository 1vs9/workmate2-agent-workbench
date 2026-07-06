# -*- coding: utf-8 -*-
"""Worker stream bus lifecycle helpers for AgentDesk team mode."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from ..runtime.worker_stream_bus import WorkerStreamBus, worker_stream_bus
from .team_sessions import team_member_session_id, team_session_id


def team_worker_bus_keys(
    *,
    task_id: str,
    session_suffix: str,
    roster_members: list[str] | None = None,
    member_lookup: dict[str, str] | None = None,
) -> list[str]:
    """Return deduped worker bus keys for roster members plus the leader bus."""
    keys: list[str] = []
    resolved_roster = [str(member).strip() for member in (roster_members or []) if str(member).strip()]
    if member_lookup is not None and not resolved_roster:
        resolved_roster = sorted({str(value).strip() for value in member_lookup.values() if str(value).strip()})
    for member in resolved_roster:
        member_key = team_member_session_id(task_id, member)
        if member_key not in keys:
            keys.append(member_key)
    leader_key = team_session_id(task_id, session_suffix)
    if leader_key not in keys:
        keys.append(leader_key)
    return keys


class TeamWorkerBusBridge:
    """Subscribe worker bus keys and pump all items into a single async queue."""

    def __init__(
        self,
        *,
        keys: list[str],
        enabled: bool,
        bus: WorkerStreamBus = worker_stream_bus,
    ) -> None:
        self.items: asyncio.Queue[Any] = asyncio.Queue()
        self._bus = bus
        self._stop = asyncio.Event()
        self._queues = [(key, bus.subscribe(key)) for key in keys]
        self._tasks: list[asyncio.Task[None]] = []
        if enabled:
            for _, queue in self._queues:
                self._tasks.append(asyncio.create_task(self._pump_one(queue)))

    @classmethod
    def subscribe(
        cls,
        *,
        task_id: str,
        session_suffix: str,
        roster_members: list[str] | None = None,
        member_lookup: dict[str, str] | None = None,
        enabled: bool,
        bus: WorkerStreamBus = worker_stream_bus,
    ) -> "TeamWorkerBusBridge":
        return cls(
            keys=team_worker_bus_keys(
                task_id=task_id,
                session_suffix=session_suffix,
                roster_members=roster_members,
                member_lookup=member_lookup,
            ),
            enabled=enabled,
            bus=bus,
        )

    async def _pump_one(self, queue: asyncio.Queue[Any]) -> None:
        while not self._stop.is_set():
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            await self.items.put(item)

    async def close(self) -> None:
        self._stop.set()
        for task in self._tasks:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        for key, queue in self._queues:
            self._bus.unsubscribe(key, queue)
        self._queues.clear()
