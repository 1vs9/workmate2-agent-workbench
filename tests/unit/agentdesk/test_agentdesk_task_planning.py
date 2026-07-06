# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.agentdesk import task_planning
from qwenpaw.agentdesk.store import AgentDeskStore


def test_task_queue_update_delete_and_reorder(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(task_planning, "store", store)

    assert task_planning.update_task_queue_item(
        "task-1",
        "a",
        {"title": "A"},
    ) == [{"id": "a", "title": "A"}]
    assert task_planning.update_task_queue_item(
        "task-1",
        "b",
        {"title": "B"},
    ) == [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]
    assert task_planning.update_task_queue_item(
        "task-1",
        "a",
        {"done": True},
    ) == [{"id": "a", "title": "A", "done": True}, {"id": "b", "title": "B"}]

    assert task_planning.reorder_task_queue("task-1", ["b", "missing", "a"]) == [
        {"id": "b", "title": "B"},
        {"id": "a", "title": "A", "done": True},
    ]
    assert task_planning.delete_task_queue_item("task-1", "b") == [
        {"id": "a", "title": "A", "done": True},
    ]


def test_get_task_plan_prefers_explicit_status(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(task_planning, "store", store)
    store.upsert_by_key(
        "tasks",
        "id",
        "task-1",
        {
            "id": "task-1",
            "plan_status": "ready",
            "wizard": {"status": "draft"},
            "plan_tasks": [{"id": "step-1"}],
        },
    )

    assert task_planning.get_task_plan("task-1") == {
        "task_id": "task-1",
        "status": "ready",
        "tasks": [{"id": "step-1"}],
        "wizard": {"status": "draft"},
    }


def test_estimate_context_budget_uses_segments(monkeypatch) -> None:
    monkeypatch.setattr(
        task_planning,
        "health_payload",
        lambda: {"model_context_size": 1000},
    )

    payload = task_planning.estimate_context_budget(
        "task-1",
        message="x" * 40,
        skill_names=["a", "b"],
    )

    assert payload["used_tokens"] == 522
    assert payload["percent"] == 52.2
    assert payload["segments"] == [
        {"key": "message", "label": "Current message", "tokens": 10},
        {"key": "skills", "label": "Skill context", "tokens": 256},
        {"key": "base", "label": "System context", "tokens": 256},
    ]


def test_confirm_task_plan_is_explicitly_unsupported() -> None:
    assert task_planning.confirm_task_plan("task-1", "accept") == {
        "task_id": "task-1",
        "status": "unsupported",
        "action": "accept",
        "tasks": [],
    }
