# -*- coding: utf-8 -*-
"""AgentDesk task record mutation helpers."""

from __future__ import annotations

import uuid
from typing import Any

from .store import store


class ClientManagedTaskFieldError(ValueError):
    """Raised when clients attempt to write runtime-managed task fields."""


def create_task_record(body: dict[str, Any] | None) -> dict[str, Any]:
    """Create a task record while preserving runtime-owned workspace fields."""
    payload = dict(body or {})
    if payload.get("workspace_dir"):
        raise ClientManagedTaskFieldError(
            "workspace_dir is managed by AgentDesk runtime",
        )
    task_id = str(payload.get("id") or uuid.uuid4().hex)
    title = str(payload.get("title") or "New Task")
    return store.ensure_task(task_id, title=title)


def task_patch_from_payload(body: dict[str, Any] | None) -> dict[str, Any]:
    """Return the user-editable task fields accepted by the patch endpoint."""
    payload = dict(body or {})
    updates: dict[str, Any] = {}
    if "title" in payload:
        updates["title"] = str(payload["title"] or "New Task")
    if "pinned" in payload:
        updates["pinned"] = bool(payload["pinned"])
    return updates


def update_task_record(task_id: str, body: dict[str, Any] | None) -> dict[str, Any]:
    """Patch a task record, returning the existing record for empty patches."""
    existing = store.get_by_key("tasks", "id", task_id)
    if existing is None:
        raise LookupError("Task not found")
    updates = task_patch_from_payload(body)
    if not updates:
        return existing
    return store.upsert_by_key("tasks", "id", task_id, updates)


def attach_skill_to_task_record(task_id: str, skill_name: str) -> dict[str, Any]:
    """Attach a skill to a task record, preserving order and avoiding duplicates."""
    normalized_task_id = str(task_id or "").strip()
    normalized_skill = str(skill_name or "").strip()
    if not normalized_task_id or not normalized_skill:
        raise ValueError("task_id and skill_name are required")
    task = store.get_by_key("tasks", "id", normalized_task_id) or store.ensure_task(
        normalized_task_id,
    )
    selected = list(
        dict.fromkeys(
            [
                *(
                    str(item).strip()
                    for item in task.get("skill_names", [])
                    if str(item).strip()
                ),
                normalized_skill,
            ],
        ),
    )
    task["skill_names"] = selected
    return store.upsert_by_key("tasks", "id", normalized_task_id, task)
