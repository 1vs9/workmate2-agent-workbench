# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from qwenpaw.agentdesk import team_completion


class _FakeTaskStore:
    def __init__(self) -> None:
        self.finalized: list[str] = []

    async def finalize_all_streaming_assistant_messages(self, task_id: str) -> None:
        self.finalized.append(task_id)

    async def get_messages(self, task_id: str) -> list[dict[str, str]]:
        return [{"role": "assistant", "content": f"done:{task_id}"}]


@pytest.mark.asyncio
async def test_build_team_done_event_finalizes_and_includes_events(monkeypatch) -> None:
    fake_store = _FakeTaskStore()
    monkeypatch.setattr(team_completion, "task_store", fake_store)
    monkeypatch.setattr(
        team_completion,
        "task_events_snapshot",
        lambda task_id: _events(task_id),
    )

    payload = await team_completion.build_team_done_event("task-1")

    assert fake_store.finalized == ["task-1"]
    assert payload == {
        "type": "done",
        "messages": [{"role": "assistant", "content": "done:task-1"}],
        "events": [{"type": "trace", "task_id": "task-1"}],
    }


@pytest.mark.asyncio
async def test_build_team_done_event_can_skip_finalize(monkeypatch) -> None:
    fake_store = _FakeTaskStore()
    monkeypatch.setattr(team_completion, "task_store", fake_store)
    monkeypatch.setattr(
        team_completion,
        "task_events_snapshot",
        lambda task_id: _events(task_id),
    )

    payload = await team_completion.build_team_done_event("task-1", finalize=False)

    assert fake_store.finalized == []
    assert payload["events"] == [{"type": "trace", "task_id": "task-1"}]


async def _events(task_id: str) -> list[dict[str, str]]:
    return [{"type": "trace", "task_id": task_id}]
