# -*- coding: utf-8 -*-
"""AgentDesk team-mode chat 鈥?leader orchestrates plaza workers via QwenPaw."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, AsyncGenerator, Callable

from fastapi import HTTPException, Request

from ..app.agent_context import (
    get_agent_for_request,
    set_current_root_session_id,
    set_current_session_id,
)
from ..app.routers.console import _extract_placeholder_name
from ..runtime.worker_stream_bus import WORKER_STREAM_DONE_SENTINEL
from .agents import lookup_agent_id, resolve_agent_id
from .background_tasks import spawn_background
from .locale import build_chat_response_language_hint
from .model_config import ensure_chat_model
from .models import ChatRequest
from .native_payload import build_agentdesk_native_payload
from .run_status import (
    RUN_STATUS_IDLE as _RUN_STATUS_IDLE,
    RUN_STATUS_RUNNING as _RUN_STATUS_RUNNING,
    commit_task_run_status as _commit_task_run_status,
    is_task_running as _is_task_running,
    set_task_run_status as _set_task_run_status,
)
from .sse import sse_line
from .stream_protocol import StreamEventSequencer, artifact_payload_from_evt
from .stream_runtime import (
    APPROVAL_POLL_S as _APPROVAL_POLL_S,
    HEARTBEAT_INTERVAL_S as _HEARTBEAT_INTERVAL_S,
    pending_approval_event as _pending_approval_event,
)
from .stream_side_effects import (
    schedule_append_assistant_delta as _schedule_append_assistant_delta,
)
from .stream_translator import QwenPawStreamTranslator, translate_sse_chunk
from .store import format_agentdesk_stream_error
from .task_store import task_store
from .task_workspace_sync import (
    schedule_sync_task_workspace as _schedule_sync_task_workspace,
)
from .team_completion import build_team_done_event as _build_done_event
from .team_records import resolve_team_record
from .team_sessions import (
    TEAM_LEADER_SESSION_SUFFIX as _TEAM_LEADER_SESSION_SUFFIX,
    team_member_session_id as _team_member_session_id,
    team_session_id as _team_session_id,
)
from .team_timeline import TeamTimelineWriter, classify_leader_narration, filter_leader_persist_text
from .team_timeline_events import (
    timeline_sse_from_entry as _timeline_sse_from_entry,
    timeline_sse_lines_for_event as _timeline_sse_lines_for_event,
)
from .team_turn_events import (
    reply_end_event as _reply_end_event,
    tag_leader_trace_event as _tag_leader_trace_event,
    team_done_label as _team_done_label,
    team_done_phase_event as _team_done_phase_event,
    timed_out_members_label as _timed_out_members_label,
)
from .team_worker_events import (
    discard_worker_stream_state as _clear_worker_stream_state,
    finalized_worker_trace_events as _build_finalized_worker_trace_events,
    leftover_worker_bubbles as _select_leftover_worker_bubbles,
    resolve_worker_display_name as _resolve_worker_display_name,
    tag_worker_event as _build_worker_event,
    worker_final_text as _select_worker_final_text,
)
from .team_worker_bus import TeamWorkerBusBridge as _TeamWorkerBusBridge
from .team_worker_messages import (
    begin_worker_assistant_message as _begin_worker_assistant_message,
    resolve_member_watch_message_id as _resolve_member_watch_message_id,
)
from .team_leader_agents import (
    is_team_leader_agent_id,
    sync_team_leader_agent,
    team_leader_agent_id,
    team_leader_display_name,
)
from .team_leader_runs import (
    arm_leader_finalize_watch as _arm_leader_finalize_watch,
    cancel_leader_finalize_watch as _cancel_leader_finalize_watch,
)
from .team_leader_chat import resolve_team_leader_chat as _resolve_team_leader_chat
from .session_bridge import AGENTDESK_SESSION_CHANNEL, AGENTDESK_SESSION_USER_ID
from .trace_events import (
    TRACE_EVENT_TYPES as _TRACE_EVENT_TYPES,
    persist_trace_event as _persist_trace_event,
)

_spawn_background = spawn_background

logger = logging.getLogger(__name__)

_AGENTDESK_USER_ID = AGENTDESK_SESSION_USER_ID
_AGENTDESK_CHANNEL = AGENTDESK_SESSION_CHANNEL


async def _stream_member_native_session(
    payload: ChatRequest,
    request: Request,
    sequencer: StreamEventSequencer,
    member_name: str,
) -> AsyncGenerator[str, None]:
    """Attach to the member's QwenPaw console session (same as single-chat reconnect)."""
    agent_id = lookup_agent_id(member_name)
    if not agent_id:
        return

    member_session = _team_member_session_id(payload.task_id, member_name)
    msg_id = await _resolve_member_watch_message_id(payload.task_id, member_name)
    if not msg_id and not payload.reconnect:
        draft = await _begin_worker_assistant_message(payload.task_id, member_name)
        msg_id = str(draft.get("id") or "").strip() or None
    if not msg_id:
        return

    if not hasattr(request.state, "agent_id") or request.state.agent_id is None:
        request.state.agent_id = agent_id
    workspace = await get_agent_for_request(request, agent_id=agent_id)
    console_channel = await workspace.channel_manager.get_channel(_AGENTDESK_CHANNEL)
    if console_channel is None:
        return

    tracker = workspace.task_tracker
    chat = await workspace.chat_manager.get_or_create_chat(
        member_session,
        _AGENTDESK_USER_ID,
        _AGENTDESK_CHANNEL,
        name=member_name,
    )
    queue = await tracker.attach(chat.id)
    if queue is None:
        return

    translator = QwenPawStreamTranslator(sender=member_name)
    streamed_text = False
    yield sse_line(
        sequencer.wrap(
            {
                "type": "stream_start",
                "sender": member_name,
                "actor_id": member_name,
                "source_member": member_name,
                "message_id": msg_id,
            },
        ),
    )

    stream_it = tracker.stream_from_queue(queue, chat.id)
    try:
        async for raw in stream_it:
            for evt in translate_sse_chunk(translator, raw):
                evt_type = str(evt.get("type") or "")
                if evt_type == "text_delta":
                    content = str(evt.get("content") or "")
                    if not content:
                        continue
                    streamed_text = True
                    if not payload.reconnect:
                        _schedule_append_assistant_delta(
                            payload.task_id,
                            content,
                            message_id=msg_id,
                        )
                    tagged = dict(evt)
                    tagged["sender"] = member_name
                    tagged["actor_id"] = member_name
                    tagged["source_member"] = member_name
                    tagged["message_id"] = msg_id
                    yield sse_line(sequencer.wrap(tagged))
                    continue
                if evt_type == "message":
                    if streamed_text:
                        continue
                    content = str(evt.get("content") or "")
                    if not content:
                        continue
                    if not payload.reconnect:
                        _schedule_append_assistant_delta(
                            payload.task_id,
                            content,
                            message_id=msg_id,
                        )
                    tagged = dict(evt)
                    tagged["sender"] = member_name
                    tagged["actor_id"] = member_name
                    tagged["source_member"] = member_name
                    tagged["message_id"] = msg_id
                    yield sse_line(sequencer.wrap(tagged))
                    continue
                if evt_type == "artifact":
                    if not payload.reconnect:
                        artifact_payload = artifact_payload_from_evt(evt)
                        if artifact_payload:
                            await task_store.append_assistant_artifacts(
                                payload.task_id,
                                [artifact_payload],
                                message_id=msg_id,
                            )
                    tagged = dict(evt)
                    tagged["sender"] = member_name
                    tagged["actor_id"] = member_name
                    tagged["source_member"] = member_name
                    tagged["message_id"] = msg_id
                    yield sse_line(sequencer.wrap(tagged))
                    continue
                if evt_type not in _TRACE_EVENT_TYPES:
                    continue
                tagged = dict(evt)
                tagged["sender"] = member_name
                tagged["actor_id"] = member_name
                tagged["source_member"] = member_name
                tagged["message_id"] = msg_id
                if evt_type not in {
                    "thinking_delta",
                    "thinking_retract",
                    "tool_result_delta",
                }:
                    await _persist_trace_event(
                        payload.task_id,
                        tagged,
                        message_id=msg_id,
                    )
                yield sse_line(sequencer.wrap(tagged))
    finally:
        await stream_it.aclose()
        if not payload.reconnect:
            final_text = translator.final_text()
            if final_text and not streamed_text:
                _schedule_append_assistant_delta(
                    payload.task_id,
                    final_text,
                    message_id=msg_id,
                )
            await task_store.finalize_assistant_message(
                payload.task_id,
                message_id=msg_id,
            )

    yield sse_line(
        sequencer.wrap(
            {
                "type": "member_stream_end",
                "member": member_name,
                "source_member": member_name,
            },
        ),
    )


async def _stream_team_member_watch(
    payload: ChatRequest,
    request: Request,
    sequencer: StreamEventSequencer,
    member_name: str,
) -> AsyncGenerator[str, None]:
    """Member tab passthrough: attach to the member's native QwenPaw session only."""
    member_name = str(member_name or "").strip()
    if not member_name:
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": "Team member is required",
                    "fatal": True,
                },
            ),
        )
        return
    async for line in _stream_member_native_session(
        payload,
        request,
        sequencer,
        member_name,
    ):
        yield line


# Idle polls before declaring the worker bus quiet during reconnect drain.
_WORKER_DRAIN_IDLE_TICKS = 40


async def _yield_team_turn_completion(
    *,
    payload: ChatRequest,
    sequencer: StreamEventSequencer,
    team_name: str,
    leader_sender: str,
    leader_message_id: str | None,
    leader_turn: dict[str, Any],
    timeline_writer: TeamTimelineWriter | None = None,
    timed_out_workers: list[str] | None = None,
    bridge: _NativeTeamEventBridge | None = None,
    worker_message_ids: dict[str, str] | None = None,
) -> AsyncGenerator[str, None]:
    """Shared tail after a leader turn finishes (normal or reconnect)."""
    _cancel_leader_finalize_watch(payload.task_id)

    if leader_turn.get("fatal"):
        await asyncio.to_thread(
            _set_task_run_status, payload.task_id, _RUN_STATUS_IDLE,
        )
        yield sse_line(sequencer.wrap(await _build_done_event(payload.task_id)))
        return

    timed_out = [str(name).strip() for name in (timed_out_workers or []) if str(name).strip()]
    if timed_out and timeline_writer is not None:
        label = _timed_out_members_label(timed_out)
        yield await _timeline_sse_from_entry(
            task_id=payload.task_id,
            entry=timeline_writer._next_entry(
                "phase",
                leader_sender,
                phase="worker_timeout",
                label=label,
            ),
            sequencer=sequencer,
        )

    yield sse_line(
        sequencer.wrap(
            _team_done_phase_event(
                team_name=team_name,
                leader_sender=leader_sender,
                timed_out=bool(timed_out),
            ),
            source="team",
            source_member=leader_sender,
        ),
    )
    if timeline_writer is not None:
        yield await _timeline_sse_from_entry(
            task_id=payload.task_id,
            entry=timeline_writer._next_entry(
                "phase",
                leader_sender,
                phase="done",
                label=_team_done_label(team_name, timed_out=bool(timed_out)),
            ),
            sequencer=sequencer,
        )

    reply_end = _reply_end_event(
        leader_sender=leader_sender,
        leader_message_id=leader_message_id,
    )
    await _persist_trace_event(payload.task_id, reply_end)
    yield sse_line(sequencer.wrap(reply_end))

    await asyncio.to_thread(
        _set_task_run_status, payload.task_id, _RUN_STATUS_IDLE,
    )
    yield sse_line(sequencer.wrap(await _build_done_event(payload.task_id)))


from .team_event_bridge import NativeTeamEventBridge as _NativeTeamEventBridge
from .team_event_bridge import NATIVE_DELEGATION_TOOLS as _NATIVE_DELEGATION_TOOLS

async def _stream_agent_turn(
    *,
    payload: ChatRequest,
    request: Request,
    agent_id: str,
    sender: str,
    agent_message: str,
    sequencer: StreamEventSequencer,
    session_suffix: str,
    emit_stream_start: bool,
    turn_result: dict[str, Any],
    event_mapper: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None,
    delegation_bridge: _NativeTeamEventBridge | None = None,
    stream_message_id: str | None = None,
    timeline_writer: TeamTimelineWriter | None = None,
    use_timeline_text_finalize: bool = False,
    worker_message_ids: dict[str, str] | None = None,
    roster_members: list[str] | None = None,
    worker_drain_only: bool = False,
) -> AsyncGenerator[str, None]:
    """Run one QwenPaw agent turn and yield AgentDesk SSE events (no ``done``)."""
    if emit_stream_start:
        stream_start_evt: dict[str, Any] = {"type": "stream_start", "sender": sender}
        if stream_message_id:
            stream_start_evt["message_id"] = stream_message_id
        yield sse_line(sequencer.wrap(stream_start_evt))

    request.state.agent_id = agent_id

    try:
        (_model_slot, model_error), workspace = await asyncio.gather(
            ensure_chat_model(agent_id),
            get_agent_for_request(request, agent_id=agent_id),
        )
    except HTTPException as exc:
        turn_result["fatal"] = True
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": str(exc.detail),
                    "fatal": True,
                },
            ),
        )
        return

    if model_error:
        turn_result["fatal"] = True
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": model_error,
                    "fatal": True,
                },
            ),
        )
        return

    _schedule_sync_task_workspace(
        payload.task_id,
        agent_id,
        Path(workspace.workspace_dir),
        employee_name=payload.employee_name,
    )

    console_channel = await workspace.channel_manager.get_channel(_AGENTDESK_CHANNEL)
    if console_channel is None:
        turn_result["fatal"] = True
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": "Console channel is not ready",
                    "fatal": True,
                },
            ),
        )
        return

    session_id = _team_session_id(payload.task_id, session_suffix)
    set_current_session_id(session_id)
    set_current_root_session_id(session_id)
    native_payload = build_agentdesk_native_payload(
        task_id=session_id,
        message=agent_message,
        agent_id=agent_id,
    )
    session_id = console_channel.resolve_session_id(
        sender_id=native_payload["sender_id"],
        channel_meta=native_payload["meta"],
    )
    name, _first_text = _extract_placeholder_name(native_payload["content_parts"])
    chat = await workspace.chat_manager.get_or_create_chat(
        session_id,
        native_payload["sender_id"],
        native_payload["channel_id"],
        name=name or "AgentDesk",
    )

    tracker = workspace.task_tracker
    if worker_drain_only:
        stream_it = None
        pending_chunk = None
    else:
        queue, is_new = await tracker.attach_or_start(
            chat.id,
            native_payload,
            console_channel.stream_one,
        )
        if is_new:
            # Producer-tied safety net (parity with single-agent chat): if the
            # client disconnects mid-run the background producer keeps going to
            # completion; this watch finalizes the assistant message and closes
            # runStatus when the run ends, so the team leader turn never stays
            # stuck at streaming=true / runStatus=running. Arming via the helper
            # cancels the PREVIOUS round's watch so it cannot fire late and finalize
            # the reopened leader message / flip runStatus mid-round.
            _arm_leader_finalize_watch(
                task_id=payload.task_id,
                run_key=chat.id,
                tracker=tracker,
            )
        stream_it = tracker.stream_from_queue(queue, chat.id)
        pending_chunk = asyncio.create_task(stream_it.__anext__())

    translator = QwenPawStreamTranslator(sender=sender)
    fatal_error: str | None = None
    announced_approvals: set[str] = set()
    worker_stream_parents: dict[str, str | None] = {}
    last_heartbeat = time.monotonic()

    # Live worker observability: the leader delegates via the synchronous
    # ``chat_with_agent`` tool, whose worker run streams its SSE to the worker
    # bus keyed by the leader's (root) session id. Because ``root_session_id``
    # propagates across nested delegation, EVERY descendant agent (e.g. a planner
    # that further delegates to a searcher) publishes to the same bus, each item
    # tagged with its own source agent id. We therefore keep one translator per
    # source agent and attribute its trace (tool calls, thinking, search
    # progress) AND its final reply text to that agent's own bubble, so
    # multi-level teamwork stays observable and each worker's answer renders in
    # its own bubble in real time.
    #
    # The worker's reply is forwarded from its OWN stream (clean text, no
    # ``[SESSION: 鈥`` header). Delegation ``tool_result_end`` echoes are not
    # re-emitted as worker text; the worker stream bus is the single source of
    # truth for sync ``chat_with_agent`` replies.
    worker_translators: dict[str, QwenPawStreamTranslator] = {}
    worker_name_cache: dict[str, str] = {}
    worker_had_content: set[str] = set()
    worker_streamed_text: set[str] = set()
    _worker_message_ids: dict[str, str] = worker_message_ids or {}

    worker_bus = _TeamWorkerBusBridge.subscribe(
        task_id=payload.task_id,
        session_suffix=session_suffix,
        roster_members=roster_members,
        member_lookup=(
            delegation_bridge._member_lookup
            if delegation_bridge is not None
            else None
        ),
        enabled=delegation_bridge is not None,
    )
    bridged_worker_items = worker_bus.items

    async def _timeline_sse_lines(mapped_evt: dict[str, Any]) -> list[str]:
        return await _timeline_sse_lines_for_event(
            task_id=payload.task_id,
            timeline_writer=timeline_writer,
            mapped_evt=mapped_evt,
            sequencer=sequencer,
            leader_message_id=stream_message_id,
            worker_message_ids=_worker_message_ids,
            resolve_actor=(
                delegation_bridge._resolve_actor
                if delegation_bridge is not None
                else None
            ),
        )

    def _worker_display_name(agent_id: str) -> str:
        return _resolve_worker_display_name(agent_id, cache=worker_name_cache)

    def _tag_worker_event(evt: dict[str, Any], actor: str) -> dict[str, Any]:
        return _build_worker_event(
            evt,
            actor=actor,
            task_id=payload.task_id,
            worker_message_ids=_worker_message_ids,
        )

    def _worker_final_text(actor: str) -> str:
        return _select_worker_final_text(
            actor,
            translators=worker_translators,
            display_name_for=_worker_display_name,
            resolve_actor=(
                delegation_bridge._resolve_actor
                if delegation_bridge is not None
                else None
            ),
        )

    def _discard_worker_stream_state(actor: str) -> None:
        _clear_worker_stream_state(
            actor,
            translators=worker_translators,
            had_content=worker_had_content,
            streamed_text=worker_streamed_text,
            display_name_for=_worker_display_name,
            resolve_actor=(
                delegation_bridge._resolve_actor
                if delegation_bridge is not None
                else None
            ),
        )

    def _finalized_worker_trace_events() -> list[dict[str, Any]]:
        return _build_finalized_worker_trace_events(
            translators=worker_translators,
            display_name_for=_worker_display_name,
            tag_event=_tag_worker_event,
        )

    def _leftover_worker_bubbles() -> list[tuple[str, str, str]]:
        return _select_leftover_worker_bubbles(
            worker_message_ids=_worker_message_ids,
            had_content=worker_had_content,
            final_text_for=_worker_final_text,
        )

    async def _drain_worker_events() -> list[str]:
        out: list[str] = []
        while True:
            try:
                item = bridged_worker_items.get_nowait()
            except asyncio.QueueEmpty:
                break
            if not isinstance(item, tuple) or len(item) != 2:
                continue
            src_agent_id, raw = item
            if raw == WORKER_STREAM_DONE_SENTINEL:
                raw_agent_id = str(src_agent_id)
                display_name = _worker_display_name(raw_agent_id)
                actor = display_name
                if delegation_bridge is not None:
                    actor = (
                        delegation_bridge._resolve_actor(raw_agent_id)
                        or delegation_bridge._resolve_actor(display_name)
                        or display_name
                    )
                done_events: list[dict[str, Any]] = []
                if actor and delegation_bridge is not None:
                    done_events = delegation_bridge.emit_worker_done_from_bus(actor)
                if not payload.reconnect and actor:
                    for extra_line in await _drain_worker_events():
                        out.append(extra_line)
                    await asyncio.sleep(0)
                    worker_msg_id = _worker_message_ids.pop(actor, None)
                    if worker_msg_id and actor in worker_had_content:
                        reply_text = _worker_final_text(actor)
                        if reply_text:
                            try:
                                _schedule_append_assistant_delta(
                                    payload.task_id,
                                    reply_text,
                                    message_id=worker_msg_id,
                                )
                            except Exception:
                                logger.warning(
                                    "Failed to persist worker reply for task %s",
                                    payload.task_id,
                                    exc_info=True,
                                )
                        await task_store.finalize_assistant_message(
                            payload.task_id,
                            message_id=worker_msg_id,
                        )
                    elif worker_msg_id:
                        await task_store.finalize_assistant_message(
                            payload.task_id,
                            message_id=worker_msg_id,
                        )
                    _discard_worker_stream_state(actor)
                for done_evt in done_events:
                    call_id = str(done_evt.get("delegation_id") or "").strip()
                    worker_stream_parents.pop(call_id, None)
                    out.append(sse_line(sequencer.wrap(done_evt)))
                continue
            raw_agent_id = str(src_agent_id)
            display_name = _worker_display_name(raw_agent_id)
            actor = display_name
            if delegation_bridge is not None:
                actor = (
                    delegation_bridge._resolve_actor(raw_agent_id)
                    or delegation_bridge._resolve_actor(display_name)
                    or display_name
                )
            if not actor:
                continue
            translator = worker_translators.get(str(src_agent_id))
            if translator is None:
                translator = QwenPawStreamTranslator(sender=actor)
                worker_translators[str(src_agent_id)] = translator
            for w_evt in translate_sse_chunk(translator, raw):
                w_type = str(w_evt.get("type") or "")
                if w_type == "text_delta":
                    # Stream the worker's own reply, attributed to its bubble.
                    content = str(w_evt.get("content") or "")
                    if not content:
                        continue
                    worker_had_content.add(actor)
                    worker_streamed_text.add(actor)
                    if not payload.reconnect:
                        worker_msg_id = _worker_message_ids.get(actor)
                        if worker_msg_id:
                            try:
                                _schedule_append_assistant_delta(
                                    payload.task_id,
                                    content,
                                    message_id=worker_msg_id,
                                )
                            except Exception:
                                logger.warning(
                                    "Failed to append worker bus delta for task %s",
                                    payload.task_id,
                                    exc_info=True,
                                )
                    tagged = _tag_worker_event(w_evt, actor)
                    for tl in await _timeline_sse_lines(tagged):
                        out.append(tl)
                    out.append(
                        sse_line(sequencer.wrap(tagged)),
                    )
                    continue
                if w_type == "message":
                    # A delta-less worker emits only the final ``message``; use
                    # it as the reply. When deltas were already forwarded the
                    # message is redundant, so skip it to avoid double-printing.
                    content = str(w_evt.get("content") or "")
                    if actor in worker_streamed_text:
                        continue
                    if not content:
                        continue
                    worker_had_content.add(actor)
                    if not payload.reconnect:
                        worker_msg_id = _worker_message_ids.get(actor)
                        if worker_msg_id:
                            try:
                                _schedule_append_assistant_delta(
                                    payload.task_id,
                                    content,
                                    message_id=worker_msg_id,
                                )
                            except Exception:
                                logger.warning(
                                    "Failed to append worker bus message for task %s",
                                    payload.task_id,
                                    exc_info=True,
                                )
                    tagged = _tag_worker_event(w_evt, actor)
                    for tl in await _timeline_sse_lines(tagged):
                        out.append(tl)
                    out.append(
                        sse_line(sequencer.wrap(tagged)),
                    )
                    continue
                if w_type not in _TRACE_EVENT_TYPES:
                    # Skip worker error/content_reset: worker-internal lifecycle
                    # that must not leak into the team bubble.
                    continue
                tagged = _tag_worker_event(w_evt, actor)
                worker_had_content.add(actor)
                for tl in await _timeline_sse_lines(tagged):
                    out.append(tl)
                out.append(sse_line(sequencer.wrap(tagged)))
                if w_type not in {
                    "thinking_delta",
                    "thinking_retract",
                    "tool_result_delta",
                }:
                    # Persist the worker's process trace onto its OWN bubble so
                    # the member tab stays observable on reload (and the leader
                    # bubble isn't polluted with every worker's tool calls).
                    await _persist_trace_event(
                        payload.task_id,
                        tagged,
                        message_id=_worker_message_ids.get(actor),
                    )
        return out

    turn_start = time.monotonic()
    ttft_logged = False

    if worker_drain_only:
        try:
            idle_ticks = 0
            last_heartbeat = time.monotonic()
            while idle_ticks < _WORKER_DRAIN_IDLE_TICKS:
                for worker_line in await _drain_worker_events():
                    yield worker_line
                    idle_ticks = 0
                pending_members = await task_store.streaming_member_assistant_messages(
                    payload.task_id,
                    leader_sender=sender,
                )
                if pending_members:
                    idle_ticks = 0
                elif bridged_worker_items.empty():
                    idle_ticks += 1
                else:
                    idle_ticks = 0
                now = time.monotonic()
                if now - last_heartbeat >= _HEARTBEAT_INTERVAL_S:
                    yield sse_line(sequencer.wrap({"type": "heartbeat"}))
                    last_heartbeat = now
                await asyncio.sleep(0.05)
        finally:
            for worker_line in await _drain_worker_events():
                yield worker_line
            for tagged_tail in _finalized_worker_trace_events():
                yield sse_line(sequencer.wrap(tagged_tail))
                await _persist_trace_event(payload.task_id, tagged_tail)
            for _leftover_actor, leftover_id, reply_text in _leftover_worker_bubbles():
                try:
                    if reply_text:
                        _schedule_append_assistant_delta(
                            payload.task_id,
                            reply_text,
                            message_id=leftover_id,
                        )
                    await task_store.finalize_assistant_message(
                        payload.task_id,
                        message_id=leftover_id,
                    )
                except Exception:
                    logger.warning(
                        "Failed to finalize leftover worker bubble for task %s",
                        payload.task_id,
                        exc_info=True,
                    )
            _worker_message_ids.clear()
            await worker_bus.close()
        turn_result["final_text"] = ""
        turn_result["fatal"] = False
        return

    # TTFT instrumentation: measure how long the leader turn takes to produce its
    # first visible token after the native run is attached (i.e. model latency,
    # excluding cold start which the warm pool removes). Logged once per turn so
    # we can tell whether per-turn slowness is prep, model, or orchestration.

    try:
        while pending_chunk is not None:
            done, _ = await asyncio.wait({pending_chunk}, timeout=_APPROVAL_POLL_S)

            approval_evt = await _pending_approval_event(payload.task_id)
            if (
                approval_evt is not None
                and approval_evt["request_id"] not in announced_approvals
            ):
                announced_approvals.add(str(approval_evt["request_id"]))
                yield sse_line(sequencer.wrap(approval_evt))

            now = time.monotonic()
            if now - last_heartbeat >= _HEARTBEAT_INTERVAL_S:
                yield sse_line(sequencer.wrap({"type": "heartbeat"}))
                last_heartbeat = now

            for worker_line in await _drain_worker_events():
                yield worker_line

            if pending_chunk not in done:
                continue

            try:
                raw = pending_chunk.result()
            except StopAsyncIteration:
                break
            pending_chunk = asyncio.create_task(stream_it.__anext__())

            for evt in translate_sse_chunk(translator, raw):
                mapped_events = (
                    event_mapper(evt)
                    if event_mapper is not None
                    else [evt]
                )
                for mapped_evt in mapped_events:
                    evt_type = mapped_evt.get("type")
                    if not payload.reconnect and evt_type == "worker_start":
                        worker_sender = str(
                            mapped_evt.get("worker")
                            or mapped_evt.get("sender")
                            or "",
                        ).strip()
                        if worker_sender:
                            call_id = str(
                                mapped_evt.get("delegation_id") or "",
                            ).strip()
                            worker_stream_parents[call_id] = (
                                await task_store.current_assistant_message_id(
                                    payload.task_id,
                                )
                            )
                            # Create a dedicated, detached bubble for this worker
                            # so parallel replies persist to separate messages.
                            # The live SSE turn stays keyed by actor (no
                            # message_id on the event) to match later deltas.
                            if worker_sender not in _worker_message_ids:
                                worker_msg = await _begin_worker_assistant_message(
                                    payload.task_id,
                                    worker_sender,
                                )
                                _worker_message_ids[worker_sender] = str(
                                    worker_msg.get("id") or "",
                                )
                            worker_msg_id = _worker_message_ids.get(worker_sender)
                            if worker_msg_id:
                                mapped_evt = {
                                    **mapped_evt,
                                    "message_id": worker_msg_id,
                                }
                    if not payload.reconnect and evt_type == "worker_done":
                        # Flush any worker trace still buffered on the bus before
                        # the worker's reply bubble is finalized. A zero-delay
                        # yield lets pending cross-thread publishes land first.
                        for worker_line in await _drain_worker_events():
                            yield worker_line
                        await asyncio.sleep(0)
                        for worker_line in await _drain_worker_events():
                            yield worker_line
                        await asyncio.sleep(0.05)
                        for worker_line in await _drain_worker_events():
                            yield worker_line
                        call_id = str(
                            mapped_evt.get("delegation_id") or "",
                        ).strip()
                        worker_stream_parents.pop(call_id, None)
                        worker_actor = str(
                            mapped_evt.get("worker")
                            or mapped_evt.get("sender")
                            or "",
                        ).strip()
                        worker_msg_id = _worker_message_ids.pop(worker_actor, None)
                        if worker_msg_id:
                            mapped_evt = {
                                **mapped_evt,
                                "message_id": worker_msg_id,
                            }
                        # When the worker streamed its reply live via the bus,
                        # persist that clean text onto its OWN message (the
                        # leader echo was suppressed, so the message is empty).
                        if (
                            worker_msg_id
                            and worker_actor
                            and worker_actor in worker_had_content
                        ):
                            reply_text = _worker_final_text(worker_actor)
                            if reply_text:
                                try:
                                    _schedule_append_assistant_delta(
                                        payload.task_id,
                                        reply_text,
                                        message_id=worker_msg_id,
                                    )
                                except Exception:
                                    logger.warning(
                                        "Failed to persist worker reply for "
                                        "task %s",
                                        payload.task_id,
                                        exc_info=True,
                                    )
                        if worker_msg_id:
                            await task_store.finalize_assistant_message(
                                payload.task_id,
                                message_id=worker_msg_id,
                            )
                        # Reset this worker's stream state so a later
                        # re-delegation to the same agent starts fresh.
                        if worker_actor:
                            _discard_worker_stream_state(worker_actor)
                    if evt_type == "error" and mapped_evt.get("fatal"):
                        fatal_error = str(mapped_evt.get("content") or fatal_error or "")
                    if evt_type == "content_reset":
                        try:
                            await task_store.reset_assistant_content(payload.task_id)
                        except Exception:
                            logger.warning(
                                "Failed to reset assistant content for task %s",
                                payload.task_id,
                                exc_info=True,
                            )
                        yield sse_line(sequencer.wrap(mapped_evt))
                        for tl in await _timeline_sse_lines(mapped_evt):
                            yield tl
                        continue
                    if evt_type == "text_delta":
                        if not ttft_logged:
                            ttft_logged = True
                            logger.info(
                                "TTFT leader=%s task=%s first_token=%.2fs",
                                sender,
                                payload.task_id,
                                time.monotonic() - turn_start,
                            )
                        same_sender = str(mapped_evt.get("sender") or sender) == sender
                        worker_actor = ""
                        if not same_sender:
                            worker_actor = str(
                                mapped_evt.get("sender") or "",
                            ).strip()
                        content = str(mapped_evt.get("content") or "")
                        # Leader-stream worker echoes: persist onto the member
                        # bubble only. Live member UI reads the worker bus and
                        # member timeline; skip leader SSE text_delta fan-out.
                        if worker_actor and not payload.reconnect:
                            worker_msg_id = _worker_message_ids.get(worker_actor)
                            if worker_msg_id and content:
                                try:
                                    _schedule_append_assistant_delta(
                                        payload.task_id,
                                        content,
                                        message_id=worker_msg_id,
                                    )
                                except Exception:
                                    logger.warning(
                                        "Failed to append worker delta for task %s",
                                        payload.task_id,
                                        exc_info=True,
                                    )
                            continue
                        for tl in await _timeline_sse_lines(mapped_evt):
                            yield tl
                        suppress_leader_status = (
                            use_timeline_text_finalize
                            and same_sender
                            and classify_leader_narration(content)[0] == "phase"
                        )
                        if suppress_leader_status:
                            yield sse_line(
                                sequencer.wrap(
                                    {
                                        "type": "team_phase",
                                        "phase": "round_progress",
                                        "label": content.strip()[:240],
                                        "sender": sender,
                                        "message_id": stream_message_id,
                                    },
                                    source="team",
                                    source_member=sender,
                                ),
                            )
                            continue
                        yield sse_line(sequencer.wrap(mapped_evt))
                        if not payload.reconnect and same_sender:
                            try:
                                _schedule_append_assistant_delta(
                                    payload.task_id,
                                    content,
                                )
                            except Exception:
                                logger.warning(
                                    "Failed to append assistant delta for task %s",
                                    payload.task_id,
                                    exc_info=True,
                                )
                        continue
                    if evt_type == "artifact":
                        if not payload.reconnect:
                            artifact_payload = artifact_payload_from_evt(mapped_evt)
                            if artifact_payload:
                                await task_store.append_assistant_artifacts(
                                    payload.task_id,
                                    [artifact_payload],
                                    message_id=stream_message_id,
                                )
                        yield sse_line(sequencer.wrap(mapped_evt))
                        for tl in await _timeline_sse_lines(mapped_evt):
                            yield tl
                        continue
                    if evt_type in _TRACE_EVENT_TYPES:
                        step = evt_type
                        leader_evt = _tag_leader_trace_event(mapped_evt, sender=sender)
                        if step in {
                            "thinking_delta",
                            "thinking_retract",
                            "tool_result_delta",
                        }:
                            yield sse_line(
                                sequencer.wrap(
                                    leader_evt,
                                    source="team",
                                    source_member=sender,
                                ),
                            )
                            continue
                        yield sse_line(
                            sequencer.wrap(
                                leader_evt,
                                source="team",
                                source_member=sender,
                            ),
                        )
                        for tl in await _timeline_sse_lines(mapped_evt):
                            yield tl
                        if not payload.reconnect:
                            await _persist_trace_event(
                                payload.task_id,
                                leader_evt,
                                message_id=stream_message_id,
                            )
                        continue
                    for tl in await _timeline_sse_lines(mapped_evt):
                        yield tl
                    yield sse_line(sequencer.wrap(mapped_evt))

    finally:
        for worker_line in await _drain_worker_events():
            yield worker_line
        for tagged_tail in _finalized_worker_trace_events():
            yield sse_line(sequencer.wrap(tagged_tail))
            await _persist_trace_event(payload.task_id, tagged_tail)
        # Finalize any worker bubbles that never received an explicit
        # ``worker_done`` (e.g. the run was stopped mid-flight) so they don't
        # stay stuck in the streaming state on reload.
        for _leftover_actor, leftover_id, reply_text in _leftover_worker_bubbles():
            try:
                if reply_text:
                    _schedule_append_assistant_delta(
                        payload.task_id,
                        reply_text,
                        message_id=leftover_id,
                    )
                await task_store.finalize_assistant_message(
                    payload.task_id,
                    message_id=leftover_id,
                )
            except Exception:
                logger.warning(
                    "Failed to finalize leftover worker bubble for task %s",
                    payload.task_id,
                    exc_info=True,
                )
        _worker_message_ids.clear()
        await worker_bus.close()
        if pending_chunk is not None and not pending_chunk.done():
            pending_chunk.cancel()
        if pending_chunk is not None:
            with suppress(asyncio.CancelledError, StopAsyncIteration):
                await pending_chunk
        with suppress(Exception):
            await stream_it.aclose()

    for evt in translator.finalize_pending_tools():
        leader_evt = _tag_leader_trace_event(evt, sender=sender)
        yield sse_line(sequencer.wrap(leader_evt, source="team", source_member=sender))
        await _persist_trace_event(
            payload.task_id,
            leader_evt,
            message_id=stream_message_id,
        )

    for evt in translator.finalize_pending_thinking():
        leader_evt = _tag_leader_trace_event(evt, sender=sender)
        yield sse_line(sequencer.wrap(leader_evt, source="team", source_member=sender))
        await _persist_trace_event(
            payload.task_id,
            leader_evt,
            message_id=stream_message_id,
        )

    for evt in translator.finalize_answer_fallback():
        yield sse_line(sequencer.wrap(evt))
        if evt.get("type") == "text_delta":
            _schedule_append_assistant_delta(
                payload.task_id,
                str(evt.get("content") or ""),
            )

    if use_timeline_text_finalize and timeline_writer is not None:
        final_text = (
            timeline_writer.leader_answer_text()
            or filter_leader_persist_text(translator.current_segment_text())
        )
    elif use_timeline_text_finalize:
        final_text = filter_leader_persist_text(translator.current_segment_text())
    else:
        final_text = translator.final_text()
    raw_final = (translator.final_text() or "").strip()
    if not str(final_text or "").strip() and raw_final:
        filtered = filter_leader_persist_text(raw_final)
        final_text = filtered or raw_final
    if fatal_error:
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": fatal_error,
                    "fatal": True,
                },
            ),
        )

    await task_store.finalize_assistant_message(
        payload.task_id,
        content=final_text or None,
    )
    turn_result["final_text"] = final_text
    turn_result["fatal"] = bool(fatal_error)


async def _run_coordinated_team_round(
    *,
    payload: ChatRequest,
    request: Request,
    sequencer: StreamEventSequencer,
    team_name: str,
    leader_sender: str,
    leader_agent_id: str,
    user_text: str,
    leader_message_id: str,
    members: list[str],
    timeline_writer: TeamTimelineWriter | None = None,
) -> AsyncGenerator[str, None]:
    """One native leader run (delegation + synthesis inside QwenPaw), then completion."""
    bridge = _NativeTeamEventBridge(members=members, leader_sender=leader_sender)
    leader_turn: dict[str, Any] = {"final_text": "", "fatal": False}
    round_worker_message_ids: dict[str, str] = {}

    leader_message = f"{build_chat_response_language_hint(user_text)}{user_text}"
    async for line in _stream_agent_turn(
        payload=payload,
        request=request,
        agent_id=leader_agent_id,
        sender=leader_sender,
        agent_message=leader_message,
        sequencer=sequencer,
        session_suffix=_TEAM_LEADER_SESSION_SUFFIX,
        emit_stream_start=True,
        stream_message_id=leader_message_id,
        turn_result=leader_turn,
        event_mapper=bridge.map_event,
        delegation_bridge=bridge,
        timeline_writer=timeline_writer,
        use_timeline_text_finalize=timeline_writer is not None,
        worker_message_ids=round_worker_message_ids,
        roster_members=members,
    ):
        yield line

    async for line in _yield_team_turn_completion(
        payload=payload,
        sequencer=sequencer,
        team_name=team_name,
        leader_sender=leader_sender,
        leader_message_id=leader_message_id,
        leader_turn=leader_turn,
        timeline_writer=timeline_writer,
        timed_out_workers=bridge.timed_out_workers(),
        bridge=bridge,
        worker_message_ids=round_worker_message_ids,
    ):
        yield line


async def _stream_team_worker_reconnect(
    *,
    payload: ChatRequest,
    request: Request,
    sequencer: StreamEventSequencer,
    team_name: str,
    leader_sender: str,
    leader_agent_id: str,
    members: list[str],
    leader_message_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Reconnect when the leader native run finished but workers are still active."""
    bridge = _NativeTeamEventBridge(members=members, leader_sender=leader_sender)
    pending_members = await task_store.streaming_member_assistant_messages(
        payload.task_id,
        leader_sender=leader_sender,
    )
    worker_message_ids = {
        str(msg.get("sender") or ""): str(msg.get("id") or "")
        for msg in pending_members
        if str(msg.get("sender") or "").strip() and str(msg.get("id") or "").strip()
    }
    for msg in pending_members:
        sender = str(msg.get("sender") or "").strip()
        msg_id = str(msg.get("id") or "").strip()
        if not sender or not msg_id:
            continue
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "stream_start",
                    "sender": sender,
                    "message_id": msg_id,
                },
            ),
        )
    await asyncio.to_thread(
        _commit_task_run_status, payload.task_id, _RUN_STATUS_RUNNING,
    )
    leader_turn: dict[str, Any] = {"final_text": "", "fatal": False}
    async for line in _stream_agent_turn(
        payload=payload,
        request=request,
        agent_id=leader_agent_id,
        sender=leader_sender,
        agent_message="",
        sequencer=sequencer,
        session_suffix=_TEAM_LEADER_SESSION_SUFFIX,
        emit_stream_start=False,
        turn_result=leader_turn,
        event_mapper=bridge.map_event,
        delegation_bridge=bridge,
        stream_message_id=leader_message_id,
        roster_members=members,
        worker_message_ids=worker_message_ids,
        worker_drain_only=True,
    ):
        yield line
    async for line in _yield_team_turn_completion(
        payload=payload,
        sequencer=sequencer,
        team_name=team_name,
        leader_sender=leader_sender,
        leader_message_id=leader_message_id,
        leader_turn=leader_turn,
        timed_out_workers=bridge.timed_out_workers(),
        bridge=bridge,
        worker_message_ids=worker_message_ids,
    ):
        yield line


async def stream_team_chat(
    payload: ChatRequest,
    request: Request,
) -> AsyncGenerator[str, None]:
    """Team-mode chat: one native leader run with delegation event mapping."""
    sequencer = StreamEventSequencer(task_id=payload.task_id)
    team = resolve_team_record(payload)
    if team is None:
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": "Team not found. Create or select a valid team first.",
                    "fatal": True,
                },
            ),
        )
        return

    team_name = str(team.get("name") or payload.team_name or "").strip()
    members = [
        str(name).strip()
        for name in (team.get("members") or [])
        if str(name).strip()
    ]

    member_watch = str(payload.team_member or "").strip()
    if member_watch:
        async for line in _stream_team_member_watch(
            payload,
            request,
            sequencer,
            member_watch,
        ):
            yield line
        return

    if payload.chat_mode == "plan":
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": "Team mode does not support plan mode yet.",
                    "fatal": True,
                },
            ),
        )
        return

    await task_store.ensure_task(payload.task_id)
    user_text = (payload.message or "").strip()

    if payload.reconnect:
        try:
            leader_info = await asyncio.to_thread(sync_team_leader_agent, team)
        except ValueError as exc:
            yield sse_line(
                sequencer.wrap(
                    {
                        "type": "error",
                        "content": str(exc),
                        "fatal": True,
                    },
                ),
            )
            return

        leader_agent_id = leader_info["agent_id"]
        leader_sender = leader_info.get("leader_name") or team_leader_display_name(
            team_name,
        )

        try:
            resolved = await _resolve_team_leader_chat(
                task_id=payload.task_id,
                request=request,
                leader_agent_id=leader_agent_id,
            )
        except HTTPException:
            resolved = None

        if resolved is None:
            if _is_task_running(payload.task_id):
                async for line in _stream_team_worker_reconnect(
                    payload=payload,
                    request=request,
                    sequencer=sequencer,
                    team_name=team_name,
                    leader_sender=leader_sender,
                    leader_agent_id=leader_agent_id,
                    members=members,
                ):
                    yield line
                return
            yield sse_line(
                sequencer.wrap(await _build_done_event(payload.task_id, finalize=True)),
            )
            return

        workspace, chat_id = resolved
        if await workspace.task_tracker.get_status(chat_id) != _RUN_STATUS_RUNNING:
            if _is_task_running(payload.task_id):
                stream_message_id = await task_store.current_assistant_message_id(
                    payload.task_id,
                )
                async for line in _stream_team_worker_reconnect(
                    payload=payload,
                    request=request,
                    sequencer=sequencer,
                    team_name=team_name,
                    leader_sender=leader_sender,
                    leader_agent_id=leader_agent_id,
                    members=members,
                    leader_message_id=stream_message_id,
                ):
                    yield line
                return
            yield sse_line(
                sequencer.wrap(await _build_done_event(payload.task_id, finalize=True)),
            )
            return

        await asyncio.to_thread(
            _commit_task_run_status, payload.task_id, _RUN_STATUS_RUNNING,
        )
        stream_message_id = await task_store.current_assistant_message_id(
            payload.task_id,
        )
        if stream_message_id:
            yield sse_line(
                sequencer.wrap(
                    {
                        "type": "stream_start",
                        "sender": leader_sender,
                        "message_id": stream_message_id,
                    },
                ),
            )

        bridge = _NativeTeamEventBridge(
            members=members,
            leader_sender=leader_sender,
        )
        leader_turn: dict[str, Any] = {"final_text": "", "fatal": False}
        async for line in _stream_agent_turn(
            payload=payload,
            request=request,
            agent_id=leader_agent_id,
            sender=leader_sender,
            agent_message="",
            sequencer=sequencer,
            session_suffix=_TEAM_LEADER_SESSION_SUFFIX,
            emit_stream_start=False,
            turn_result=leader_turn,
            event_mapper=bridge.map_event,
            delegation_bridge=bridge,
            stream_message_id=stream_message_id,
            roster_members=members,
        ):
            yield line
        async for line in _yield_team_turn_completion(
            payload=payload,
            sequencer=sequencer,
            team_name=team_name,
            leader_sender=leader_sender,
            leader_message_id=stream_message_id,
            leader_turn=leader_turn,
            timed_out_workers=bridge.timed_out_workers(),
            bridge=bridge,
            worker_message_ids={},
        ):
            yield line
        return

    if not user_text:
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": "娑堟伅涓嶈兘涓虹┖",
                    "fatal": True,
                },
            ),
        )
        return

    await task_store.append_user_message(payload.task_id, user_text)
    _spawn_background(
        asyncio.to_thread(_commit_task_run_status, payload.task_id, _RUN_STATUS_RUNNING),
    )

    leader_sender = team_leader_display_name(team_name)
    team_id = str(team.get("id") or "").strip()
    stored_leader_id = str(team.get("leader_agent_id") or "").strip()
    if not stored_leader_id or not is_team_leader_agent_id(stored_leader_id):
        stored_leader_id = team_leader_agent_id(team_id)

    async def _warm_leader_runtime() -> tuple[Any, Any]:
        return await asyncio.gather(
            ensure_chat_model(stored_leader_id),
            get_agent_for_request(request, agent_id=stored_leader_id),
        )

    warm_task = asyncio.create_task(_warm_leader_runtime())
    sync_task = asyncio.create_task(asyncio.to_thread(sync_team_leader_agent, team))

    planning_evt = {
        "type": "team_phase",
        "phase": "planning",
        "label": f"{team_name} leader is planning",
        "source_member": leader_sender,
    }
    yield sse_line(
        sequencer.wrap(
            planning_evt,
            source="team",
            source_member=leader_sender,
        ),
    )

    try:
        leader_info = await sync_task
    except ValueError as exc:
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": str(exc),
                    "fatal": True,
                },
            ),
        )
        return

    leader_agent_id = leader_info["agent_id"]
    leader_sender = leader_info.get("leader_name") or leader_sender

    with suppress(asyncio.CancelledError, Exception):
        await warm_task

    leader_draft = await task_store.begin_assistant_message(
        payload.task_id,
        sender=leader_sender,
        session_id=_team_session_id(payload.task_id, _TEAM_LEADER_SESSION_SUFFIX),
    )

    try:
        async for line in _run_coordinated_team_round(
            payload=payload,
            request=request,
            sequencer=sequencer,
            team_name=team_name,
            leader_sender=leader_sender,
            leader_agent_id=leader_agent_id,
            user_text=user_text,
            leader_message_id=str(leader_draft.get("id") or ""),
            members=members,
        ):
            yield line

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("AgentDesk team chat error task_id=%s", payload.task_id)
        await task_store.finalize_assistant_message(payload.task_id)
        await asyncio.to_thread(
            _set_task_run_status, payload.task_id, _RUN_STATUS_IDLE,
        )
        user_message = format_agentdesk_stream_error(
            exc,
            default="Team chat failed. Please retry.",
        )
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": user_message,
                    "fatal": True,
                },
            ),
        )
        yield sse_line(sequencer.wrap(await _build_done_event(payload.task_id)))
