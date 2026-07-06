# -*- coding: utf-8 -*-
"""Runtime preparation for AgentDesk single-agent chat turns."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from fastapi import Request

from ..app.agent_context import get_agent_for_request
from .agent_reload import reload_agent_after_skill_mount
from .agents import resolve_agent_id
from .chat_skill_mount import dedupe_skill_names, ensure_payload_skills_mounted
from .model_config import ensure_chat_model
from .models import ChatRequest
from .session_bridge import AGENTDESK_SESSION_CHANNEL, bind_agentdesk_session_bridge


@dataclass
class SingleChatRuntime:
    workspace: Any
    mounted_skills: list[str]
    model_error: str | None
    console_channel: Any


async def prepare_single_chat_runtime_fast(
    payload: ChatRequest,
    request: Request,
    agent_id: str,
    *,
    resolve_agent_id_fn: Callable[[str | None], str | None] = resolve_agent_id,
    get_agent_for_request_fn: Callable[..., Awaitable[Any]] = get_agent_for_request,
    ensure_chat_model_fn: Callable[[str], Awaitable[tuple[Any, str | None]]] = ensure_chat_model,
) -> SingleChatRuntime:
    """Fetch workspace + model without blocking on skill disk I/O."""
    resolved_id = await asyncio.to_thread(resolve_agent_id_fn, payload.employee_name)
    agent_id = resolved_id or agent_id
    workspace, (_model_slot, model_error) = await asyncio.gather(
        get_agent_for_request_fn(request, agent_id=agent_id),
        ensure_chat_model_fn(agent_id),
    )
    bind_agentdesk_session_bridge(workspace)
    if not hasattr(request.state, "agent_id") or request.state.agent_id is None:
        request.state.agent_id = agent_id
    console_channel = await workspace.channel_manager.get_channel(AGENTDESK_SESSION_CHANNEL)
    return SingleChatRuntime(
        workspace=workspace,
        mounted_skills=[],
        model_error=model_error,
        console_channel=console_channel,
    )


async def prepare_single_chat_runtime(
    payload: ChatRequest,
    request: Request,
    agent_id: str,
    *,
    resolve_agent_id_fn: Callable[[str | None], str | None] = resolve_agent_id,
    get_agent_for_request_fn: Callable[..., Awaitable[Any]] = get_agent_for_request,
    ensure_chat_model_fn: Callable[[str], Awaitable[tuple[Any, str | None]]] = ensure_chat_model,
    dedupe_skill_names_fn: Callable[[list[str]], list[str]] = dedupe_skill_names,
    ensure_payload_skills_mounted_fn: Callable[..., Awaitable[list[str]]] = ensure_payload_skills_mounted,
    reload_agent_after_skill_mount_fn: Callable[..., Awaitable[bool]] = reload_agent_after_skill_mount,
) -> SingleChatRuntime:
    """Prepare runtime and, when requested, mount selected skills."""
    runtime = await prepare_single_chat_runtime_fast(
        payload,
        request,
        agent_id,
        resolve_agent_id_fn=resolve_agent_id_fn,
        get_agent_for_request_fn=get_agent_for_request_fn,
        ensure_chat_model_fn=ensure_chat_model_fn,
    )
    skill_names = dedupe_skill_names_fn(payload.skill_names)
    if not skill_names:
        return runtime
    mounted_skills = await ensure_payload_skills_mounted_fn(
        payload,
        agent_id=str(getattr(request.state, "agent_id", None) or agent_id),
        request=request,
    )
    agent_id = str(getattr(request.state, "agent_id", None) or agent_id)
    if mounted_skills and await reload_agent_after_skill_mount_fn(request, agent_id):
        runtime.workspace = await get_agent_for_request_fn(request, agent_id=agent_id)
        runtime.console_channel = await runtime.workspace.channel_manager.get_channel(
            AGENTDESK_SESSION_CHANNEL,
        )
    runtime.mounted_skills = mounted_skills
    return runtime
