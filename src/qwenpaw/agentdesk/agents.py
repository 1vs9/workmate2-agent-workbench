# -*- coding: utf-8 -*-
"""Map AgentDesk employees to QwenPaw agent profiles."""

from __future__ import annotations

from ..config.utils import load_config
from .default_agent import (
    DEFAULT_AGENT_ID,
    DEFAULT_DISPLAY_NAME,
    is_default_agentdesk_assignee,
)
from .store import store


def lookup_agent_id(employee_name: str | None) -> str:
    """Resolve ``employee_name`` to an agent id without provisioning or sync."""
    from .employee_agents import build_agent_display_name_index

    config = load_config()
    profiles = config.agents.profiles
    active = config.agents.active_agent or DEFAULT_AGENT_ID

    if is_default_agentdesk_assignee(employee_name):
        if DEFAULT_AGENT_ID in profiles:
            return DEFAULT_AGENT_ID
        return active if active in profiles else DEFAULT_AGENT_ID

    if not employee_name:
        return active if active in profiles else DEFAULT_AGENT_ID

    name = str(employee_name).strip()
    if not name:
        return active if active in profiles else DEFAULT_AGENT_ID

    employee = store.get_by_key("employees", "name", name)
    stored_id = str((employee or {}).get("agent_id") or "").strip()
    if stored_id and stored_id in profiles:
        return stored_id

    if name in profiles:
        return name

    name_index = build_agent_display_name_index(profiles)
    matched = name_index.get(name)
    if matched:
        return matched

    for agent_id, profile in profiles.items():
        if getattr(profile, "id", agent_id) == name:
            return agent_id

    return active if active in profiles else DEFAULT_AGENT_ID


def resolve_agent_id(employee_name: str | None) -> str:
    """Resolve ``employee_name`` to a configured agent profile id."""
    from .employee_agents import ensure_employee_agent_profile

    if is_default_agentdesk_assignee(employee_name):
        return lookup_agent_id(employee_name)

    if not employee_name:
        return lookup_agent_id(employee_name)

    ensured = ensure_employee_agent_profile(employee_name)
    if ensured:
        return ensured

    return lookup_agent_id(employee_name)


def display_sender(employee_name: str | None, agent_id: str) -> str:
    """Label shown in AgentDesk stream events."""
    if agent_id == DEFAULT_AGENT_ID and (
        not employee_name or is_default_agentdesk_assignee(employee_name)
    ):
        return DEFAULT_DISPLAY_NAME
    if employee_name:
        return employee_name
    return agent_id or "assistant"
