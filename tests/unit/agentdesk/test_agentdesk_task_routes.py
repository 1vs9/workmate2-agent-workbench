# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

import pytest

from qwenpaw.agentdesk import task_routes
from qwenpaw.agentdesk.store import AgentDeskStore


def test_list_task_payloads_sorts_and_projects(monkeypatch, tmp_path) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(task_routes, "store", store)
    store.upsert_by_key("tasks", "id", "older", {"title": "Older", "created_at": 1})
    store.upsert_by_key("tasks", "id", "newer", {"title": "Newer", "created_at": 2})

    payloads = task_routes.list_task_payloads()

    assert [item["id"] for item in payloads] == ["newer", "older"]


@pytest.mark.asyncio
async def test_get_task_payload_prefers_live_messages(monkeypatch, tmp_path) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(task_routes, "store", store)
    store.upsert_by_key(
        "tasks",
        "id",
        "task-1",
        {"id": "task-1", "title": "Saved", "messages": [{"content": "saved"}]},
    )

    class FakeTaskStore:
        async def ensure_task(self, task_id: str) -> None:
            assert task_id == "task-1"

        async def get_messages(self, task_id: str):
            assert task_id == "task-1"
            return [{"role": "user", "content": "live"}]

    monkeypatch.setitem(
        __import__("sys").modules,
        "qwenpaw.agentdesk.task_store",
        SimpleNamespace(task_store=FakeTaskStore()),
    )

    payload = await task_routes.get_task_payload("task-1")

    assert payload["messages"] == [{"role": "user", "content": "live"}]


@pytest.mark.asyncio
async def test_delete_task_payload_delegates_to_cleanup(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []

    async def _cleanup(task_id: str, request: object):
        calls.append((task_id, request))
        return {"deleted": True, "id": task_id}

    monkeypatch.setitem(
        __import__("sys").modules,
        "qwenpaw.agentdesk.task_cleanup",
        SimpleNamespace(cleanup_task=_cleanup),
    )

    request = object()

    assert await task_routes.delete_task_payload("task-1", request) == {
        "deleted": True,
        "id": "task-1",
    }
    assert calls == [("task-1", request)]


def test_task_stats_payload_counts_model_and_tool_events(monkeypatch, tmp_path) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(task_routes, "store", store)
    store.upsert_by_key(
        "tasks",
        "id",
        "task-1",
        {
            "events": [
                {"step": "reply_start"},
                {"step": "tool_call_end"},
                {"tool_name": "shell"},
            ],
            "messages": [{"content": "12345678"}],
        },
    )

    assert task_routes.task_stats_payload("task-1") == {
        "events": 3,
        "model_calls": 1,
        "tool_calls": 2,
        "total_tokens": 2,
        "tool_usage": {},
    }


def test_task_events_payload_omits_large_browser_snapshot(monkeypatch, tmp_path) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(task_routes, "store", store)
    snapshot = "\n".join(f"role=button [ref={idx}]" for idx in range(80))
    store.upsert_by_key(
        "tasks",
        "id",
        "task-1",
        {
            "events": [
                {
                    "type": "trace",
                    "step": "tool_result_end",
                    "tool_name": "browser_use",
                    "detail": snapshot,
                    "result": {"snapshot": snapshot, "title": "Example"},
                },
            ],
        },
    )

    events = task_routes.task_events_payload("task-1")

    assert events[0]["detail"] == "[browser snapshot omitted]"
    assert events[0]["result"]["snapshot"] == "[browser snapshot omitted]"
    assert events[0]["result"]["title"] == "Example"


def test_estimate_task_context_budget_payload_normalizes_skill_names(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _estimate(task_id: str, *, message: str, skill_names: list[str]):
        captured.update(
            {"task_id": task_id, "message": message, "skill_names": skill_names},
        )
        return {"ok": True}

    monkeypatch.setattr(task_routes, "estimate_context_budget", _estimate)

    assert task_routes.estimate_task_context_budget_payload(
        "task-1",
        {"message": "hello", "skill_names": ["skill-a"]},
    ) == {"ok": True}
    assert captured == {
        "task_id": "task-1",
        "message": "hello",
        "skill_names": ["skill-a"],
    }


@pytest.mark.asyncio
async def test_stop_task_payload_aborts_and_commits_stopped(
    monkeypatch,
    tmp_path,
) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(task_routes, "store", store)
    calls: dict[str, object] = {}

    async def _abort(task_id: str, task: dict, request: object):
        calls["abort"] = (task_id, task["id"], request)
        return ["run-1"]

    monkeypatch.setitem(
        __import__("sys").modules,
        "qwenpaw.agentdesk.task_cleanup",
        SimpleNamespace(abort_task_runs=_abort),
    )
    monkeypatch.setattr(
        task_routes,
        "commit_task_run_status",
        lambda task_id, status: calls.setdefault("status", (task_id, status)),
    )

    request = object()
    result = await task_routes.stop_task_payload("task-1", request)

    assert result == {"id": "task-1", "stopped": True, "aborted": ["run-1"]}
    assert calls["abort"] == ("task-1", "task-1", request)
    assert calls["status"] == ("task-1", task_routes.RUN_STATUS_STOPPED)
