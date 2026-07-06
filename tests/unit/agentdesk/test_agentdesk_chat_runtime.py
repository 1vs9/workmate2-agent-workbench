# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from qwenpaw.agentdesk import chat_runtime
from qwenpaw.agentdesk.models import ChatRequest


class _Workspace:
    def __init__(self, channel: object) -> None:
        self.channel_manager = SimpleNamespace(
            get_channel=AsyncMock(return_value=channel),
        )


async def test_prepare_single_chat_runtime_fast_resolves_agent_and_model(
    monkeypatch,
) -> None:
    channel = object()
    workspace = _Workspace(channel)
    bound: list[object] = []
    monkeypatch.setattr(
        chat_runtime,
        "bind_agentdesk_session_bridge",
        lambda candidate: bound.append(candidate),
    )

    async def get_agent(_request, *, agent_id: str):
        assert agent_id == "agent-1"
        return workspace

    async def ensure_model(agent_id: str):
        assert agent_id == "agent-1"
        return object(), None

    request = SimpleNamespace(state=SimpleNamespace(agent_id=None))
    payload = ChatRequest(task_id="task-1", employee_name="Analyst")

    runtime = await chat_runtime.prepare_single_chat_runtime_fast(
        payload,
        request,
        "default",
        resolve_agent_id_fn=lambda _name: "agent-1",
        get_agent_for_request_fn=get_agent,
        ensure_chat_model_fn=ensure_model,
    )

    assert runtime.workspace is workspace
    assert runtime.console_channel is channel
    assert runtime.model_error is None
    assert request.state.agent_id == "agent-1"
    assert bound == [workspace]


async def test_prepare_single_chat_runtime_mounts_and_reloads_workspace(
    monkeypatch,
) -> None:
    first_channel = object()
    second_channel = object()
    workspaces = [_Workspace(first_channel), _Workspace(second_channel)]
    monkeypatch.setattr(chat_runtime, "bind_agentdesk_session_bridge", lambda _w: None)

    async def get_agent(_request, *, agent_id: str):
        assert agent_id == "agent-1"
        return workspaces.pop(0)

    async def ensure_model(_agent_id: str):
        return object(), None

    async def mount(_payload, *, agent_id: str, request):
        assert agent_id == "agent-1"
        assert request is not None
        return ["search"]

    async def reload_agent(_request, agent_id: str):
        assert agent_id == "agent-1"
        return True

    request = SimpleNamespace(state=SimpleNamespace(agent_id=None))
    payload = ChatRequest(
        task_id="task-1",
        employee_name="Analyst",
        skill_names=["search"],
    )

    runtime = await chat_runtime.prepare_single_chat_runtime(
        payload,
        request,
        "default",
        resolve_agent_id_fn=lambda _name: "agent-1",
        get_agent_for_request_fn=get_agent,
        ensure_chat_model_fn=ensure_model,
        dedupe_skill_names_fn=lambda names: names,
        ensure_payload_skills_mounted_fn=mount,
        reload_agent_after_skill_mount_fn=reload_agent,
    )

    assert runtime.mounted_skills == ["search"]
    assert runtime.console_channel is second_channel
