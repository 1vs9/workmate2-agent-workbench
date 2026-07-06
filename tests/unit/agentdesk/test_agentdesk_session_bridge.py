# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from qwenpaw.app.runner.session import SafeJSONSession
from qwenpaw.agentdesk.session_bridge import (
    bind_agentdesk_session_bridge,
    build_agentdesk_session,
    agentdesk_session_dir,
)


class _FakeAgentState:
    def __init__(self, payload: dict | None = None) -> None:
        self.loaded: dict | None = None
        self.payload = payload or {"state": {"context": [{"role": "user"}]}}

    def state_dict(self) -> dict:
        return self.payload

    def load_state_dict(self, state: dict) -> None:
        self.loaded = state


def test_agentdesk_session_dir_uses_shared_agentdesk_scope(tmp_path) -> None:
    assert agentdesk_session_dir(working_dir=tmp_path) == tmp_path / "agentdesk" / "sessions"
    session = build_agentdesk_session(working_dir=tmp_path)
    assert session.save_dir == str(tmp_path / "agentdesk" / "sessions")


async def test_bind_agentdesk_session_bridge_shares_history_across_workspaces(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "qwenpaw.agentdesk.session_bridge.WORKING_DIR",
        tmp_path,
    )
    workspace_a = SimpleNamespace(
        runner=SimpleNamespace(session=SafeJSONSession(str(tmp_path / "a" / "sessions"))),
    )
    workspace_b = SimpleNamespace(
        runner=SimpleNamespace(session=SafeJSONSession(str(tmp_path / "b" / "sessions"))),
    )
    session_a = bind_agentdesk_session_bridge(workspace_a)
    session_b = bind_agentdesk_session_bridge(workspace_b)
    saved_agent = _FakeAgentState()
    loaded_agent = _FakeAgentState()

    assert session_a is not None
    assert session_b is not None
    assert session_a.save_dir == session_b.save_dir

    await session_a.save_session_state(
        session_id="session-1",
        user_id="agentdesk",
        channel="console",
        agent=saved_agent,
    )
    await session_b.load_session_state(
        session_id="session-1",
        user_id="agentdesk",
        channel="console",
        agent=loaded_agent,
    )

    assert loaded_agent.loaded == saved_agent.payload


def test_bind_agentdesk_session_bridge_is_idempotent(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "qwenpaw.agentdesk.session_bridge.WORKING_DIR",
        tmp_path,
    )
    workspace = SimpleNamespace(
        runner=SimpleNamespace(session=SafeJSONSession(str(tmp_path / "a" / "sessions"))),
    )

    first = bind_agentdesk_session_bridge(workspace)
    second = bind_agentdesk_session_bridge(workspace)

    assert first is second
    assert workspace.runner.session is first
