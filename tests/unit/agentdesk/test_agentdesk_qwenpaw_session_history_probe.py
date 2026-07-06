# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from qwenpaw.app.runner.session import SafeJSONSession


class _FakeAgentState:
    def __init__(self) -> None:
        self.loaded: dict[str, Any] | None = None
        self.payload: dict[str, Any] = {"state": {"context": [{"role": "user"}]}}

    def state_dict(self) -> dict[str, Any]:
        return self.payload

    def load_state_dict(self, state: dict[str, Any]) -> None:
        self.loaded = state


async def test_qwenpaw_session_history_is_workspace_scoped_by_default(tmp_path) -> None:
    session_id = "agentdesk-session-1"
    user_id = "agentdesk"
    channel = "console"
    agent_a_session = SafeJSONSession(str(tmp_path / "agent-a" / "sessions"))
    agent_b_session = SafeJSONSession(str(tmp_path / "agent-b" / "sessions"))
    saved_agent = _FakeAgentState()
    loaded_agent = _FakeAgentState()

    await agent_a_session.save_session_state(
        session_id=session_id,
        user_id=user_id,
        channel=channel,
        agent=saved_agent,
    )
    await agent_b_session.load_session_state(
        session_id=session_id,
        user_id=user_id,
        channel=channel,
        agent=loaded_agent,
    )

    assert loaded_agent.loaded is None


async def test_qwenpaw_session_history_can_share_when_session_dir_is_shared(
    tmp_path,
) -> None:
    session_id = "agentdesk-session-1"
    user_id = "agentdesk"
    channel = "console"
    shared_session = SafeJSONSession(str(tmp_path / "shared" / "sessions"))
    saved_agent = _FakeAgentState()
    loaded_agent = _FakeAgentState()

    await shared_session.save_session_state(
        session_id=session_id,
        user_id=user_id,
        channel=channel,
        agent=saved_agent,
    )
    await shared_session.load_session_state(
        session_id=session_id,
        user_id=user_id,
        channel=channel,
        agent=loaded_agent,
    )

    assert loaded_agent.loaded == saved_agent.payload
