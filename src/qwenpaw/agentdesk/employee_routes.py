# -*- coding: utf-8 -*-
"""AgentDesk employee endpoint orchestration helpers."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from ..config.utils import load_config
from .agent_profiles import agent_skill_names
from .agent_workspace import resolve_agentdesk_agent_id
from .employee_plaza_records import (
    employee_plaza_sync_patch,
    requested_skill_names,
)
from .plaza_projection import coalesce_desc, configured_employees
from .record_avatars import apply_avatar_on_write, enrich_avatar
from .skill_mount import ensure_skill_mounted
from .skill_resolution import (
    ensure_skill_in_pool_for_mount,
    resolve_employee_mount_skill_name,
    resolve_workspace_skill_name,
)
from .store import store

logger = logging.getLogger(__name__)


def list_employee_payloads() -> list[dict[str, Any]]:
    from .employee_agents import (
        _match_agent_id_by_display_name,
        build_agent_display_name_index,
    )

    profiles = load_config().agents.profiles
    name_index = build_agent_display_name_index(profiles)
    employees = configured_employees(
        profiles=profiles,
        name_index=name_index,
        match_agent_id_by_display_name=_match_agent_id_by_display_name,
    )
    return [enrich_avatar(employee, role="employee") for employee in employees]


def create_employee_payload(body: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(body or {})
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    payload = coalesce_desc(payload)
    payload = apply_avatar_on_write(payload, role="employee")
    return store.upsert_by_key("employees", "name", name, payload)


def sync_employee_agent_skills(employee_name: str) -> None:
    """Re-provision agent workspace skills after employee/plaza record changes."""
    from .employee_agents import ensure_employee_agent_profile

    trimmed = str(employee_name or "").strip()
    if trimmed:
        ensure_employee_agent_profile(trimmed)


def mount_employee_requested_skills(
    agent_id: str,
    skill_names: list[str],
) -> tuple[list[str], list[str]]:
    """Mount requested skills on an employee agent workspace."""
    requested = [str(item).strip() for item in skill_names if str(item).strip()]
    mounted: list[str] = []
    failed: list[str] = []
    for skill_name in requested:
        mount_name = resolve_employee_mount_skill_name(agent_id, skill_name)
        if resolve_workspace_skill_name(agent_id, mount_name):
            mounted.append(skill_name)
            continue
        mount_name = ensure_skill_in_pool_for_mount(mount_name, agent_id)
        try:
            ensure_skill_mounted(skill_name=mount_name, agent_id=agent_id)
            mounted.append(skill_name)
        except HTTPException:
            failed.append(skill_name)
        except Exception:  # noqa: BLE001 - mount must not block employee save
            logger.exception(
                "Failed to mount skill %s on agent %s",
                skill_name,
                agent_id,
            )
            failed.append(skill_name)
    return mounted, failed


def update_employee_payload(
    name: str,
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    from .employee_agents import invalidate_employee_sync_cache_for_name
    from .avatars import is_legacy_emoji_avatar

    payload = dict(body or {})
    payload["name"] = str(payload.get("name") or name)
    payload = coalesce_desc(payload)
    if is_legacy_emoji_avatar(str(payload.get("avatar") or "")):
        payload = apply_avatar_on_write(payload, role="employee")
    if "skills" in payload or "desc" in payload:
        invalidate_employee_sync_cache_for_name(name)
    result = store.upsert_by_key("employees", "name", name, payload)
    plaza_item = store.get_by_key("plaza", "name", name)
    if plaza_item is not None:
        plaza_patch = employee_plaza_sync_patch(payload)
        if plaza_patch:
            store.upsert_by_key(
                "plaza",
                "name",
                name,
                {**plaza_item, **plaza_patch},
            )
    if "skills" in payload or "desc" in payload:
        sync_employee_agent_skills(name)
    if "skills" in payload:
        requested_skills = requested_skill_names(payload)
        agent_id = resolve_agentdesk_agent_id(name)
        mounted_skills: list[str] = []
        failed_skills: list[str] = []
        if agent_id and requested_skills:
            mounted_skills, failed_skills = mount_employee_requested_skills(
                agent_id,
                requested_skills,
            )
        result = {
            **result,
            "requested_skills": requested_skills,
            "mounted_skills": mounted_skills,
            "failed_skills": failed_skills,
        }
    return result


def delete_employee_payload(name: str) -> dict[str, Any]:
    from .employee_agents import delete_employee_agent

    trimmed = str(name or "").strip()
    if not trimmed:
        raise ValueError("name is required")

    if not delete_employee_agent(trimmed):
        raise LookupError(f"Employee '{trimmed}' not found")

    return {"deleted": True, "name": trimmed}
