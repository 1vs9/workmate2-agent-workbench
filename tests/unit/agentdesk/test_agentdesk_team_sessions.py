# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.agentdesk import team_sessions


def test_team_session_id_sanitizes_suffix() -> None:
    assert team_sessions.team_session_id("task-1", "member:Alice Smith!") == (
        "task-1:team:member:Alice_Smith_"
    )


def test_team_member_session_id_keeps_cjk_names_stable() -> None:
    assert team_sessions.team_member_session_id("task-1", "张三") == (
        "task-1:team:member:张三"
    )


def test_team_session_id_uses_unknown_for_empty_suffix() -> None:
    assert team_sessions.team_session_id("task-1", "") == "task-1:team:unknown"
    assert team_sessions.team_member_session_id("task-1", "") == (
        "task-1:team:member:unknown"
    )


def test_team_session_suffix_is_truncated() -> None:
    suffix = "x" * 80
    assert team_sessions.team_session_id("task-1", suffix) == (
        f"task-1:team:{'x' * 48}"
    )
