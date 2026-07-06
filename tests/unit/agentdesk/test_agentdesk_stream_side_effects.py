# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.agentdesk import stream_side_effects
from qwenpaw.agentdesk.run_status import RUN_STATUS_IDLE, RUN_STATUS_RUNNING


class _FakeTracker:
    def __init__(self) -> None:
        self.calls = 0

    async def get_status(self, run_key: str) -> str:
        assert run_key == "run-1"
        self.calls += 1
        if self.calls == 1:
            return RUN_STATUS_RUNNING
        return RUN_STATUS_IDLE


class _FakeTaskStore:
    def __init__(self) -> None:
        self.finalized: list[str] = []
        self.finalized_all: list[str] = []

    async def finalize_assistant_message(self, task_id: str) -> None:
        self.finalized.append(task_id)

    async def finalize_all_streaming_assistant_messages(self, task_id: str) -> None:
        self.finalized_all.append(task_id)


async def test_schedule_run_finalize_watch_finalizes_when_tracker_idle(
    monkeypatch,
) -> None:
    fake_store = _FakeTaskStore()
    committed: list[tuple[str, str]] = []
    monkeypatch.setattr(stream_side_effects, "task_store", fake_store)
    monkeypatch.setattr(
        stream_side_effects,
        "commit_task_run_status",
        lambda task_id, status: committed.append((task_id, status)),
    )
    monkeypatch.setattr(stream_side_effects, "RUN_WATCH_POLL_S", 0)

    watch = stream_side_effects.schedule_run_finalize_watch(
        task_id="task-1",
        run_key="run-1",
        tracker=_FakeTracker(),
    )
    await watch

    assert fake_store.finalized_all == ["task-1"]
    assert fake_store.finalized == []
    assert committed == [("task-1", RUN_STATUS_IDLE)]


async def test_schedule_run_finalize_watch_closes_stale_running_task(monkeypatch) -> None:
    class AlwaysRunningTracker:
        async def get_status(self, run_key: str) -> str:
            assert run_key == "run-1"
            return RUN_STATUS_RUNNING

    fake_store = _FakeTaskStore()
    committed: list[tuple[str, str]] = []
    monkeypatch.setattr(stream_side_effects, "task_store", fake_store)
    monkeypatch.setattr(
        stream_side_effects,
        "commit_task_run_status",
        lambda task_id, status: committed.append((task_id, status)),
    )
    monkeypatch.setattr(stream_side_effects, "RUN_WATCH_POLL_S", 0)

    watch = stream_side_effects.schedule_run_finalize_watch(
        task_id="task-1",
        run_key="run-1",
        tracker=AlwaysRunningTracker(),
        stale_after_s=0,
    )
    await watch

    assert fake_store.finalized_all == ["task-1"]
    assert committed == [("task-1", RUN_STATUS_IDLE)]


def test_schedule_append_assistant_delta_ignores_empty_delta(monkeypatch) -> None:
    spawned: list[object] = []
    monkeypatch.setattr(stream_side_effects, "spawn_background", spawned.append)

    stream_side_effects.schedule_append_assistant_delta("task-1", "")

    assert spawned == []
