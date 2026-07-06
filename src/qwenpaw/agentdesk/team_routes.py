# -*- coding: utf-8 -*-
"""AgentDesk team endpoint orchestration helpers."""

from __future__ import annotations

import uuid
from typing import Any

from .avatars import is_legacy_emoji_avatar
from .record_avatars import apply_avatar_on_write, enrich_avatar
from .store import store
from .team_projection import attach_team_leader, normalize_team_payload


def list_team_payloads() -> list[dict[str, Any]]:
    return [enrich_avatar(team, role="team") for team in store.list_items("teams")]


def _attach_leader_or_raise(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return attach_team_leader(payload)
    except ValueError as exc:
        raise ValueError("team id and name are required") from exc


def create_team_payload(body: dict[str, Any] | None) -> dict[str, Any]:
    # Modern AgentDesk API payloads treat ``members`` as worker names. Assign an
    # id before normalization so the legacy "members[0] is leader" migration
    # path does not drop the first worker on new team creation.
    raw = dict(body or {})
    team_id = str(raw.get("id") or uuid.uuid4().hex)
    raw["id"] = team_id
    payload = normalize_team_payload(raw)
    payload["id"] = team_id
    payload.setdefault("members", [])
    payload.setdefault("tags", [])
    payload.pop("leader", None)
    payload.pop("leader_agent_id", None)
    payload = _attach_leader_or_raise(payload)
    payload = apply_avatar_on_write(payload, role="team")
    return store.upsert_by_key("teams", "id", team_id, payload)


def update_team_payload(team_id: str, body: dict[str, Any] | None) -> dict[str, Any]:
    existing = store.get_by_key("teams", "id", team_id) or {"id": team_id}
    merged = {**existing, **dict(body or {}), "id": team_id}
    normalized = normalize_team_payload(merged)
    normalized = _attach_leader_or_raise(normalized)
    if is_legacy_emoji_avatar(str(normalized.get("avatar") or "")):
        normalized = apply_avatar_on_write(normalized, role="team")
    return store.upsert_by_key("teams", "id", team_id, normalized)


def delete_team_payload(team_id: str) -> dict[str, Any]:
    from .builtin_agents import dismiss_builtin_agent
    from .team_leader_agents import delete_team_leader_agent

    existing = store.get_by_key("teams", "id", team_id)
    if existing:
        dismiss_builtin_agent(str(existing.get("name") or ""))
        delete_team_leader_agent(existing)
    return {"deleted": store.delete_by_key("teams", "id", team_id), "id": team_id}
