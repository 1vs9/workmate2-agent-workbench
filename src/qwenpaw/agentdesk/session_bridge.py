# -*- coding: utf-8 -*-
"""Thin AgentDesk session-history bridge.

QwenPaw's default runner session directory is scoped to each agent workspace.
AgentDesk single-chat UX wants one logical session to survive switching agents,
so AgentDesk provides an explicit shared session directory while still using
QwenPaw's SafeJSONSession format and runtime load/save hooks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..app.runner.session import SafeJSONSession
from ..constant import WORKING_DIR

_BRIDGE_MARKER = "_agentdesk_session_bridge_bound"
AGENTDESK_SESSION_USER_ID = "agentdesk"
AGENTDESK_SESSION_CHANNEL = "console"


def agentdesk_session_dir(*, working_dir: Path | None = None) -> Path:
    base = working_dir or WORKING_DIR
    return base / "agentdesk" / "sessions"


def build_agentdesk_session(*, working_dir: Path | None = None) -> SafeJSONSession:
    return SafeJSONSession(save_dir=str(agentdesk_session_dir(working_dir=working_dir)))


def bind_agentdesk_session_bridge(workspace: Any) -> SafeJSONSession | None:
    """Bind a workspace runner to AgentDesk's shared session store.

    This intentionally does not change QwenPaw's session schema. It only changes
    the session directory used by AgentDesk chat runs, keeping the bridge thin and
    easy to remove once upstream offers a native shared-session policy.
    """

    runner = getattr(workspace, "runner", None)
    if runner is None:
        return None
    existing = getattr(runner, "session", None)
    if getattr(existing, _BRIDGE_MARKER, False):
        return existing
    session = build_agentdesk_session()
    setattr(session, _BRIDGE_MARKER, True)
    runner.session = session
    return session
