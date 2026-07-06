# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.agentdesk import task_planning_routes


def test_update_task_queue_item_payload_normalizes_body(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []
    monkeypatch.setattr(
        task_planning_routes,
        "update_task_queue_item",
        lambda task_id, item_id, payload: calls.append((task_id, item_id, payload))
        or [{"id": item_id, **payload}],
    )

    assert task_planning_routes.update_task_queue_item_payload(
        "task-1",
        "item-1",
        {"title": "Step"},
    ) == [{"id": "item-1", "title": "Step"}]
    assert calls == [("task-1", "item-1", {"title": "Step"})]


def test_reorder_task_queue_payload_extracts_ids(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        task_planning_routes,
        "reorder_task_queue",
        lambda task_id, order: calls.append((task_id, order)) or [{"id": order[0]}],
    )

    assert task_planning_routes.reorder_task_queue_payload(
        "task-1",
        {"ids": ["b", "a"]},
    ) == [{"id": "b"}]
    assert calls == [("task-1", ["b", "a"])]


def test_confirm_task_plan_payload_extracts_action(monkeypatch) -> None:
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        task_planning_routes,
        "confirm_task_plan",
        lambda task_id, action: calls.append((task_id, action))
        or {"task_id": task_id, "action": action},
    )

    assert task_planning_routes.confirm_task_plan_payload(
        "task-1",
        {"action": "accept"},
    ) == {"task_id": "task-1", "action": "accept"}
    assert calls == [("task-1", "accept")]


def test_passthrough_payloads_delegate(monkeypatch) -> None:
    monkeypatch.setattr(
        task_planning_routes,
        "get_task_queue",
        lambda task_id: [{"id": task_id}],
    )
    monkeypatch.setattr(
        task_planning_routes,
        "delete_task_queue_item",
        lambda task_id, item_id: [{"deleted": item_id}],
    )
    monkeypatch.setattr(
        task_planning_routes,
        "get_task_plan",
        lambda task_id: {"task_id": task_id},
    )

    assert task_planning_routes.get_task_queue_payload("task-1") == [
        {"id": "task-1"},
    ]
    assert task_planning_routes.delete_task_queue_item_payload(
        "task-1",
        "item-1",
    ) == [{"deleted": "item-1"}]
    assert task_planning_routes.get_task_plan_payload("task-1") == {
        "task_id": "task-1",
    }
