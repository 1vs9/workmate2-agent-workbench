# -*- coding: utf-8 -*-
"""AgentDesk plaza and employee projection helpers."""

from __future__ import annotations

from typing import Any, Callable

from .agent_profiles import agent_desc_and_skills
from .default_agent import is_plaza_hidden_assignee
from .store import store

# Canonical responsibility/prompt field for plaza cards and employees. The UI
# form path, employee/plaza list payloads and edit modals read ``desc``. Creator
# flows may emit QwenPaw-native profile aliases instead.
DESC_ALIAS_FIELDS = (
    "description",
    "prompt",
    "system_prompt",
    "systemPrompt",
    "responsibilities",
    "persona",
)


def coalesce_desc(payload: dict[str, Any]) -> dict[str, Any]:
    """Populate the canonical ``desc`` from common aliases when it is empty."""
    if str(payload.get("desc") or "").strip():
        return payload
    parts: list[str] = []
    for key in DESC_ALIAS_FIELDS:
        value = str(payload.get(key) or "").strip()
        if value and value not in parts:
            parts.append(value)
    if not parts:
        return payload
    return {**payload, "desc": "\n\n".join(parts)}


def enrich_plaza_card(
    item: dict[str, Any],
    *,
    profiles: dict[str, Any] | None = None,
    employees_by_name: dict[str, dict[str, Any]] | None = None,
    name_index: dict[str, str] | None = None,
    load_profiles: Callable[[], dict[str, Any]],
    match_agent_id_by_display_name: Callable[
        [str, dict[str, Any], dict[str, str] | None],
        str | None,
    ],
) -> dict[str, Any]:
    """Backfill plaza card fields from linked agent profiles when store data is thin."""
    enriched = coalesce_desc(item)
    name = str(enriched.get("name") or "").strip()
    if not name:
        return enriched

    desc = str(enriched.get("desc") or "").strip()
    skills = list(enriched.get("skills") or [])
    if desc and skills:
        return enriched

    if employees_by_name is None:
        employee = store.get_by_key("employees", "name", name)
    else:
        employee = employees_by_name.get(name)
    agent_id = str((employee or {}).get("agent_id") or "").strip()
    if not agent_id:
        if profiles is None:
            profiles = load_profiles()
        agent_id = match_agent_id_by_display_name(
            name,
            profiles,
            name_index,
        ) or ""

    if agent_id and (not desc or not skills):
        agent_desc, agent_skills = agent_desc_and_skills(agent_id)
        if not desc and agent_desc:
            desc = agent_desc
            enriched = {**enriched, "desc": desc}
        if not skills and agent_skills:
            enriched = {**enriched, "skills": agent_skills}

    return enriched


def configured_employees(
    *,
    profiles: dict[str, Any],
    name_index: dict[str, str],
    match_agent_id_by_display_name: Callable[
        [str, dict[str, Any], dict[str, str] | None],
        str | None,
    ],
) -> list[dict[str, Any]]:
    """Employees explicitly joined in AgentDesk store, enriched from agent profiles."""
    employees: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    for item in store.list_items("employees"):
        name = str(item.get("name") or "").strip()
        if not name or is_plaza_hidden_assignee(name):
            continue
        if name in seen_names:
            continue

        agent_id = str(item.get("agent_id") or "").strip()
        if not agent_id and name in profiles:
            agent_id = name
        if not agent_id:
            agent_id = match_agent_id_by_display_name(
                name,
                profiles,
                name_index,
            ) or ""

        ref = profiles.get(agent_id) if agent_id else None
        desc = str(item.get("desc") or "").strip()
        skills = list(item.get("skills") or [])
        if agent_id and (not desc or not skills):
            agent_desc, agent_skills = agent_desc_and_skills(agent_id)
            if not desc:
                desc = agent_desc
            if not skills:
                skills = agent_skills

        employees.append(
            {
                "name": name,
                "id": agent_id or name,
                "agent_id": agent_id or None,
                "desc": desc,
                "tools": list(item.get("tools") or []),
                "skills": skills,
                "mcp": list(item.get("mcp") or []),
                "avatar": item.get("avatar"),
                "workspace_dir": getattr(ref, "workspace_dir", "") if ref else "",
                "enabled": getattr(ref, "enabled", True) if ref else True,
            },
        )
        seen_names.add(name)

    return employees
