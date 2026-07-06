# -*- coding: utf-8 -*-
"""AgentDesk agent profile metadata helpers."""

from __future__ import annotations

from typing import Any

from ..config.config import load_agent_config


def agent_desc_and_skills(agent_id: str) -> tuple[str, list[str]]:
    """Load description and skill names from agent config in one disk read."""
    try:
        cfg = load_agent_config(agent_id)
        desc = str(getattr(cfg, "description", "") or "").strip()
        skills = [
            str(item).strip()
            for item in (getattr(cfg, "skill_names", []) or [])
            if str(item).strip()
        ]
        return desc, skills
    except Exception:  # noqa: BLE001 - config can be user-edited
        return "", []


def agent_description(agent_id: str) -> str:
    desc, _skills = agent_desc_and_skills(agent_id)
    return desc


def agent_skill_names(agent_id: str) -> list[str]:
    _desc, skills = agent_desc_and_skills(agent_id)
    return skills


def agent_display_name(
    agent_id: str,
    store_overrides: dict[str, dict[str, Any]],
) -> str:
    """Human-readable label for a configured agent profile."""
    for item in store_overrides.values():
        if str(item.get("agent_id") or "").strip() == agent_id:
            label = str(item.get("name") or "").strip()
            if label and not label.startswith("emp_"):
                return label
    try:
        label = str(load_agent_config(agent_id).name or "").strip()
        if label and not label.startswith("emp_"):
            return label
    except Exception:  # noqa: BLE001 - config can be user-edited
        pass
    return agent_id
