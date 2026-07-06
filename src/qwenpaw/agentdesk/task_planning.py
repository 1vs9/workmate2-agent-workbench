# -*- coding: utf-8 -*-
"""AgentDesk task queue, plan, and context-budget helpers."""

from __future__ import annotations

from typing import Any

from .stubs import health_payload
from .store import store


def estimate_context_budget(
    task_id: str,
    *,
    message: str,
    skill_names: list[Any],
) -> dict[str, Any]:
    used = max(1, len(message) // 4 + 256 + len(skill_names) * 128)
    limit = health_payload()["model_context_size"]
    return {
        "task_id": task_id,
        "percent": min(100, round(used / limit * 100, 2)),
        "used_tokens": used,
        "context_limit": limit,
        "segments": [
            {"key": "message", "label": "Current message", "tokens": max(1, len(message) // 4)},
            {"key": "skills", "label": "Skill context", "tokens": len(skill_names) * 128},
            {"key": "base", "label": "System context", "tokens": 256},
        ],
        "estimate_note": "Local estimate; actual token usage depends on the model call.",
    }


def get_task_queue(task_id: str) -> list[dict[str, Any]]:
    task = store.get_by_key("tasks", "id", task_id) or {}
    queue = task.get("queue", [])
    return list(queue) if isinstance(queue, list) else []


def update_task_queue_item(
    task_id: str,
    item_id: str,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    task = store.get_by_key("tasks", "id", task_id) or store.ensure_task(task_id)
    queue = get_task_queue(task_id)
    for idx, item in enumerate(queue):
        if str(item.get("id")) == item_id:
            queue[idx] = {**item, **payload, "id": item_id}
            break
    else:
        queue.append({"id": item_id, **payload})
    task["queue"] = queue
    store.upsert_by_key("tasks", "id", task_id, task)
    return queue


def delete_task_queue_item(task_id: str, item_id: str) -> list[dict[str, Any]]:
    task = store.get_by_key("tasks", "id", task_id) or store.ensure_task(task_id)
    task["queue"] = [
        item for item in get_task_queue(task_id) if str(item.get("id")) != item_id
    ]
    store.upsert_by_key("tasks", "id", task_id, task)
    return task["queue"]


def reorder_task_queue(task_id: str, order: list[Any]) -> list[dict[str, Any]]:
    task = store.get_by_key("tasks", "id", task_id) or store.ensure_task(task_id)
    ids = [str(item_id) for item_id in order]
    by_id = {str(item.get("id")): item for item in get_task_queue(task_id)}
    task["queue"] = [by_id[item_id] for item_id in ids if item_id in by_id]
    store.upsert_by_key("tasks", "id", task_id, task)
    return task["queue"]


def get_task_plan(task_id: str) -> dict[str, Any]:
    task = store.get_by_key("tasks", "id", task_id) or {}
    wizard = task.get("wizard")
    status = task.get("plan_status") or (
        str(wizard.get("status"))
        if isinstance(wizard, dict) and wizard.get("status")
        else "idle"
    )
    return {
        "task_id": task_id,
        "status": status,
        "tasks": task.get("plan_tasks") or [],
        "wizard": wizard,
    }


def confirm_task_plan(task_id: str, action: Any) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "status": "unsupported",
        "action": action,
        "tasks": [],
    }
