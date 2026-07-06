# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from qwenpaw.agentdesk import team_worker_messages
from qwenpaw.agentdesk.team_worker_messages import reusable_member_message_id


class _FakeTaskStore:
    def __init__(self) -> None:
        self.begin_calls: list[dict[str, object]] = []
        self.messages: list[dict[str, object]] = []

    async def begin_assistant_message(
        self,
        task_id: str,
        *,
        sender: str,
        set_streaming: bool,
        session_id: str,
    ) -> dict[str, object]:
        self.begin_calls.append(
            {
                "task_id": task_id,
                "sender": sender,
                "set_streaming": set_streaming,
                "session_id": session_id,
            },
        )
        return {"id": "msg-1"}

    async def get_assistant_messages_by_sender(
        self,
        task_id: str,
        member_name: str,
    ) -> list[dict[str, object]]:
        return self.messages


def test_reusable_member_message_id_prefers_newest_streaming_message() -> None:
    assert reusable_member_message_id(
        [
            {"id": "old-streaming", "streaming": True, "content": "x"},
            {"id": "new-empty", "streaming": False, "content": ""},
            {"id": "new-streaming", "streaming": True, "content": "x"},
        ],
    ) == "new-streaming"


def test_reusable_member_message_id_uses_newest_empty_message() -> None:
    assert reusable_member_message_id(
        [
            {"id": "with-content", "content": "done"},
            {"id": "empty", "content": " "},
        ],
    ) == "empty"


def test_reusable_member_message_id_returns_none_without_reusable_message() -> None:
    assert reusable_member_message_id(
        [
            {"id": "", "streaming": True},
            {"id": "done", "content": "already final"},
        ],
    ) is None


@pytest.mark.asyncio
async def test_begin_worker_assistant_message_uses_member_session(monkeypatch) -> None:
    fake_store = _FakeTaskStore()
    monkeypatch.setattr(team_worker_messages, "task_store", fake_store)

    created = await team_worker_messages.begin_worker_assistant_message(
        "task-1",
        "Writer",
    )

    assert created == {"id": "msg-1"}
    assert fake_store.begin_calls == [
        {
            "task_id": "task-1",
            "sender": "Writer",
            "set_streaming": False,
            "session_id": "task-1:team:member:Writer",
        },
    ]


@pytest.mark.asyncio
async def test_resolve_member_watch_message_id_uses_task_store(monkeypatch) -> None:
    fake_store = _FakeTaskStore()
    fake_store.messages = [{"id": "msg-1", "streaming": True}]
    monkeypatch.setattr(team_worker_messages, "task_store", fake_store)

    assert await team_worker_messages.resolve_member_watch_message_id(
        "task-1",
        "Writer",
    ) == "msg-1"
