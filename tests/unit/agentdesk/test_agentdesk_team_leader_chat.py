# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

import pytest

from qwenpaw.agentdesk import team_leader_chat


class _FakeChannel:
    def __init__(self) -> None:
        self.resolved: list[tuple[str, dict[str, object]]] = []

    def resolve_session_id(self, *, sender_id: str, channel_meta: dict[str, object]) -> str:
        self.resolved.append((sender_id, channel_meta))
        return "resolved-session"


class _FakeChannelManager:
    def __init__(self, channel) -> None:
        self.channel = channel
        self.requested: list[str] = []

    async def get_channel(self, name: str):
        self.requested.append(name)
        return self.channel


class _FakeChatManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str]] = []

    async def get_or_create_chat(
        self,
        session_id: str,
        sender_id: str,
        channel_id: str,
        *,
        name: str,
    ) -> SimpleNamespace:
        self.calls.append((session_id, sender_id, channel_id, name))
        return SimpleNamespace(id="chat-1")


def _request() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace())


@pytest.mark.asyncio
async def test_resolve_team_leader_chat_creates_native_leader_chat(monkeypatch) -> None:
    channel = _FakeChannel()
    workspace = SimpleNamespace(
        channel_manager=_FakeChannelManager(channel),
        chat_manager=_FakeChatManager(),
    )

    async def _get_agent_for_request(request, *, agent_id: str):
        assert agent_id == "leader-agent"
        return workspace

    monkeypatch.setattr(team_leader_chat, "get_agent_for_request", _get_agent_for_request)
    request = _request()

    resolved = await team_leader_chat.resolve_team_leader_chat(
        task_id="task-1",
        request=request,
        leader_agent_id="leader-agent",
    )

    assert resolved == (workspace, "chat-1")
    assert request.state.agent_id == "leader-agent"
    assert workspace.channel_manager.requested == ["console"]
    assert channel.resolved[0][1]["session_id"] == "task-1:team:leader-native"
    assert workspace.chat_manager.calls[0][0] == "resolved-session"
    assert workspace.chat_manager.calls[0][3] == "Media Message"


@pytest.mark.asyncio
async def test_resolve_team_leader_chat_returns_none_without_console_channel(
    monkeypatch,
) -> None:
    workspace = SimpleNamespace(
        channel_manager=_FakeChannelManager(None),
        chat_manager=_FakeChatManager(),
    )

    async def _get_agent_for_request(request, *, agent_id: str):
        return workspace

    monkeypatch.setattr(team_leader_chat, "get_agent_for_request", _get_agent_for_request)

    resolved = await team_leader_chat.resolve_team_leader_chat(
        task_id="task-1",
        request=_request(),
        leader_agent_id="leader-agent",
    )

    assert resolved is None
    assert workspace.chat_manager.calls == []
