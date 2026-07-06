# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from qwenpaw.agentdesk import team_leader_runs
from qwenpaw.agentdesk.run_status import RUN_STATUS_IDLE, RUN_STATUS_RUNNING


class _FakeWatch:
    def __init__(self) -> None:
        self.cancelled = False
        self._done = False
        self.callbacks = []

    def done(self) -> bool:
        return self._done

    def cancel(self) -> None:
        self.cancelled = True

    def add_done_callback(self, callback) -> None:
        self.callbacks.append(callback)

    def finish(self) -> None:
        self._done = True
        for callback in list(self.callbacks):
            callback(self)


class _FakeTracker:
    def __init__(self, statuses: list[str]) -> None:
        self.statuses = list(statuses)
        self.stopped: list[str] = []

    async def get_status(self, run_key: str) -> str:
        if len(self.statuses) > 1:
            return self.statuses.pop(0)
        return self.statuses[0]

    async def request_stop(self, run_key: str) -> bool:
        self.stopped.append(run_key)
        return True


def test_arm_leader_finalize_watch_cancels_previous(monkeypatch) -> None:
    watches = [_FakeWatch(), _FakeWatch()]

    def _schedule(**kwargs):
        return watches.pop(0)

    monkeypatch.setattr(team_leader_runs, "schedule_run_finalize_watch", _schedule)
    team_leader_runs._leader_finalize_watches.clear()

    team_leader_runs.arm_leader_finalize_watch(
        task_id="task-1",
        run_key="run-1",
        tracker=object(),
    )
    first = team_leader_runs._leader_finalize_watches["task-1"]
    team_leader_runs.arm_leader_finalize_watch(
        task_id="task-1",
        run_key="run-2",
        tracker=object(),
    )

    assert first.cancelled
    assert team_leader_runs._leader_finalize_watches["task-1"] is not first


def test_finished_leader_finalize_watch_discards_registry(monkeypatch) -> None:
    watch = _FakeWatch()
    monkeypatch.setattr(
        team_leader_runs,
        "schedule_run_finalize_watch",
        lambda **kwargs: watch,
    )
    team_leader_runs._leader_finalize_watches.clear()

    team_leader_runs.arm_leader_finalize_watch(
        task_id="task-1",
        run_key="run-1",
        tracker=object(),
    )
    watch.finish()

    assert "task-1" not in team_leader_runs._leader_finalize_watches


@pytest.mark.asyncio
async def test_release_leader_tracker_run_requests_stop_for_running_tracker() -> None:
    tracker = _FakeTracker([RUN_STATUS_RUNNING, RUN_STATUS_IDLE])

    await team_leader_runs.release_leader_tracker_run(tracker, "run-1")

    assert tracker.stopped == ["run-1"]


@pytest.mark.asyncio
async def test_release_leader_tracker_run_ignores_idle_tracker() -> None:
    tracker = _FakeTracker([RUN_STATUS_IDLE])

    await team_leader_runs.release_leader_tracker_run(tracker, "run-1")

    assert tracker.stopped == []
