# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from qwenpaw.agentdesk import session_routing
from qwenpaw.agentdesk.models import ChatRequest


def _patch_task(monkeypatch: pytest.MonkeyPatch, task: dict) -> None:
    monkeypatch.setattr(
        session_routing,
        "agentdesk_store",
        SimpleNamespace(get_by_key=lambda *_args: task),
    )


def test_team_session_rejects_switching_to_single_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_task(monkeypatch, {"id": "s1", "mode": "team", "team_id": "team-a"})
    payload = ChatRequest(task_id="s1", mode="single", employee_name="Alice")

    with pytest.raises(HTTPException) as exc:
        session_routing.coerce_team_routing_from_store(payload)

    assert exc.value.status_code == 409
    assert "新开一个 session" in str(exc.value.detail)


def test_team_session_rejects_switching_team(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_task(
        monkeypatch,
        {"id": "s1", "mode": "team", "team_id": "team-a", "team_name": "A Team"},
    )
    payload = ChatRequest(
        task_id="s1",
        mode="team",
        team_id="team-b",
        team_name="B Team",
    )

    with pytest.raises(HTTPException) as exc:
        session_routing.coerce_team_routing_from_store(payload)

    assert exc.value.status_code == 409
    assert "切换团队" in str(exc.value.detail)


def test_team_session_fills_original_team_when_payload_omits_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_task(
        monkeypatch,
        {"id": "s1", "mode": "team", "team_id": "team-a", "team_name": "A Team"},
    )
    payload = ChatRequest(task_id="s1", mode="team")

    session_routing.coerce_team_routing_from_store(payload)

    assert payload.mode == "team"
    assert payload.team_id == "team-a"
    assert payload.team_name == "A Team"


def test_single_session_rejects_switching_to_team(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_task(
        monkeypatch,
        {
            "id": "s1",
            "mode": "single",
            "employee_name": "Alice",
            "messages": [{"role": "assistant", "content": "hello"}],
        },
    )
    payload = ChatRequest(task_id="s1", mode="team", team_id="team-a")

    with pytest.raises(HTTPException) as exc:
        session_routing.coerce_team_routing_from_store(payload)

    assert exc.value.status_code == 409
    assert "发起群聊" in str(exc.value.detail)


def test_single_session_allows_switching_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_task(
        monkeypatch,
        {
            "id": "s1",
            "mode": "single",
            "employee_name": "Alice",
            "messages": [{"role": "assistant", "content": "hello"}],
        },
    )
    payload = ChatRequest(task_id="s1", mode="single", employee_name="Bob")

    session_routing.coerce_team_routing_from_store(payload)

    assert payload.mode == "single"
    assert payload.employee_name == "Bob"


def test_apply_chat_routing_to_task_records_team_target() -> None:
    payload = ChatRequest(
        task_id="s1",
        mode="team",
        team_id="team-a",
        team_name="A Team",
        employee_name="Alice",
    )

    updated = session_routing.apply_chat_routing_to_task({"id": "s1"}, payload)

    assert updated["mode"] == "team"
    assert updated["team_id"] == "team-a"
    assert updated["team_name"] == "A Team"
    assert "employee_name" not in updated


def test_apply_chat_routing_to_task_preserves_established_team() -> None:
    payload = ChatRequest(task_id="s1", mode="single", employee_name="Bob")

    updated = session_routing.apply_chat_routing_to_task(
        {"id": "s1", "mode": "team", "team_id": "team-a", "team_name": "A Team"},
        payload,
    )

    assert updated["mode"] == "team"
    assert updated["team_id"] == "team-a"
    assert updated["team_name"] == "A Team"
    assert "employee_name" not in updated


def test_apply_chat_routing_to_task_allows_single_agent_switch() -> None:
    payload = ChatRequest(task_id="s1", mode="single", employee_name="Bob")

    updated = session_routing.apply_chat_routing_to_task(
        {"id": "s1", "mode": "single", "employee_name": "Alice"},
        payload,
    )

    assert updated["mode"] == "single"
    assert updated["employee_name"] == "Bob"
    assert "team_id" not in updated
    assert "team_name" not in updated
