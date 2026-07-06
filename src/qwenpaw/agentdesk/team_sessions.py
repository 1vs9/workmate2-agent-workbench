# -*- coding: utf-8 -*-
"""AgentDesk team-mode native session identifiers."""

from __future__ import annotations

import re

_MEMBER_SESSION_SAFE_RE = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9:_路-]+")

TEAM_LEADER_SESSION_SUFFIX = "leader-native"


def team_session_id(task_id: str, suffix: str) -> str:
    # Keep CJK roster names stable; must match agent-management member sessions.
    safe = _MEMBER_SESSION_SAFE_RE.sub("_", str(suffix or "").strip())[:48]
    return f"{task_id}:team:{safe or 'unknown'}"


def team_member_session_suffix(member_name: str) -> str:
    """Stable native-session suffix for one roster member tab."""
    safe = _MEMBER_SESSION_SAFE_RE.sub("_", str(member_name or "").strip())[:48]
    return f"member:{safe or 'unknown'}"


def team_member_session_id(task_id: str, member_name: str) -> str:
    return team_session_id(task_id, team_member_session_suffix(member_name))
