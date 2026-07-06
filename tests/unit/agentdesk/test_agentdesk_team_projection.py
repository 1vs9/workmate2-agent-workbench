# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from qwenpaw.agentdesk import team_projection


def test_normalize_team_payload_promotes_legacy_first_member_to_leader() -> None:
    normalized = team_projection.normalize_team_payload(
        {
            "name": "Research",
            "members": [" Alice ", "Bob", "", "  "],
        },
    )

    assert normalized["leader"] == "Alice"
    assert normalized["members"] == ["Bob"]


def test_normalize_team_payload_removes_explicit_leader_from_members() -> None:
    normalized = team_projection.normalize_team_payload(
        {
            "id": "team-1",
            "name": "Research",
            "leader": "Alice",
            "members": ["Alice", "Bob"],
        },
    )

    assert normalized["leader"] == "Alice"
    assert normalized["members"] == ["Bob"]


def test_normalize_team_payload_preserves_existing_leader_agent_id() -> None:
    normalized = team_projection.normalize_team_payload(
        {
            "id": "team-1",
            "name": "Research",
            "leader_agent_id": "leader-agent",
            "members": ["Alice", "Bob"],
        },
    )

    assert normalized["leader_agent_id"] == "leader-agent"
    assert normalized["members"] == ["Alice", "Bob"]


def test_attach_team_leader_provisions_new_leader(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def _provision(**kwargs):
        calls.append(kwargs)
        return {"leader_name": "Research leader", "agent_id": "leader-agent"}

    monkeypatch.setattr(team_projection, "provision_team_leader_agent", _provision)

    payload = team_projection.attach_team_leader(
        {
            "id": "team-1",
            "name": "Research",
            "desc": "Coordinate research",
            "members": ["Alice", "Bob"],
        },
    )

    assert payload["leader"] == "Research leader"
    assert payload["leader_agent_id"] == "leader-agent"
    assert calls == [
        {
            "team_id": "team-1",
            "team_name": "Research",
            "team_prompt": "Coordinate research",
            "workers": ["Alice", "Bob"],
        },
    ]


def test_attach_team_leader_syncs_existing_leader(monkeypatch) -> None:
    synced: list[dict[str, object]] = []

    def _sync(payload):
        synced.append(payload)
        return {"leader_name": "Synced leader", "agent_id": "leader-agent"}

    monkeypatch.setattr(team_projection, "sync_team_leader_agent", _sync)

    payload = team_projection.attach_team_leader(
        {
            "id": "team-1",
            "name": "Research",
            "leader_agent_id": "leader-agent",
            "members": ["Alice"],
        },
    )

    assert payload["leader"] == "Synced leader"
    assert payload["leader_agent_id"] == "leader-agent"
    assert synced == [
        {
            "id": "team-1",
            "name": "Research",
            "leader_agent_id": "leader-agent",
            "members": ["Alice"],
        },
    ]


def test_attach_team_leader_requires_id_and_name() -> None:
    with pytest.raises(ValueError, match="team id and name are required"):
        team_projection.attach_team_leader({"id": "team-1"})
