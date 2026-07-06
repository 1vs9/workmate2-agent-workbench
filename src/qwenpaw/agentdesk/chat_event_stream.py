# -*- coding: utf-8 -*-
"""Translate native QwenPaw stream chunks into AgentDesk chat SSE events."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from typing import Any, AsyncGenerator, AsyncIterator, Awaitable, Callable

from .run_status import RUN_STATUS_IDLE, commit_task_run_status
from .sse import sse_line
from .stream_protocol import StreamEventSequencer, artifact_payload_from_evt
from .stream_runtime import (
    APPROVAL_POLL_S,
    HEARTBEAT_INTERVAL_S,
    pending_approval_event,
    tag_turn_event,
)
from .stream_translator import QwenPawStreamTranslator, translate_sse_chunk
from .task_store import task_store
from .trace_events import TRACE_EVENT_TYPES, persist_trace_event, schedule_persist_trace_event

logger = logging.getLogger(__name__)


async def emit_translated_events(
    *,
    payload: Any,
    sender: str,
    sequencer: StreamEventSequencer,
    stream_it: AsyncIterator[str],
    tracker: Any | None = None,
    run_key: str | None = None,
    stream_message_id: str | None = None,
    agent_id: str | None = None,
    task_store_obj: Any = task_store,
    pending_approval_event_fn: Callable[[str], Awaitable[dict | None]] = pending_approval_event,
    approval_poll_s: float = APPROVAL_POLL_S,
    heartbeat_interval_s: float = HEARTBEAT_INTERVAL_S,
    trace_event_types: set[str] = TRACE_EVENT_TYPES,
    schedule_persist_trace_event_fn: Callable[[str, dict[str, Any]], None] = schedule_persist_trace_event,
    persist_trace_event_fn: Callable[[str, dict[str, Any]], Awaitable[None]] = persist_trace_event,
    commit_task_run_status_fn: Callable[[str, str], None] = commit_task_run_status,
) -> AsyncGenerator[str, None]:
    _ = tracker, run_key
    translator = QwenPawStreamTranslator(sender=sender)

    def _tag(evt: dict[str, Any]) -> dict[str, Any]:
        return tag_turn_event(
            evt,
            sender=sender,
            message_id=stream_message_id,
            agent_id=agent_id,
        )

    def _schedule_trace_persist(evt: dict[str, Any]) -> None:
        try:
            schedule_persist_trace_event_fn(payload.task_id, evt)
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to schedule trace persist for task %s (type=%s, step=%s)",
                payload.task_id,
                evt.get("type"),
                evt.get("step"),
                exc_info=True,
            )

    fatal_error: str | None = None
    fatal_error_emitted = False
    streamed_text = False
    announced_approvals: set[str] = set()
    last_heartbeat = time.monotonic()
    pending_chunk: asyncio.Task | None = asyncio.create_task(stream_it.__anext__())
    try:
        while pending_chunk is not None:
            done, _pending = await asyncio.wait(
                {pending_chunk},
                timeout=approval_poll_s,
            )

            approval_evt = await pending_approval_event_fn(payload.task_id)
            if (
                approval_evt is not None
                and approval_evt["request_id"] not in announced_approvals
            ):
                announced_approvals.add(str(approval_evt["request_id"]))
                yield sse_line(sequencer.wrap(approval_evt))

            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_interval_s:
                yield sse_line(sequencer.wrap({"type": "heartbeat"}))
                last_heartbeat = now

            if pending_chunk not in done:
                continue

            try:
                raw = pending_chunk.result()
            except StopAsyncIteration:
                break
            pending_chunk = asyncio.create_task(stream_it.__anext__())

            for evt in translate_sse_chunk(translator, raw):
                evt_type = evt.get("type")
                if evt_type == "error" and evt.get("fatal"):
                    fatal_error = str(evt.get("content") or fatal_error or "")
                    fatal_error_emitted = True
                if evt_type == "content_reset":
                    streamed_text = False
                    yield sse_line(sequencer.wrap(evt))
                    if not payload.reconnect:
                        await task_store_obj.reset_assistant_content(payload.task_id)
                    continue
                if evt_type == "text_delta":
                    streamed_text = True
                    yield sse_line(sequencer.wrap(evt))
                    if not payload.reconnect:
                        await task_store_obj.append_assistant_delta(
                            payload.task_id,
                            str(evt.get("content") or ""),
                        )
                    continue
                if evt_type in trace_event_types:
                    tagged = _tag(evt)
                    step = evt_type
                    if step in {"thinking_delta", "thinking_retract", "tool_result_delta"}:
                        yield sse_line(sequencer.wrap(tagged))
                        continue
                    yield sse_line(sequencer.wrap(tagged))
                    _schedule_trace_persist(tagged)
                    continue
                if evt_type == "artifact":
                    yield sse_line(sequencer.wrap(evt))
                    if not payload.reconnect:
                        artifact_payload = artifact_payload_from_evt(evt)
                        if artifact_payload:
                            await task_store_obj.append_assistant_artifacts(
                                payload.task_id,
                                [artifact_payload],
                                message_id=stream_message_id,
                            )
                    continue
                if evt_type == "message":
                    if streamed_text:
                        continue
                    yield sse_line(sequencer.wrap(evt))
                    continue
                yield sse_line(sequencer.wrap(evt))
    finally:
        if pending_chunk is not None and not pending_chunk.done():
            pending_chunk.cancel()
        if pending_chunk is not None:
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                await pending_chunk
        with suppress(Exception):
            await stream_it.aclose()

    for evt in translator.finalize_pending_tools():
        tagged = _tag(evt)
        yield sse_line(sequencer.wrap(tagged))
        _schedule_trace_persist(tagged)

    for evt in translator.finalize_pending_thinking():
        tagged = _tag(evt)
        yield sse_line(sequencer.wrap(tagged))
        _schedule_trace_persist(tagged)

    for evt in translator.finalize_answer_fallback():
        yield sse_line(sequencer.wrap(evt))
        if evt.get("type") == "text_delta" and not payload.reconnect:
            await task_store_obj.append_assistant_delta(
                payload.task_id,
                str(evt.get("content") or ""),
            )

    await task_store_obj.finalize_assistant_message(
        payload.task_id,
        content=translator.final_text() or None,
    )
    await asyncio.to_thread(commit_task_run_status_fn, payload.task_id, RUN_STATUS_IDLE)

    if fatal_error and not fatal_error_emitted:
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": fatal_error,
                    "fatal": True,
                },
            ),
        )

    reply_end = _tag(
        {
            "type": "reply_end",
            "label": "Reply complete",
        },
    )
    await persist_trace_event_fn(payload.task_id, reply_end)
    yield sse_line(sequencer.wrap(reply_end))
    yield sse_line(
        sequencer.wrap(
            {
                "type": "done",
                "messages": await task_store_obj.get_messages(payload.task_id),
            },
        ),
    )
