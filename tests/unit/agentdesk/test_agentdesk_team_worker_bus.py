# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from qwenpaw.agentdesk.team_worker_bus import (
    TeamWorkerBusBridge,
    team_worker_bus_keys,
)


class _FakeBus:
    def __init__(self) -> None:
        self.queues: dict[str, asyncio.Queue[Any]] = {}
        self.unsubscribed: list[tuple[str, asyncio.Queue[Any]]] = []

    def subscribe(self, key: str) -> asyncio.Queue[Any]:
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self.queues[key] = queue
        return queue

    def unsubscribe(self, key: str, queue: asyncio.Queue[Any]) -> None:
        self.unsubscribed.append((key, queue))


def test_team_worker_bus_keys_dedupes_roster_and_appends_leader() -> None:
    assert team_worker_bus_keys(
        task_id="task-1",
        session_suffix="leader-native",
        roster_members=["Writer", "Writer", "Reviewer"],
    ) == [
        "task-1:team:member:Writer",
        "task-1:team:member:Reviewer",
        "task-1:team:leader-native",
    ]


def test_team_worker_bus_keys_falls_back_to_member_lookup() -> None:
    assert team_worker_bus_keys(
        task_id="task-1",
        session_suffix="leader-native",
        roster_members=[],
        member_lookup={"agent-b": "Writer", "agent-a": "Reviewer"},
    ) == [
        "task-1:team:member:Reviewer",
        "task-1:team:member:Writer",
        "task-1:team:leader-native",
    ]


@pytest.mark.asyncio
async def test_team_worker_bus_bridge_pumps_items_when_enabled() -> None:
    bus = _FakeBus()
    bridge = TeamWorkerBusBridge.subscribe(
        task_id="task-1",
        session_suffix="leader-native",
        roster_members=["Writer"],
        enabled=True,
        bus=bus,
    )

    await bus.queues["task-1:team:member:Writer"].put(("agent-1", "chunk"))
    item = await asyncio.wait_for(bridge.items.get(), timeout=1)
    await bridge.close()

    assert item == ("agent-1", "chunk")
    assert [key for key, _ in bus.unsubscribed] == [
        "task-1:team:member:Writer",
        "task-1:team:leader-native",
    ]


@pytest.mark.asyncio
async def test_team_worker_bus_bridge_does_not_pump_when_disabled() -> None:
    bus = _FakeBus()
    bridge = TeamWorkerBusBridge.subscribe(
        task_id="task-1",
        session_suffix="leader-native",
        roster_members=["Writer"],
        enabled=False,
        bus=bus,
    )

    await bus.queues["task-1:team:member:Writer"].put(("agent-1", "chunk"))
    await asyncio.sleep(0.1)
    await bridge.close()

    assert bridge.items.empty()
    assert len(bus.unsubscribed) == 2
