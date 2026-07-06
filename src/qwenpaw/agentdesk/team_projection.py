# -*- coding: utf-8 -*-
"""AgentDesk team record projection and leader binding helpers."""

from __future__ import annotations

from typing import Any

from .team_leader_agents import provision_team_leader_agent, sync_team_leader_agent


def normalize_team_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize team leader/member shape for current and legacy payloads."""
    members_raw = payload.get("members")
    members = (
        [str(name).strip() for name in members_raw if str(name).strip()]
        if isinstance(members_raw, list)
        else []
    )
    leader = str(payload.get("leader") or "").strip()
    leader_agent_id = str(payload.get("leader_agent_id") or "").strip()
    if leader_agent_id or leader:
        members = [name for name in members if name != leader]
    elif members and not payload.get("id"):
        # Legacy create payloads stored the leader as members[0].
        leader = members[0]
        members = members[1:]

    normalized = {**payload, "members": members}
    if leader:
        normalized["leader"] = leader
    if leader_agent_id:
        normalized["leader_agent_id"] = leader_agent_id
    return normalized


def attach_team_leader(payload: dict[str, Any]) -> dict[str, Any]:
    """Create or sync the hidden leader agent for a team payload."""
    team_id = str(payload.get("id") or "").strip()
    team_name = str(payload.get("name") or "").strip()
    if not team_id or not team_name:
        raise ValueError("team id and name are required")

    workers = list(payload.get("members") or [])
    team_prompt = str(payload.get("desc") or "")
    if payload.get("leader_agent_id"):
        info = sync_team_leader_agent({**payload, "id": team_id})
    else:
        info = provision_team_leader_agent(
            team_id=team_id,
            team_name=team_name,
            team_prompt=team_prompt,
            workers=workers,
        )

    return {
        **payload,
        "leader": info["leader_name"],
        "leader_agent_id": info["agent_id"],
    }
