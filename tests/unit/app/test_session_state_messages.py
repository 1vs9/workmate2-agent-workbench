# -*- coding: utf-8 -*-
from __future__ import annotations

from agentscope.message import Msg, TextBlock
from agentscope.state import AgentState

from qwenpaw.app.runner.utils import (
    session_state_to_agent_messages,
    session_state_to_messages,
)


def _message_texts(state: dict) -> list[str]:
    out: list[str] = []
    for message in session_state_to_messages(state):
        for item in message.content:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                out.append(text)
    return out


def test_session_state_to_messages_reads_agent_state_context() -> None:
    state = {
        "agent": {
            "state": AgentState(
                context=[
                    Msg(
                        name="user",
                        role="user",
                        content=[TextBlock(text="hello")],
                    ),
                    Msg(
                        name="assistant",
                        role="assistant",
                        content=[TextBlock(text="hi")],
                    ),
                ],
            ).model_dump(),
        },
    }

    messages = session_state_to_messages(state)

    assert [message.role for message in messages] == ["user", "assistant"]
    assert _message_texts(state) == ["hello", "hi"]
    assert messages[0].metadata["original_name"] == "user"
    agent_messages = session_state_to_agent_messages(state)
    assert [message.name for message in agent_messages] == ["user", "assistant"]


def test_session_state_to_messages_reads_legacy_memory() -> None:
    state = {
        "agent": {
            "memory": {
                "content": [
                    [
                        Msg(
                            name="user",
                            role="user",
                            content=[TextBlock(text="legacy hello")],
                        ).model_dump(),
                        [],
                    ],
                ],
            },
        },
    }

    messages = session_state_to_messages(state)

    assert len(messages) == 1
    assert messages[0].role == "user"
    assert _message_texts(state) == ["legacy hello"]
    assert session_state_to_agent_messages(state)[0].name == "user"
