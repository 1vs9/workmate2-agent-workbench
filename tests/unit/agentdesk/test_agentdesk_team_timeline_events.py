# -*- coding: utf-8 -*-
from __future__ import annotations

import json

import pytest

from qwenpaw.agentdesk import team_timeline_events
from qwenpaw.agentdesk.stream_protocol import StreamEventSequencer


class _FakeTaskStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.entries: list[tuple[str, dict[str, object]]] = []

    async def append_team_timeline_entry(
        self,
        task_id: str,
        entry: dict[str, object],
    ) -> dict[str, object]:
        self.entries.append((task_id, entry))
        if self.fail:
            raise RuntimeError("store unavailable")
        return {**entry, "persisted": True}


def _decode_sse(line: str) -> dict[str, object]:
    assert line.startswith("data: ")
    return json.loads(line.removeprefix("data: ").strip())


@pytest.mark.asyncio
async def test_timeline_sse_from_entry_persists_and_wraps(monkeypatch) -> None:
    fake_store = _FakeTaskStore()
    monkeypatch.setattr(team_timeline_events, "task_store", fake_store)
    sequencer = StreamEventSequencer(task_id="task-1", round_id="round-1")

    line = await team_timeline_events.timeline_sse_from_entry(
        task_id="task-1",
        entry={"kind": "phase", "actor": "leader", "seq": 0, "round_id": "round-1"},
        sequencer=sequencer,
    )

    payload = _decode_sse(line)
    assert fake_store.entries == [
        (
            "task-1",
            {"kind": "phase", "actor": "leader", "seq": 0, "round_id": "round-1"},
        ),
    ]
    assert payload["type"] == "timeline_entry"
    assert payload["persisted"] is True
    assert payload["task_id"] == "task-1"
    assert payload["source"] == "team"


@pytest.mark.asyncio
async def test_timeline_sse_from_entry_falls_back_when_persist_fails(monkeypatch) -> None:
    fake_store = _FakeTaskStore(fail=True)
    monkeypatch.setattr(team_timeline_events, "task_store", fake_store)
    sequencer = StreamEventSequencer(task_id="task-1", round_id="round-1")

    line = await team_timeline_events.timeline_sse_from_entry(
        task_id="task-1",
        entry={"kind": "phase", "actor": "leader", "seq": 0, "round_id": "round-1"},
        sequencer=sequencer,
    )

    payload = _decode_sse(line)
    assert payload["type"] == "timeline_entry"
    assert payload["kind"] == "phase"
    assert "persisted" not in payload


@pytest.mark.asyncio
async def test_timeline_sse_lines_for_event_returns_empty_without_writer() -> None:
    sequencer = StreamEventSequencer(task_id="task-1", round_id="round-1")

    lines = await team_timeline_events.timeline_sse_lines_for_event(
        task_id="task-1",
        timeline_writer=None,
        mapped_evt={"type": "team_phase", "phase": "thinking"},
        sequencer=sequencer,
    )

    assert lines == []
