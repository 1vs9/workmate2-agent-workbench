# -*- coding: utf-8 -*-
"""AgentDesk task endpoint orchestration helpers."""

from __future__ import annotations

from typing import Any

from .run_status import RUN_STATUS_STOPPED, commit_task_run_status
from .store import store
from .task_planning import estimate_context_budget
from .task_projection import task_for_client, task_sort_key
from .task_records import create_task_record, update_task_record
from .trace_events import slim_events_for_client


def list_task_payloads() -> list[dict[str, Any]]:
    tasks = store.list_items("tasks")
    tasks.sort(key=task_sort_key, reverse=True)
    return [task_for_client(task) for task in tasks]


def create_task_payload(body: dict[str, Any] | None) -> dict[str, Any]:
    return task_for_client(create_task_record(dict(body or {})))


def update_task_payload(task_id: str, body: dict[str, Any] | None) -> dict[str, Any]:
    return task_for_client(update_task_record(task_id, dict(body or {})))


async def ensure_memory_task(task_id: str) -> None:
    try:
        from .task_store import task_store

        messages = await task_store.get_messages(task_id)
    except Exception:  # noqa: BLE001
        messages = []
    if messages:
        task = store.ensure_task(task_id)
        task["messages"] = messages
        store.upsert_by_key("tasks", "id", task_id, task)


async def get_task_payload(task_id: str) -> dict[str, Any]:
    from .task_store import task_store

    task = store.get_by_key("tasks", "id", task_id)
    if task is None:
        await ensure_memory_task(task_id)
        task = store.get_by_key("tasks", "id", task_id) or {
            "id": task_id,
            "title": "AgentDesk",
            "messages": [],
        }
    await task_store.ensure_task(task_id)
    live_messages = await task_store.get_messages(task_id)
    if live_messages:
        task = {**task, "messages": live_messages}
    return task_for_client(task)


async def delete_task_payload(task_id: str, request: Any) -> dict[str, Any]:
    from .task_cleanup import cleanup_task

    return await cleanup_task(task_id, request)


def task_events_payload(task_id: str) -> list[dict[str, Any]]:
    task = store.get_by_key("tasks", "id", task_id) or {}
    events = task.get("events", [])
    return slim_events_for_client(events if isinstance(events, list) else [])


def task_stats_payload(task_id: str) -> dict[str, Any]:
    task = store.get_by_key("tasks", "id", task_id) or {}
    events = task.get("events", [])
    messages = task.get("messages", [])
    events = events if isinstance(events, list) else []
    messages = messages if isinstance(messages, list) else []
    tool_calls = sum(
        1
        for event in events
        if isinstance(event, dict)
        and (
            event.get("step") in ("tool_call_end", "tool_result_start")
            or event.get("tool_name")
        )
    )
    model_calls = sum(
        1
        for event in events
        if isinstance(event, dict)
        and event.get("step") in ("reply_start", "model_call")
    )
    if model_calls == 0 and any(
        isinstance(event, dict) and event.get("step") == "reply_end"
        for event in events
    ):
        model_calls = 1
    return {
        "events": len(events),
        "model_calls": model_calls,
        "tool_calls": tool_calls,
        "total_tokens": sum(
            len(str(msg.get("content", ""))) // 4
            for msg in messages
            if isinstance(msg, dict)
        ),
        "tool_usage": {},
    }


def estimate_task_context_budget_payload(
    task_id: str,
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(body or {})
    message = str(payload.get("message") or "")
    skill_names = payload.get("skill_names") or []
    return estimate_context_budget(
        task_id,
        message=message,
        skill_names=list(skill_names) if isinstance(skill_names, list) else [],
    )


async def stop_task_payload(task_id: str, request: Any) -> dict[str, Any]:
    from .task_cleanup import abort_task_runs

    task = store.get_by_key("tasks", "id", task_id) or store.ensure_task(task_id)
    aborted = await abort_task_runs(task_id, task, request)
    commit_task_run_status(task_id, RUN_STATUS_STOPPED)
    return {"id": task_id, "stopped": True, "aborted": aborted}
