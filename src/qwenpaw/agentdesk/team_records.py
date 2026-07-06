# -*- coding: utf-8 -*-
"""AgentDesk team record lookup helpers."""

from __future__ import annotations

from typing import Any

from .models import ChatRequest
from .store import store as agentdesk_store


def resolve_team_record(payload: ChatRequest) -> dict[str, Any] | None:
    """Resolve a team record from ``team_id`` / ``team_name`` on the payload."""
    team_id = str(payload.team_id or "").strip()
    team_name = str(payload.team_name or "").strip()
    if team_id:
        found = agentdesk_store.get_by_key("teams", "id", team_id)
        if found is not None:
            return found
    if team_name:
        for item in agentdesk_store.list_items("teams"):
            if str(item.get("name") or "").strip() == team_name:
                return item
    return None
