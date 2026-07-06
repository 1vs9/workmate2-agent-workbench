# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.agentdesk.message_projection import (
    assistant_messages_by_sender,
    message_for_client,
    messages_for_client,
    streaming_member_assistant_messages,
)


def test_message_for_client_projects_user_display_without_mutating_source() -> None:
    stored = {
        "role": "user",
        "content": "Use skill context. the user's task: hello\n\nTool context follows",
        "artifacts": [{"path": "a.txt"}],
    }

    projected = message_for_client(stored)

    assert projected["content"] == "hello"
    assert stored["content"] == (
        "Use skill context. the user's task: hello\n\nTool context follows"
    )
    assert projected is not stored
    assert projected["artifacts"] is not stored["artifacts"]


def test_messages_for_client_preserves_assistant_content() -> None:
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello", "sender": "AgentDesk"},
        "invalid",
    ]

    assert messages_for_client(messages) == messages[:2]


def test_assistant_messages_by_sender_projects_matching_sender_only() -> None:
    messages = [
        {"role": "user", "content": "hi", "sender": "Alice"},
        {"role": "assistant", "content": "one", "sender": "Alice"},
        {"role": "assistant", "content": "two", "sender": "Bob"},
        {"role": "assistant", "content": "three", "sender": "alice"},
    ]

    projected = assistant_messages_by_sender(messages, "Alice")

    assert [msg["content"] for msg in projected] == ["one", "three"]


def test_streaming_member_assistant_messages_filters_leader_bubbles() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "leader exact",
            "sender": "Team Leader",
            "streaming": True,
        },
        {
            "role": "assistant",
            "content": "hidden leader",
            "sender": "Research Team\u00b7leader",
            "streaming": True,
        },
        {
            "role": "assistant",
            "content": "member",
            "sender": "Alice",
            "streaming": True,
        },
        {
            "role": "assistant",
            "content": "done",
            "sender": "Bob",
            "streaming": False,
        },
    ]

    projected = streaming_member_assistant_messages(
        messages,
        leader_sender="Team Leader",
    )

    assert [msg["content"] for msg in projected] == ["member"]
