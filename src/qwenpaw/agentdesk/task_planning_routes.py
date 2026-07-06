# -*- coding: utf-8 -*-
"""AgentDesk task queue and plan endpoint orchestration helpers."""

from __future__ import annotations

from typing import Any

from .task_planning import (
    confirm_task_plan,
    delete_task_queue_item,
    get_task_plan,
    get_task_queue,
    reorder_task_queue,
    update_task_queue_item,
)


def get_task_queue_payload(task_id: str) -> list[dict[str, Any]]:
    return get_task_queue(task_id)


def update_task_queue_item_payload(
    task_id: str,
    item_id: str,
    body: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    return update_task_queue_item(task_id, item_id, dict(body or {}))


def delete_task_queue_item_payload(task_id: str, item_id: str) -> list[dict[str, Any]]:
    return delete_task_queue_item(task_id, item_id)


def reorder_task_queue_payload(
    task_id: str,
    body: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    return reorder_task_queue(task_id, dict(body or {}).get("ids", []))


def get_task_plan_payload(task_id: str) -> dict[str, Any]:
    return get_task_plan(task_id)


def confirm_task_plan_payload(
    task_id: str,
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    return confirm_task_plan(task_id, dict(body or {}).get("action"))
