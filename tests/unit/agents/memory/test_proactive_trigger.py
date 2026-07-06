# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from agentscope.message import Msg, TextBlock
from agentscope.state import AgentState

from qwenpaw.agents.memory.proactive.proactive_trigger import (
    is_last_message_proactive,
)


class _FakeChatManager:
    async def list_chats(self) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                session_id="session-1",
                user_id="user-1",
                channel="console",
                updated_at=datetime.now(timezone.utc),
            ),
        ]


class _FakeSession:
    async def get_session_state_dict(
        self,
        session_id: str,
        user_id: str,
        channel: str,
    ) -> dict:
        assert (session_id, user_id, channel) == ("session-1", "user-1", "console")
        return {
            "agent": {
                "state": AgentState(
                    context=[
                        Msg(
                            name="assistant",
                            role="assistant",
                            content=[TextBlock(text="[PROACTIVE] hello")],
                        ),
                    ],
                ).model_dump(),
            },
        }


async def test_is_last_message_proactive_reads_runtime_content() -> None:
    workspace = SimpleNamespace(
        chat_manager=_FakeChatManager(),
        runner=SimpleNamespace(session=_FakeSession()),
    )

    assert await is_last_message_proactive(workspace) is True
