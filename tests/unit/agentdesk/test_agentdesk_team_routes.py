# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from qwenpaw.agentdesk import builtin_agents, team_leader_agents, team_routes
from qwenpaw.agentdesk.store import AgentDeskStore


def test_create_team_payload_provisions_leader_and_persists(monkeypatch, tmp_path) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(team_routes, "store", store)
    monkeypatch.setattr(
        team_routes,
        "attach_team_leader",
        lambda payload: {
            **payload,
            "leader": "Research leader",
            "leader_agent_id": "leader-agent",
        },
    )
    monkeypatch.setattr(
        team_routes,
        "apply_avatar_on_write",
        lambda payload, *, role: {**payload, "avatar": f"{role}.svg"},
    )

    result = team_routes.create_team_payload(
        {"id": "team-1", "name": "Research", "members": ["Alice", "Bob"]},
    )

    assert result["id"] == "team-1"
    assert result["leader"] == "Research leader"
    assert result["leader_agent_id"] == "leader-agent"
    assert result["avatar"] == "team.svg"
    assert result["members"] == ["Alice", "Bob"]
    assert store.get_by_key("teams", "id", "team-1")["name"] == "Research"


def test_create_team_payload_without_leader_keeps_all_workers(monkeypatch, tmp_path) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(team_routes, "store", store)
    monkeypatch.setattr(
        team_routes,
        "attach_team_leader",
        lambda payload: {
            **payload,
            "leader": f"{payload['name']}·leader",
            "leader_agent_id": "leader-agent",
        },
    )
    monkeypatch.setattr(
        team_routes,
        "apply_avatar_on_write",
        lambda payload, *, role: payload,
    )

    result = team_routes.create_team_payload(
        {"name": "数据分析团队", "members": ["采集", "分析", "质检", "洞察"]},
    )

    assert result["members"] == ["采集", "分析", "质检", "洞察"]


def test_create_team_payload_requires_id_and_name(monkeypatch) -> None:
    def _attach(payload):
        raise ValueError("team id and name are required")

    monkeypatch.setattr(team_routes, "attach_team_leader", _attach)

    with pytest.raises(ValueError, match="team id and name are required"):
        team_routes.create_team_payload({"id": "team-1"})


def test_update_team_payload_syncs_existing_leader_and_refreshes_legacy_avatar(
    monkeypatch,
    tmp_path,
) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(team_routes, "store", store)
    store.upsert_by_key(
        "teams",
        "id",
        "team-1",
        {
            "id": "team-1",
            "name": "Research",
            "leader_agent_id": "leader-agent",
            "avatar": "🧠",
        },
    )
    monkeypatch.setattr(
        team_routes,
        "attach_team_leader",
        lambda payload: {**payload, "leader": "Synced leader"},
    )
    monkeypatch.setattr(team_routes, "is_legacy_emoji_avatar", lambda avatar: True)
    monkeypatch.setattr(
        team_routes,
        "apply_avatar_on_write",
        lambda payload, *, role: {**payload, "avatar": f"{role}.svg"},
    )

    result = team_routes.update_team_payload("team-1", {"members": ["Alice"]})

    assert result["leader"] == "Synced leader"
    assert result["leader_agent_id"] == "leader-agent"
    assert result["avatar"] == "team.svg"
    assert result["members"] == ["Alice"]


def test_delete_team_payload_dismisses_builtin_and_deletes_leader(
    monkeypatch,
    tmp_path,
) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    calls: dict[str, object] = {}
    monkeypatch.setattr(team_routes, "store", store)
    monkeypatch.setattr(
        builtin_agents,
        "dismiss_builtin_agent",
        lambda name: calls.setdefault("dismissed", name),
    )
    monkeypatch.setattr(
        team_leader_agents,
        "delete_team_leader_agent",
        lambda team: calls.setdefault("deleted_leader", team["id"]),
    )
    store.upsert_by_key(
        "teams",
        "id",
        "team-1",
        {"id": "team-1", "name": "Research", "leader_agent_id": "leader-agent"},
    )

    result = team_routes.delete_team_payload("team-1")

    assert result == {"deleted": True, "id": "team-1"}
    assert calls == {"dismissed": "Research", "deleted_leader": "team-1"}
