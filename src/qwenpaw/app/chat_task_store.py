# -*- coding: utf-8 -*-
"""In-process store and runner for background ``/console/chat/task`` jobs."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from qwenpaw.agents.tools.agent_management import (
    is_completed_agent_sse_response,
    merge_agent_sse_snapshot,
    parse_agent_sse_line,
)
from qwenpaw.runtime.worker_stream_bus import WORKER_STREAM_DONE_SENTINEL, worker_stream_bus

logger = logging.getLogger(__name__)

DEFAULT_STREAM_TASK_TIMEOUT = 600.0

# How long each bounded ``queue.get`` waits before re-checking the deadline.
_QUEUE_POLL_SLICE_S = 5.0
# If a reply was already produced but the upstream stream never closes, finalize
# after this much idle time instead of waiting for the full task timeout.
_IDLE_FINALIZE_S = 60.0


@dataclass
class ChatTaskRecord:
    """Lifecycle record for one background console chat task."""

    task_id: str
    status: str = "submitted"
    submitted_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: dict[str, Any] | None = None
    executor_agent_id: str = ""
    allowed_reader_agent_ids: frozenset[str] = field(default_factory=frozenset)

    def is_readable_by(self, agent_id: str) -> bool:
        """Return whether *agent_id* may poll this task's status/result."""
        normalized = str(agent_id or "").strip()
        if not normalized or not self.allowed_reader_agent_ids:
            return False
        return normalized in self.allowed_reader_agent_ids


class ChatTaskStore:
    """Thread-safe (async-lock) registry of background chat tasks."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tasks: dict[str, ChatTaskRecord] = {}

    async def create(
        self,
        *,
        executor_agent_id: str = "",
        allowed_reader_agent_ids: frozenset[str] | None = None,
    ) -> ChatTaskRecord:
        task_id = uuid.uuid4().hex
        executor = str(executor_agent_id or "").strip()
        allowed = allowed_reader_agent_ids
        if allowed is None:
            allowed = frozenset({executor} if executor else ())
        record = ChatTaskRecord(
            task_id=task_id,
            executor_agent_id=executor,
            allowed_reader_agent_ids=allowed,
        )
        async with self._lock:
            self._tasks[task_id] = record
        return record

    async def get(self, task_id: str) -> ChatTaskRecord | None:
        async with self._lock:
            return self._tasks.get(task_id)

    async def mark_running(self, task_id: str) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            record.status = "running"
            record.started_at = time.time()

    async def mark_finished(
        self,
        task_id: str,
        *,
        result: dict[str, Any],
    ) -> None:
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return
            record.status = "finished"
            record.finished_at = time.time()
            record.result = result

    def to_status_payload(self, record: ChatTaskRecord) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "task_id": record.task_id,
            "status": record.status,
            "submitted_at": record.submitted_at,
        }
        if record.started_at is not None:
            payload["started_at"] = record.started_at
        if record.finished_at is not None:
            payload["finished_at"] = record.finished_at
        if record.result is not None:
            payload["result"] = record.result
        return payload


chat_task_store = ChatTaskStore()


def build_task_allowed_readers(
    *,
    executor_agent_id: str,
    request_data: dict[str, Any] | None = None,
) -> frozenset[str]:
    """Collect agent ids permitted to poll a background console chat task."""
    allowed: set[str] = set()
    executor = str(executor_agent_id or "").strip()
    if executor:
        allowed.add(executor)
    if isinstance(request_data, dict):
        ctx = request_data.get("request_context")
        if isinstance(ctx, dict):
            for key in ("root_agent_id", "caller_agent_id"):
                value = str(ctx.get(key) or "").strip()
                if value:
                    allowed.add(value)
    return frozenset(allowed)


async def run_background_console_chat(
    *,
    task_id: str,
    workspace: Any,
    console_channel: Any,
    native_payload: dict[str, Any],
    to_agent: str,
    publish_key: str | None,
    task_timeout: float | None,
) -> None:
    """Execute one console chat run in the background and record its result."""
    await chat_task_store.mark_running(task_id)
    tracker = workspace.task_tracker
    run_key = f"chat-task-{task_id}"
    await tracker.register_external_task(run_key)

    session_id = console_channel.resolve_session_id(
        sender_id=native_payload["sender_id"],
        channel_meta=native_payload["meta"],
    )
    from .routers.console import _extract_placeholder_name

    name, _first_text = _extract_placeholder_name(native_payload["content_parts"])
    chat = await workspace.chat_manager.get_or_create_chat(
        session_id,
        native_payload["sender_id"],
        native_payload["channel_id"],
        name=name or "AgentDesk",
    )

    # Whether to mirror this background worker's live SSE onto the worker stream
    # bus so the team-mode leader stream can render the member's process in real
    # time. Re-checked per line below (not just once) so a team stream that
    # subscribes slightly after the task starts still receives the process.
    can_publish = bool(publish_key)
    published_any = False
    response_data: dict[str, Any] | None = None
    session_id_out = str(native_payload["meta"].get("session_id") or session_id)
    queue: asyncio.Queue | None = None

    try:
        queue, _is_new = await tracker.attach_or_start(
            chat.id,
            native_payload,
            console_channel.stream_one,
        )
        deadline = None
        if task_timeout is not None and task_timeout > 0:
            deadline = time.monotonic() + float(task_timeout)

        # Consume the run's queue directly (instead of ``stream_from_queue``) so
        # the wall-clock deadline is enforced even when the producer goes silent.
        # A provider stream that emits the reply but never closes would otherwise
        # block ``queue.get()`` forever — the task would stay ``running`` and any
        # poller (e.g. the team leader) would wait indefinitely.
        last_event_at = time.monotonic()
        while True:
            now = time.monotonic()
            if deadline is not None and now > deadline:
                await tracker.request_stop(chat.id)
                if response_data is not None:
                    # Reply already produced before the deadline; keep it rather
                    # than discarding the worker's completed answer.
                    break
                raise TimeoutError(
                    f"Background chat task exceeded timeout ({task_timeout}s)",
                )
            if (
                response_data is not None
                and is_completed_agent_sse_response(response_data)
                and (now - last_event_at) > _IDLE_FINALIZE_S
            ):
                # The completed reply landed but the upstream stream never
                # closed; stop the idle producer and finalize so callers aren't
                # stuck waiting. Do not finalize on in-progress tool output
                # alone — the model may still be writing its summary.
                await tracker.request_stop(chat.id)
                break
            try:
                raw = await asyncio.wait_for(
                    queue.get(),
                    timeout=_QUEUE_POLL_SLICE_S,
                )
            except asyncio.TimeoutError:
                continue
            if raw is None:  # producer sentinel: run finished cleanly
                break
            last_event_at = time.monotonic()
            if (
                can_publish
                and raw
                and worker_stream_bus.has_subscribers(str(publish_key))
            ):
                worker_stream_bus.publish(
                    str(publish_key),
                    (to_agent, raw),
                )
                published_any = True
            parsed = parse_agent_sse_line(str(raw))
            if parsed:
                response_data = merge_agent_sse_snapshot(
                    response_data,
                    parsed,
                )
    except asyncio.CancelledError:
        await chat_task_store.mark_finished(
            task_id,
            result={
                "status": "failed",
                "session_id": session_id_out,
                "error": {"message": "Task cancelled"},
            },
        )
        raise
    except Exception as exc:  # noqa: BLE001 - surface as task failure
        logger.exception("Background console chat task %s failed", task_id)
        await chat_task_store.mark_finished(
            task_id,
            result={
                "status": "failed",
                "session_id": session_id_out,
                "error": {"message": str(exc)},
            },
        )
    else:
        await chat_task_store.mark_finished(
            task_id,
            result={
                "status": "completed",
                "session_id": session_id_out,
                "output": (response_data or {}).get("output", []),
            },
        )
    finally:
        # Detach our subscriber queue from the run (we consumed it directly
        # rather than via ``stream_from_queue``, which would normally do this).
        if queue is not None:
            with suppress(Exception):
                await tracker.detach_subscriber(chat.id, queue)
        if published_any and worker_stream_bus.has_subscribers(str(publish_key)):
            worker_stream_bus.publish(
                str(publish_key),
                (to_agent, WORKER_STREAM_DONE_SENTINEL),
            )
        await tracker.unregister_external_task(run_key)
