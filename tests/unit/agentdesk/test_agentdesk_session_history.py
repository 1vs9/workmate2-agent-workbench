# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from qwenpaw.agentdesk.session_bridge import build_agentdesk_session
from qwenpaw.agentdesk.session_bridge import (
    AGENTDESK_SESSION_CHANNEL,
    AGENTDESK_SESSION_USER_ID,
)
from qwenpaw.agentdesk.session_history import (
    read_agentdesk_session_messages,
)
from qwenpaw.agentdesk.store import AgentDeskStore
from qwenpaw.agentdesk.task_store import TaskStore


class _FakeAgentState:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def state_dict(self) -> dict[str, Any]:
        return self.payload


def test_native_payload_uses_same_session_key_as_history_reader() -> None:
    from qwenpaw.agentdesk.native_payload import build_agentdesk_native_payload

    payload = build_agentdesk_native_payload(
        task_id="task-1",
        message="hello",
        agent_id="agent-a",
    )

    assert payload["channel_id"] == AGENTDESK_SESSION_CHANNEL
    assert payload["sender_id"] == AGENTDESK_SESSION_USER_ID
    assert payload["meta"]["session_id"] == "task-1"
    assert payload["meta"]["user_id"] == AGENTDESK_SESSION_USER_ID


async def test_read_agentdesk_session_messages_projects_qwenpaw_history(
    tmp_path,
) -> None:
    session = build_agentdesk_session(working_dir=tmp_path)
    agent = _FakeAgentState(
        {
            "state": {
                "context": [
                    {
                        "id": "u1",
                        "role": "user",
                        "name": "user",
                        "content": (
                            "Use mounted skill.\n\n"
                            "the user's task: hello from the user"
                        ),
                    },
                    {
                        "id": "a1",
                        "role": "assistant",
                        "name": "agentdesk",
                        "content": [{"type": "text", "text": "hello back"}],
                        "timestamp": "2026-06-30T09:00:00",
                    },
                ],
            },
        },
    )

    await session.save_session_state(
        session_id="task-1",
        user_id=AGENTDESK_SESSION_USER_ID,
        channel=AGENTDESK_SESSION_CHANNEL,
        agent=agent,
    )

    messages = await read_agentdesk_session_messages("task-1", working_dir=tmp_path)

    assert messages == [
        {
            "id": "u1",
            "role": "user",
            "content": "hello from the user",
            "streaming": False,
            "artifacts": [],
            "sender": "user",
        },
        {
            "id": "a1",
            "role": "assistant",
            "content": "hello back",
            "streaming": False,
            "artifacts": [],
            "updatedAt": "2026-06-30T09:00:00",
            "sender": "agentdesk",
        },
    ]


async def test_read_agentdesk_session_messages_returns_empty_for_missing_session(
    tmp_path,
) -> None:
    assert await read_agentdesk_session_messages("missing", working_dir=tmp_path) == []


async def test_read_agentdesk_session_messages_supports_legacy_memory_state(
    tmp_path,
) -> None:
    session = build_agentdesk_session(working_dir=tmp_path)
    agent = _FakeAgentState(
        {
            "memory": {
                "content": [
                    [
                        {
                            "id": "legacy-u1",
                            "role": "user",
                            "name": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Use mounted skill.\n\n"
                                        "the user's task: legacy hello"
                                    ),
                                },
                            ],
                        },
                        [],
                    ],
                    [
                        {
                            "id": "legacy-a1",
                            "role": "assistant",
                            "name": "agentdesk",
                            "content": [{"type": "text", "text": "legacy answer"}],
                        },
                        [],
                    ],
                ],
            },
        },
    )

    await session.save_session_state(
        session_id="legacy-task",
        user_id=AGENTDESK_SESSION_USER_ID,
        channel=AGENTDESK_SESSION_CHANNEL,
        agent=agent,
    )

    messages = await read_agentdesk_session_messages(
        "legacy-task",
        working_dir=tmp_path,
    )

    assert [
        (message["id"], message["role"], message["content"], message.get("sender"))
        for message in messages
    ] == [
        ("legacy-u1", "user", "legacy hello", "user"),
        ("legacy-a1", "assistant", "legacy answer", "agentdesk"),
    ]


async def test_task_store_get_messages_falls_back_to_session_history(
    tmp_path,
) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    seen_task_ids: list[str] = []

    async def reader(task_id: str) -> list[dict[str, Any]]:
        seen_task_ids.append(task_id)
        return [
            {
                "id": "history-1",
                "role": "assistant",
                "content": "from qwenpaw session",
                "streaming": False,
            },
        ]

    task_store = TaskStore(store, session_history_reader=reader)
    await task_store.ensure_task("task-1")

    assert await task_store.get_messages("task-1") == [
        {
            "id": "history-1",
            "role": "assistant",
            "content": "from qwenpaw session",
            "streaming": False,
        },
    ]
    assert seen_task_ids == ["task-1"]


async def test_task_store_get_messages_prefers_live_cache(tmp_path) -> None:
    store = AgentDeskStore(tmp_path / "store.json")

    async def reader(_task_id: str) -> list[dict[str, Any]]:
        return [
            {
                "id": "history-1",
                "role": "assistant",
                "content": "from qwenpaw session",
                "streaming": False,
            },
        ]

    task_store = TaskStore(store, session_history_reader=reader)
    await task_store.ensure_task("task-1")
    await task_store.append_user_message("task-1", "live cache wins")

    messages = await task_store.get_messages("task-1")

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "live cache wins"
