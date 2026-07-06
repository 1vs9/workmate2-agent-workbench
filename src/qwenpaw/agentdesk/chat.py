# -*- coding: utf-8 -*-
"""AgentDesk chat streaming — bridge to QwenPaw console runner."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, AsyncGenerator, AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from qwenpaw.exceptions import SkillsError

from ..app.agent_context import get_agent_for_request
from ..app.approvals import get_approval_service
from ..app.routers.console import _extract_placeholder_name
from ..app.utils import schedule_agent_reload
from ..security.tool_guard.approval import ApprovalDecision
from .agent_workspace import (
    agent_workspace_dir as _agent_workspace_dir,
    resolve_active_agentdesk_agent_id,
)
from .agents import display_sender, lookup_agent_id, resolve_agent_id
from .agent_reload import reload_agent_after_skill_mount as _reload_agent_after_skill_mount
from .background_tasks import spawn_background
from .model_config import ensure_chat_model
from .models import ChatRequest
from .native_payload import build_agentdesk_native_payload
from .run_status import (
    RUN_STATUS_IDLE as _RUN_STATUS_IDLE,
    RUN_STATUS_RUNNING as _RUN_STATUS_RUNNING,
    commit_task_run_status as _commit_task_run_status,
    set_task_run_status as _set_task_run_status,
)
from .chat_skill_mount import (
    dedupe_skill_names as _dedupe_skill_names,
    ensure_payload_skills_mounted as _ensure_payload_skills_mounted,
)
from .chat_message_composer import (
    augment_user_message_with_skills as _compose_user_message_with_skills,
    resolve_chat_user_messages as _compose_chat_user_messages,
)
from .chat_runtime import (
    SingleChatRuntime as _SingleChatRuntime,
    prepare_single_chat_runtime as _prepare_single_chat_runtime_impl,
    prepare_single_chat_runtime_fast as _prepare_single_chat_runtime_fast_impl,
)
from .chat_event_stream import emit_translated_events as _emit_translated_events_impl
from .chat_task_target import schedule_task_chat_target as _schedule_task_chat_target
from .chat_turn_lifecycle import finalize_failed_turn as _finalize_failed_turn
from .skill_mount import ensure_skill_mounted
from .session_bridge import (
    AGENTDESK_SESSION_CHANNEL,
    AGENTDESK_SESSION_USER_ID,
)
from .session_routing import coerce_team_routing_from_store
from .skill_wizard import (
    SKILL_WIZARD_SENDER,
    build_skill_create_agent_message,
    build_skill_done_wizard,
    build_skill_failed_wizard,
    ensure_skill_creator_mounted,
    is_skill_create_message,
    is_skill_find_message,
    load_created_skill,
    parse_materialize_skill_success,
    persist_task_wizard,
    resolve_skill_wizard_agent_id,
    sync_created_skill_to_pool_and_store,
)
from .sse import sse_line
from .stream_protocol import StreamEventSequencer, artifact_payload_from_evt
from .stream_runtime import (
    APPROVAL_POLL_S,
    HEARTBEAT_INTERVAL_S,
    iter_with_heartbeat as _iter_with_heartbeat,
    pending_approval_event,
    tag_turn_event as _tag_turn_event,
)
from .stream_side_effects import (
    RUN_WATCH_POLL_S,
    schedule_append_assistant_delta,
    schedule_run_finalize_watch,
)
from .stream_translator import QwenPawStreamTranslator, translate_sse_chunk
from .store import format_agentdesk_persistence_error, store as agentdesk_store
from .task_store import task_store
from .task_workspace_sync import schedule_sync_task_workspace, sync_task_workspace
from .trace_events import (
    TRACE_EVENT_TYPES,
    persist_trace_event,
    schedule_persist_trace_event,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["agentdesk-chat"])

_RUN_WATCH_POLL_S = RUN_WATCH_POLL_S

_spawn_background = spawn_background


_schedule_append_assistant_delta = schedule_append_assistant_delta


_schedule_sync_task_workspace = schedule_sync_task_workspace


_schedule_run_finalize_watch = schedule_run_finalize_watch

_AGENTDESK_USER_ID = AGENTDESK_SESSION_USER_ID
_AGENTDESK_CHANNEL = AGENTDESK_SESSION_CHANNEL
_HEARTBEAT_INTERVAL_S = HEARTBEAT_INTERVAL_S
_APPROVAL_POLL_S = APPROVAL_POLL_S
_TRACE_EVENT_TYPES = TRACE_EVENT_TYPES


_pending_approval_event = pending_approval_event


_persist_trace_event = persist_trace_event
_schedule_persist_trace_event = schedule_persist_trace_event


async def _prepare_single_chat_runtime_fast(
    payload: ChatRequest,
    request: Request,
    agent_id: str,
) -> _SingleChatRuntime:
    return await _prepare_single_chat_runtime_fast_impl(
        payload,
        request,
        agent_id,
        resolve_agent_id_fn=resolve_agent_id,
        get_agent_for_request_fn=get_agent_for_request,
        ensure_chat_model_fn=ensure_chat_model,
    )


async def _prepare_single_chat_runtime(
    payload: ChatRequest,
    request: Request,
    agent_id: str,
) -> _SingleChatRuntime:
    """Parallel prep (legacy entry — tests and callers that need bundled mount)."""
    return await _prepare_single_chat_runtime_impl(
        payload,
        request,
        agent_id,
        resolve_agent_id_fn=resolve_agent_id,
        get_agent_for_request_fn=get_agent_for_request,
        ensure_chat_model_fn=ensure_chat_model,
        dedupe_skill_names_fn=_dedupe_skill_names,
        ensure_payload_skills_mounted_fn=_ensure_payload_skills_mounted,
        reload_agent_after_skill_mount_fn=_reload_agent_after_skill_mount,
    )


async def _stream_chat_reconnect(
    *,
    payload: ChatRequest,
    request: Request,
    agent_id: str,
    sender: str,
    sequencer: StreamEventSequencer,
) -> AsyncGenerator[str, None]:
    """Attach to an in-flight native run without skill/model prep."""
    if not hasattr(request.state, "agent_id") or request.state.agent_id is None:
        request.state.agent_id = agent_id
    workspace = await get_agent_for_request(request, agent_id=agent_id)
    console_channel = await workspace.channel_manager.get_channel(_AGENTDESK_CHANNEL)
    if console_channel is None:
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": "Console 通道未就绪",
                    "fatal": True,
                },
            ),
        )
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "done",
                    "messages": await task_store.get_messages(payload.task_id),
                },
            ),
        )
        return

    tracker = workspace.task_tracker
    session_id = console_channel.resolve_session_id(
        sender_id=_AGENTDESK_USER_ID,
        channel_meta={"session_id": payload.task_id},
    )
    chat = await workspace.chat_manager.get_or_create_chat(
        session_id,
        _AGENTDESK_USER_ID,
        _AGENTDESK_CHANNEL,
        name="AgentDesk",
    )
    queue = await tracker.attach(chat.id)
    if queue is None:
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "done",
                    "messages": await task_store.get_messages(payload.task_id),
                },
            ),
        )
        return
    await task_store.resume_streaming_assistant(payload.task_id)
    await asyncio.to_thread(
        _commit_task_run_status, payload.task_id, _RUN_STATUS_RUNNING,
    )
    stream_message_id = await task_store.current_assistant_message_id(payload.task_id)
    if stream_message_id:
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "stream_start",
                    "sender": sender,
                    "message_id": stream_message_id,
                },
            ),
        )
    stream_it = tracker.stream_from_queue(queue, chat.id)
    async for line in _emit_translated_events(
        payload=payload,
        sender=sender,
        sequencer=sequencer,
        stream_it=stream_it,
        tracker=tracker,
        run_key=chat.id,
        stream_message_id=stream_message_id,
        agent_id=agent_id,
    ):
        yield line


def augment_user_message_with_skills(
    workspace_dir: Path,
    user_text: str,
    skill_names: list[str],
) -> str:
    return _compose_user_message_with_skills(workspace_dir, user_text, skill_names)


def resolve_chat_user_messages(
    workspace_dir: Path,
    user_text: str,
    skill_names: list[str],
) -> tuple[str, str]:
    return _compose_chat_user_messages(workspace_dir, user_text, skill_names)


async def _emit_translated_events(
    *,
    payload: ChatRequest,
    sender: str,
    sequencer: StreamEventSequencer,
    stream_it: AsyncIterator[str],
    tracker: Any | None = None,
    run_key: str | None = None,
    stream_message_id: str | None = None,
    agent_id: str | None = None,
) -> AsyncGenerator[str, None]:
    async for line in _emit_translated_events_impl(
        payload=payload,
        sender=sender,
        sequencer=sequencer,
        stream_it=stream_it,
        tracker=tracker,
        run_key=run_key,
        stream_message_id=stream_message_id,
        agent_id=agent_id,
        task_store_obj=task_store,
        pending_approval_event_fn=_pending_approval_event,
        approval_poll_s=_APPROVAL_POLL_S,
        heartbeat_interval_s=_HEARTBEAT_INTERVAL_S,
        trace_event_types=_TRACE_EVENT_TYPES,
        schedule_persist_trace_event_fn=_schedule_persist_trace_event,
        persist_trace_event_fn=_persist_trace_event,
        commit_task_run_status_fn=_commit_task_run_status,
    ):
        yield line


async def _stream_skill_wizard(
    payload: ChatRequest,
    request: Request,
) -> AsyncGenerator[str, None]:
    """One-sentence skill creation via make-skill agent orchestration."""
    sequencer = StreamEventSequencer(task_id=payload.task_id)
    agent_id = resolve_skill_wizard_agent_id(payload.employee_name)
    sender = SKILL_WIZARD_SENDER
    action = payload.wizard_action

    if payload.intent != "skill_create":
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": "当前仅支持技能创建向导。",
                    "fatal": True,
                },
            ),
        )
        return

    await task_store.ensure_task(payload.task_id)

    if action == "cancel":
        wizard = {
            "kind": "skill_create",
            "status": "skill_cancelled",
            "questions": [],
            "answers": {},
        }
        persist_task_wizard(payload.task_id, wizard)
        yield sse_line(sequencer.wrap({"type": "wizard_update", "wizard": wizard}))
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "done",
                    "messages": await task_store.get_messages(payload.task_id),
                },
            ),
        )
        return

    if action != "start":
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": "一句话创建技能请直接描述需求；多步问卷尚未开放。",
                    "fatal": True,
                },
            ),
        )
        return

    user_text = (payload.message or "").strip()
    if not user_text:
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": "请用一句话描述要创建的技能。",
                    "fatal": True,
                },
            ),
        )
        return

    _model_slot, model_error = await ensure_chat_model(agent_id)
    if model_error:
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

    if not hasattr(request.state, "agent_id") or request.state.agent_id is None:
        request.state.agent_id = agent_id

    try:
        mounted_skills = ensure_skill_creator_mounted(
            agent_id=agent_id,
            request=request,
            user_text=user_text,
        )
        workspace = await get_agent_for_request(request, agent_id=agent_id)
        if await _reload_agent_after_skill_mount(request, agent_id):
            workspace = await get_agent_for_request(request, agent_id=agent_id)
        sync_task_workspace(
            payload.task_id,
            agent_id,
            Path(workspace.workspace_dir),
            employee_name=payload.employee_name,
        )
    except HTTPException as exc:
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
    except SkillsError as exc:
        err = str(exc)
        yield sse_line(
            sequencer.wrap({"type": "error", "content": err, "fatal": True}),
        )
        return

    console_channel = await workspace.channel_manager.get_channel(_AGENTDESK_CHANNEL)
    if console_channel is None:
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": "Console 通道未就绪",
                    "fatal": True,
                },
            ),
        )
        return

    await task_store.append_user_message(payload.task_id, user_text)
    assistant_draft = await task_store.begin_assistant_message(payload.task_id, sender=sender)
    _set_task_run_status(payload.task_id, _RUN_STATUS_RUNNING)
    yield sse_line(
        sequencer.wrap(
            {
                "type": "stream_start",
                "sender": sender,
                "message_id": assistant_draft.get("id"),
            },
        ),
    )

    creating_trace = {
        "type": "skill_create",
        "label": "正在通过 skill-creator 编排生成技能…",
    }
    await _persist_trace_event(payload.task_id, creating_trace)
    yield sse_line(sequencer.wrap(creating_trace))

    skill_trace = {
        "type": "skills_active",
        "label": f"已加载技能: {', '.join(mounted_skills)}",
        "skills": mounted_skills,
    }
    await _persist_trace_event(payload.task_id, skill_trace)
    yield sse_line(sequencer.wrap(skill_trace))

    agent_message = build_skill_create_agent_message(user_text)
    agent_message = augment_user_message_with_skills(
        Path(workspace.workspace_dir),
        agent_message,
        mounted_skills,
    )

    native_payload = build_agentdesk_native_payload(
        task_id=payload.task_id,
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
    queue, is_new = await tracker.attach_or_start(
        chat.id,
        native_payload,
        console_channel.stream_one,
    )
    if is_new:
        _schedule_run_finalize_watch(
            task_id=payload.task_id,
            run_key=chat.id,
            tracker=tracker,
        )
    stream_it = tracker.stream_from_queue(queue, chat.id)
    translator = QwenPawStreamTranslator(sender=sender)
    materialize_attempted = False
    created_skill_name: str | None = None

    try:
        async for raw in _iter_with_heartbeat(stream_it):
            if raw is None:
                yield sse_line(sequencer.wrap({"type": "heartbeat"}))
                continue
            for evt in translate_sse_chunk(translator, raw):
                evt_type = str(evt.get("type") or "")
                if evt_type in _TRACE_EVENT_TYPES:
                    step = evt_type
                    tool_name = str(evt.get("tool_name") or "")
                    if step == "tool_call_end" and tool_name == "materialize_skill":
                        materialize_attempted = True
                    if step == "tool_result_end" and tool_name == "materialize_skill":
                        materialize_attempted = True
                        parsed = parse_materialize_skill_success(str(evt.get("detail") or ""))
                        if parsed:
                            created_skill_name = parsed
                    if step == "thinking_delta":
                        yield sse_line(sequencer.wrap(evt))
                        continue
                    if step == "thinking_retract":
                        yield sse_line(sequencer.wrap(evt))
                        continue
                    if step == "tool_result_delta":
                        yield sse_line(sequencer.wrap(evt))
                        continue
                    yield sse_line(sequencer.wrap(evt))
                    _schedule_persist_trace_event(payload.task_id, evt)
                    continue
                if evt.get("type") == "content_reset":
                    await task_store.reset_assistant_content(payload.task_id)
                    yield sse_line(sequencer.wrap(evt))
                    continue
                if evt.get("type") == "text_delta":
                    yield sse_line(sequencer.wrap(evt))
                    await task_store.append_assistant_delta(
                        payload.task_id,
                        str(evt.get("content") or ""),
                    )
                    continue
                if evt_type == "artifact":
                    artifact_payload = artifact_payload_from_evt(evt)
                    if artifact_payload:
                        await task_store.append_assistant_artifacts(
                            payload.task_id,
                            [artifact_payload],
                            message_id=str(assistant_draft.get("id") or "") or None,
                        )
                    yield sse_line(sequencer.wrap(evt))
                    continue
                yield sse_line(sequencer.wrap(evt))
        for evt in translator.finalize_pending_tools():
            yield sse_line(sequencer.wrap(evt))
            _schedule_persist_trace_event(payload.task_id, evt)
        for evt in translator.finalize_pending_thinking():
            yield sse_line(sequencer.wrap(evt))
            _schedule_persist_trace_event(payload.task_id, evt)
        for evt in translator.finalize_answer_fallback():
            yield sse_line(sequencer.wrap(evt))
            if evt.get("type") == "text_delta":
                await task_store.append_assistant_delta(
                    payload.task_id,
                    str(evt.get("content") or ""),
                )
    finally:
        await stream_it.aclose()

    # End the visible reply before pool sync / mount tail work so the UI does
    # not keep the streaming cursor while we mirror the skill and reload agents.
    reply_end = _tag_turn_event(
        {
            "type": "reply_end",
            "label": "本轮回复结束",
        },
        sender=sender,
        message_id=str(assistant_draft.get("id") or ""),
        agent_id=agent_id,
    )
    yield sse_line(sequencer.wrap(reply_end))
    _schedule_persist_trace_event(payload.task_id, reply_end)

    final_text = (translator.final_text() or "").strip()
    created: dict[str, str] | None = None
    failure_reason = ""

    if created_skill_name:
        loaded = load_created_skill(agent_id, created_skill_name)
        if loaded is None:
            failure_reason = (
                f"技能 `{created_skill_name}` 已写入，但内容未通过质量检查（过于模板化或为空）。"
            )
        else:
            try:
                created = await asyncio.to_thread(
                    sync_created_skill_to_pool_and_store,
                    loaded,
                    agent_id=agent_id,
                )
            except SkillsError as exc:
                failure_reason = str(exc)
    elif materialize_attempted:
        failure_reason = "materialize_skill 未成功完成，请根据上方工具输出调整后重试。"
    else:
        failure_reason = "未完成 skill 编排：智能体未调用 materialize_skill 创建技能。"

    if created is not None:
        skill_name = created["name"]
        sync_task_workspace(
            payload.task_id,
            agent_id,
            Path(_agent_workspace_dir(agent_id)),
            employee_name=payload.employee_name,
        )
        mount_agent_ids: list[str] = []
        for candidate in (agent_id, resolve_active_agentdesk_agent_id()):
            if candidate and candidate not in mount_agent_ids:
                mount_agent_ids.append(candidate)
        mounted = False
        for mount_agent_id in mount_agent_ids:
            try:
                await asyncio.to_thread(
                    ensure_skill_mounted,
                    skill_name=skill_name,
                    agent_id=mount_agent_id,
                    overwrite=False,
                )
                schedule_agent_reload(request, mount_agent_id)
                mounted = True
            except HTTPException as exc:
                logger.warning(
                    "Skill '%s' created but mount failed on agent '%s': %s",
                    skill_name,
                    mount_agent_id,
                    exc.detail,
                )
        if mounted:
            task = agentdesk_store.get_by_key("tasks", "id", payload.task_id) or agentdesk_store.ensure_task(
                payload.task_id,
            )
            selected = list(dict.fromkeys([*(task.get("skill_names") or []), skill_name]))
            task["skill_names"] = selected
            agentdesk_store.upsert_by_key("tasks", "id", payload.task_id, task)

        if not final_text:
            reply_lines = [
                f"已根据你的描述创建技能「{skill_name}」。",
                "",
                f"**用途：** {created['purpose']}",
                "",
                "可在左侧「技能」页查看；对话中也可从技能选择器挂载使用。",
            ]
            if mounted:
                reply_lines.extend(["", "已自动挂载到当前智能体。"])
            final_text = "\n".join(reply_lines)

        wizard = build_skill_done_wizard(created)
        persist_task_wizard(payload.task_id, wizard)
        skill_md_path = f"skills/{skill_name}/SKILL.md"
        skill_artifact = {
            "type": "artifact",
            "kind": "file",
            "role": "product",
            "path": skill_md_path,
            "name": f"{skill_name}/SKILL.md",
            "summary": skill_md_path,
            "op": "write",
            "tool": "materialize_skill",
        }
        await task_store.append_assistant_artifacts(
            payload.task_id,
            [skill_artifact],
            message_id=str(assistant_draft.get("id") or "") or None,
        )
        yield sse_line(sequencer.wrap(skill_artifact))
        yield sse_line(sequencer.wrap({"type": "wizard_update", "wizard": wizard}))
    else:
        wizard = build_skill_failed_wizard(reason=failure_reason)
        persist_task_wizard(payload.task_id, wizard)
        yield sse_line(sequencer.wrap({"type": "wizard_update", "wizard": wizard}))
        if final_text:
            final_text = f"{final_text.rstrip()}\n\n（提示：{failure_reason}）"
        else:
            final_text = failure_reason
            yield sse_line(
                sequencer.wrap(
                    {
                        "type": "error",
                        "content": failure_reason,
                        "fatal": False,
                    },
                ),
            )

    await task_store.finalize_assistant_message(
        payload.task_id,
        content=final_text or None,
    )
    await asyncio.to_thread(_commit_task_run_status, payload.task_id, _RUN_STATUS_IDLE)
    yield sse_line(
        sequencer.wrap(
            {
                "type": "done",
                "messages": await task_store.get_messages(payload.task_id),
            },
        ),
    )


async def _stream_chat(payload: ChatRequest, request: Request) -> AsyncGenerator[str, None]:
    try:
        await asyncio.gather(
            task_store.ensure_task(payload.task_id),
            asyncio.to_thread(coerce_team_routing_from_store, payload),
        )
    except HTTPException as exc:
        sequencer = StreamEventSequencer(task_id=payload.task_id)
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
    _schedule_task_chat_target(payload)

    user_text = (payload.message or "").strip()
    if (
        payload.wizard_action
        and payload.intent == "skill_create"
        and not is_skill_find_message(user_text)
        and is_skill_create_message(user_text)
    ):
        async for line in _stream_skill_wizard(payload, request):
            yield line
        return

    sequencer = StreamEventSequencer(task_id=payload.task_id)
    agent_id = lookup_agent_id(payload.employee_name)
    sender = display_sender(payload.employee_name, agent_id)

    if payload.mode == "team":
        from .team_chat import stream_team_chat

        async for line in stream_team_chat(payload, request):
            yield line
        return

    if payload.chat_mode == "plan" or (
        payload.wizard_action and payload.intent != "skill_create"
    ):
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": "计划/技能向导模式 Phase 1 暂未实现，请使用普通对话。",
                    "fatal": True,
                },
            ),
        )
        return

    if payload.reconnect:
        async for line in _stream_chat_reconnect(
            payload=payload,
            request=request,
            agent_id=agent_id,
            sender=sender,
            sequencer=sequencer,
        ):
            yield line
        return

    user_text = (payload.message or "").strip()
    if user_text and not payload.plan_auto_continue:
        await task_store.append_user_message(payload.task_id, user_text)

    stream_turn_started = False
    stream_message_id: str | None = None
    prep_task: asyncio.Task[_SingleChatRuntime] | None = None
    skills_task: asyncio.Task[list[str]] | None = None
    skill_names = _dedupe_skill_names(payload.skill_names)
    if user_text or payload.plan_auto_continue:
        assistant_draft = await task_store.begin_assistant_message(
            payload.task_id,
            sender=sender,
        )
        stream_message_id = str(assistant_draft.get("id") or "") or None
        prep_task = asyncio.create_task(
            _prepare_single_chat_runtime_fast(payload, request, agent_id),
        )
        if skill_names:
            skills_task = asyncio.create_task(
                _ensure_payload_skills_mounted(
                    payload,
                    agent_id=agent_id,
                    request=request,
                ),
            )
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "stream_start",
                    "sender": sender,
                    "message_id": assistant_draft.get("id"),
                },
            ),
        )
        _spawn_background(
            asyncio.to_thread(
                _commit_task_run_status, payload.task_id, _RUN_STATUS_RUNNING,
            ),
        )
        stream_turn_started = True

    mounted_skills: list[str] = []
    workspace = None
    console_channel = None
    model_error: str | None = None

    if prep_task is not None:
        try:
            runtime = await prep_task
        except HTTPException as exc:
            err = str(exc.detail)
            await _finalize_failed_turn(
                payload.task_id,
                sender=sender,
                content=err,
                stream_turn_started=stream_turn_started,
            )
            yield sse_line(
                sequencer.wrap(
                    {
                        "type": "error",
                        "content": err,
                        "fatal": True,
                    },
                ),
            )
            yield sse_line(
                sequencer.wrap(
                    {
                        "type": "done",
                        "messages": await task_store.get_messages(payload.task_id),
                    },
                ),
            )
            return

        mounted_skills = runtime.mounted_skills
        model_error = runtime.model_error
        workspace = runtime.workspace
        console_channel = runtime.console_channel
        agent_id = str(getattr(request.state, "agent_id", None) or agent_id)

        if skills_task is not None:
            try:
                mounted_skills = await skills_task
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Skill mount failed for task %s: %s",
                    payload.task_id,
                    exc,
                    exc_info=True,
                )
                mounted_skills = []
            if mounted_skills and await _reload_agent_after_skill_mount(request, agent_id):
                workspace = await get_agent_for_request(request, agent_id=agent_id)
                console_channel = await workspace.channel_manager.get_channel(
                    _AGENTDESK_CHANNEL,
                )

        if model_error:
            await _finalize_failed_turn(
                payload.task_id,
                sender=sender,
                content=model_error,
                stream_turn_started=stream_turn_started,
            )
            yield sse_line(
                sequencer.wrap(
                    {
                        "type": "error",
                        "content": model_error,
                        "fatal": True,
                    },
                ),
            )
            if stream_turn_started:
                yield sse_line(
                    sequencer.wrap(
                        {
                            "type": "done",
                            "messages": await task_store.get_messages(payload.task_id),
                        },
                    ),
                )
            return

        if console_channel is None:
            err = "Console 通道未就绪"
            await _finalize_failed_turn(
                payload.task_id,
                sender=sender,
                content=err,
                stream_turn_started=stream_turn_started,
            )
            yield sse_line(
                sequencer.wrap(
                    {
                        "type": "error",
                        "content": err,
                        "fatal": True,
                    },
                ),
            )
            if stream_turn_started:
                yield sse_line(
                    sequencer.wrap(
                        {
                            "type": "done",
                            "messages": await task_store.get_messages(payload.task_id),
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

    tracker = workspace.task_tracker if workspace is not None else None

    display_text, agent_message = resolve_chat_user_messages(
        Path(workspace.workspace_dir) if workspace is not None else Path("."),
        user_text,
        mounted_skills,
    )

    if not agent_message and not payload.plan_auto_continue:
        err = "消息不能为空"
        await _finalize_failed_turn(
            payload.task_id,
            sender=sender,
            content=err,
            stream_turn_started=stream_turn_started,
        )
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "error",
                    "content": err,
                    "fatal": True,
                },
            ),
        )
        if stream_turn_started:
            yield sse_line(
                sequencer.wrap(
                    {
                        "type": "done",
                        "messages": await task_store.get_messages(payload.task_id),
                    },
                ),
            )
        return

    native_payload = build_agentdesk_native_payload(
        task_id=payload.task_id,
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

    if not stream_turn_started:
        assistant_draft = await task_store.begin_assistant_message(
            payload.task_id,
            sender=sender,
        )
        stream_message_id = str(assistant_draft.get("id") or "") or None
        _spawn_background(
            asyncio.to_thread(
                _commit_task_run_status, payload.task_id, _RUN_STATUS_RUNNING,
            ),
        )
        yield sse_line(
            sequencer.wrap(
                {
                    "type": "stream_start",
                    "sender": sender,
                    "message_id": assistant_draft.get("id"),
                },
            ),
        )
    if mounted_skills:
        skill_trace = _tag_turn_event(
            {
                "type": "skills_active",
                "label": f"已加载技能: {', '.join(mounted_skills)}",
                "skills": mounted_skills,
            },
            sender=sender,
            message_id=stream_message_id,
            agent_id=agent_id,
        )
        _schedule_persist_trace_event(payload.task_id, skill_trace)
        yield sse_line(sequencer.wrap(skill_trace))

    queue, is_new = await tracker.attach_or_start(
        chat.id,
        native_payload,
        console_channel.stream_one,
    )
    if is_new:
        _schedule_run_finalize_watch(
            task_id=payload.task_id,
            run_key=chat.id,
            tracker=tracker,
        )
    stream_it = tracker.stream_from_queue(queue, chat.id)

    try:
        async for line in _emit_translated_events(
            payload=payload,
            sender=sender,
            sequencer=sequencer,
            stream_it=stream_it,
            tracker=tracker,
            run_key=chat.id,
            stream_message_id=stream_message_id,
            agent_id=agent_id,
        ):
            yield line
    except asyncio.CancelledError:
        # Client disconnected (e.g. browser refresh). Background finalize watch
        # keeps runStatus accurate until the tracker run actually ends.
        raise
    except Exception as exc:
        logger.exception("AgentDesk chat stream error task_id=%s", payload.task_id)
        still_running = await tracker.get_status(chat.id) == _RUN_STATUS_RUNNING
        if not still_running:
            await task_store.finalize_assistant_message(payload.task_id)
            _commit_task_run_status(payload.task_id, _RUN_STATUS_IDLE)
        user_message = format_agentdesk_persistence_error(exc) or (
            "对话处理失败，请稍后重试。"
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
        if not still_running:
            yield sse_line(
                sequencer.wrap(
                    {
                        "type": "done",
                        "messages": await task_store.get_messages(payload.task_id),
                    },
                ),
            )


@router.post("/stream")
async def post_chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    """Stream assistant reply in AgentDesk SSE format."""
    # Each AgentDesk conversation maps 1:1 to a QwenPaw session via
    # ``meta.session_id = task_id``. An empty task_id would collapse every
    # conversation onto the shared ``console:agentdesk`` session and cause
    # cross-talk between chats, so reject it up front.
    if not str(payload.task_id or "").strip():
        raise HTTPException(
            status_code=400,
            detail="task_id is required for AgentDesk chat streaming.",
        )

    stream_headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    # Converged streaming path: both single and team modes stream directly from
    # ``_stream_chat``. Team reconnect now reuses the leader/member native
    # sessions instead of an extra outer tracker buffer keyed by task_id.
    return StreamingResponse(
        _stream_chat(payload, request),
        media_type="text/event-stream",
        headers=stream_headers,
    )


@router.post("")
async def post_chat(payload: ChatRequest, request: Request) -> dict:
    """Non-streaming chat — not used by AgentDesk UI in Phase 1."""
    _ = payload, request
    raise HTTPException(
        status_code=501,
        detail="Use POST /api/chat/stream for AgentDesk chat",
    )


@router.post("/approve")
async def post_chat_approve(body: dict, request: Request) -> dict:
    """AgentDesk approval hook bridged to QwenPaw tool-guard approvals."""
    _ = request
    task_id = str(body.get("task_id") or "")
    approved = bool(body.get("approved", True))
    request_id = str(body.get("request_id") or "")
    session_id = str(body.get("session_id") or task_id)
    svc = get_approval_service()
    if not request_id:
        pending = await svc.get_pending_by_session(session_id)
        if pending is None and hasattr(svc, "get_pending_by_root_session"):
            pending_list = await svc.get_pending_by_root_session(session_id)
            pending = pending_list[0] if pending_list else None
        if pending is not None:
            request_id = pending.request_id
        else:
            pending = None
    else:
        pending = await svc.get_request(request_id)

    if not request_id:
        return {
            "task_id": task_id,
            "approved": approved,
            "status": "no_pending_approval",
        }

    if pending is None:
        return {
            "task_id": task_id,
            "approved": approved,
            "request_id": request_id,
            "status": "no_pending_approval",
        }
    if pending.root_session_id != session_id:
        raise HTTPException(
            status_code=403,
            detail="Root session mismatch: cannot approve other session trees",
        )

    decision = ApprovalDecision.APPROVED if approved else ApprovalDecision.DENIED
    resolved = await svc.resolve_request(request_id, decision)
    return {
        "task_id": task_id,
        "approved": approved,
        "request_id": request_id,
        "tool_name": resolved.tool_name,
        "status": "approved" if approved else "denied",
    }
