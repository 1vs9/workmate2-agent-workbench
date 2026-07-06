# -*- coding: utf-8 -*-
"""AgentDesk task trace event persistence."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .background_tasks import spawn_background
from .store import store as agentdesk_store
from .task_store import task_store

logger = logging.getLogger(__name__)

_EVENT_TEXT_LIMIT = 4096
_BROWSER_SNAPSHOT_KEYS = frozenset(
    {
        "accessibility_snapshot",
        "browser_snapshot",
        "dom_snapshot",
        "page_snapshot",
        "screenshot",
        "snapshot",
    },
)

TRACE_EVENT_TYPES = frozenset(
    {
        "thinking_start",
        "thinking_delta",
        "thinking_end",
        "thinking_retract",
        "tool_call_start",
        "tool_call_end",
        "tool_result_start",
        "tool_result_delta",
        "tool_result_end",
        "skills_active",
        "skill_create",
        "info",
        "reply_start",
        "reply_end",
    },
)


def to_persisted_trace(evt: dict[str, Any]) -> dict[str, Any] | None:
    evt_type = str(evt.get("type") or "")
    if evt_type == "trace":
        return evt
    if evt_type not in TRACE_EVENT_TYPES:
        return None
    payload = dict(evt)
    payload["type"] = "trace"
    payload["step"] = evt_type
    return payload


def _trim_text(value: str) -> str:
    if len(value) <= _EVENT_TEXT_LIMIT:
        return value
    omitted = len(value) - _EVENT_TEXT_LIMIT
    return f"{value[:_EVENT_TEXT_LIMIT]}\n... [{omitted} chars omitted]"


def _looks_like_browser_snapshot(text: str) -> bool:
    lowered = text.lower()
    return (
        "accessibility snapshot" in lowered
        or "aria snapshot" in lowered
        or "browser snapshot" in lowered
        or lowered.count("[ref=") >= 20
        or lowered.count("role=") >= 20
    )


def _slim_event_value(value: Any, *, key: str = "") -> Any:
    key_l = key.lower()
    if key_l in _BROWSER_SNAPSHOT_KEYS:
        return "[browser snapshot omitted]"
    if isinstance(value, str):
        if _looks_like_browser_snapshot(value):
            return "[browser snapshot omitted]"
        return _trim_text(value)
    if isinstance(value, list):
        if key_l in _BROWSER_SNAPSHOT_KEYS:
            return "[browser snapshot omitted]"
        return [_slim_event_value(item) for item in value[:50]]
    if isinstance(value, dict):
        return {
            str(child_key): _slim_event_value(child_value, key=str(child_key))
            for child_key, child_value in value.items()
        }
    return value


def slim_event_for_client(evt: dict[str, Any]) -> dict[str, Any]:
    """Return a frontend-safe trace event without huge browser snapshots."""
    slimmed = {
        str(key): _slim_event_value(value, key=str(key))
        for key, value in dict(evt).items()
    }
    for field in ("detail", "result", "content", "output"):
        value = slimmed.get(field)
        if not isinstance(value, str):
            continue
        stripped = value.strip()
        if not stripped or stripped[0] not in "[{":
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        slimmed[field] = json.dumps(
            _slim_event_value(parsed),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return slimmed


def slim_events_for_client(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [slim_event_for_client(evt) for evt in events if isinstance(evt, dict)]


async def persist_trace_event(
    task_id: str,
    evt: dict,
    *,
    message_id: str | None = None,
) -> None:
    payload = to_persisted_trace(evt)
    if payload is None:
        return
    try:
        target_id = message_id or await task_store.current_assistant_message_id(
            task_id,
        )
        # append_task_event rewrites the whole store.json; never do that on the
        # event loop or every trace event stalls the SSE stream.
        await asyncio.to_thread(
            agentdesk_store.append_task_event,
            task_id,
            payload,
            message_id=target_id,
        )
    except Exception:
        logger.warning(
            "Failed to persist trace event for task %s (step=%s)",
            task_id,
            evt.get("step"),
            exc_info=True,
        )


def schedule_persist_trace_event(task_id: str, evt: dict) -> None:
    """Persist trace events off the SSE hot path."""

    spawn_background(persist_trace_event(task_id, evt))


async def task_events_snapshot(task_id: str) -> list[dict[str, Any]]:
    """Authoritative trace events for a task."""

    task = await asyncio.to_thread(
        agentdesk_store.get_by_key, "tasks", "id", task_id,
    )
    events = (task or {}).get("events", [])
    return slim_events_for_client(events if isinstance(events, list) else [])
