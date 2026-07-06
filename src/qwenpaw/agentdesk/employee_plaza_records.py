# -*- coding: utf-8 -*-
"""Record-shaping helpers for employee/plaza write paths."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

EMPLOYEE_PLAZA_SYNC_KEYS = ("desc", "skills", "tools", "mcp", "avatar", "tags")


def employee_plaza_sync_patch(payload: dict[str, Any]) -> dict[str, Any]:
    """Fields mirrored between joined employee records and plaza cards."""
    return {key: payload[key] for key in EMPLOYEE_PLAZA_SYNC_KEYS if key in payload}


def employee_record_from_plaza_item(
    name: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    """Build the employee record created when a plaza card is joined."""
    return {
        "name": name,
        "desc": item.get("desc", ""),
        "tools": item.get("tools", []),
        "skills": item.get("skills", []),
        "mcp": item.get("mcp", []),
        "avatar": item.get("avatar"),
    }


def requested_skill_names(record: dict[str, Any]) -> list[str]:
    """Normalize user-requested skill names from an employee-like record."""
    return [
        str(item).strip()
        for item in list(record.get("skills") or [])
        if str(item).strip()
    ]


def mounted_requested_skill_names(
    agent_id: str,
    requested_skills: list[str],
    *,
    workspace_skill_state: Callable[[str], dict[str, Any]],
    agent_skill_names: Callable[[str], list[str]],
) -> list[str]:
    """Return requested skills that are already present in the agent workspace."""
    if not agent_id:
        return []
    mounted_set = set(workspace_skill_state(agent_id).keys()) or set(
        agent_skill_names(agent_id),
    )
    return [skill for skill in requested_skills if skill in mounted_set]


def joined_employee_payload(
    employee: dict[str, Any],
    *,
    requested_skills: list[str],
    mounted_skills: list[str],
) -> dict[str, Any]:
    """Final response payload for joining a plaza card as an employee."""
    mounted_set = set(mounted_skills)
    return {
        **employee,
        "joined": True,
        "requested_skills": requested_skills,
        "mounted_skills": mounted_skills,
        "failed_skills": [
            skill for skill in requested_skills if skill not in mounted_set
        ],
    }
