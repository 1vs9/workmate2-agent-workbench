# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.agentdesk import team_records
from qwenpaw.agentdesk.models import ChatRequest
from qwenpaw.agentdesk.store import AgentDeskStore


def test_resolve_team_record_prefers_team_id(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(team_records, "agentdesk_store", store)
    by_id = {"id": "team-1", "name": "Alpha"}
    by_name = {"id": "team-2", "name": "Beta"}
    store.upsert_by_key("teams", "id", "team-1", by_id)
    store.upsert_by_key("teams", "id", "team-2", by_name)

    payload = ChatRequest(task_id="task-1", team_id="team-1", team_name="Beta")

    resolved = team_records.resolve_team_record(payload)

    assert resolved is not None
    assert resolved["id"] == by_id["id"]
    assert resolved["name"] == by_id["name"]


def test_resolve_team_record_falls_back_to_team_name(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(team_records, "agentdesk_store", store)
    team = {"id": "team-1", "name": "Alpha"}
    store.upsert_by_key("teams", "id", "team-1", team)

    payload = ChatRequest(task_id="task-1", team_name="Alpha")

    resolved = team_records.resolve_team_record(payload)

    assert resolved is not None
    assert resolved["id"] == team["id"]
    assert resolved["name"] == team["name"]


def test_resolve_team_record_returns_none_for_missing_team(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(team_records, "agentdesk_store", store)

    payload = ChatRequest(task_id="task-1", team_id="missing", team_name="Missing")

    assert team_records.resolve_team_record(payload) is None
