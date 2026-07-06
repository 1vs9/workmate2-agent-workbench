# -*- coding: utf-8 -*-
"""AgentDesk plaza endpoint orchestration helpers."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from ..config.utils import load_config
from .agent_profiles import agent_skill_names
from .default_agent import is_plaza_hidden_assignee
from .employee_plaza_records import (
    employee_plaza_sync_patch,
    employee_record_from_plaza_item,
    joined_employee_payload,
    mounted_requested_skill_names,
    requested_skill_names,
)
from .employee_routes import sync_employee_agent_skills
from .plaza_projection import (
    coalesce_desc,
    configured_employees,
    enrich_plaza_card,
)
from .record_avatars import (
    apply_avatar_on_write,
    enrich_avatar,
    maybe_persist_avatar,
)
from .skill_catalog import workspace_skill_state
from .store import store

logger = logging.getLogger(__name__)

_PLAZA_ORPHAN_SYNC_AT = 0.0
_PLAZA_ORPHAN_SYNC_TTL_S = 60.0
_PLAZA_ORPHAN_SYNC_LOCK = threading.Lock()
_PLAZA_ORPHAN_SYNC_RUNNING = False


def invalidate_plaza_orphan_sync() -> None:
    global _PLAZA_ORPHAN_SYNC_AT
    _PLAZA_ORPHAN_SYNC_AT = 0.0


def run_orphan_plaza_sync() -> None:
    global _PLAZA_ORPHAN_SYNC_AT, _PLAZA_ORPHAN_SYNC_RUNNING
    from .employee_agents import sync_orphan_employee_agents_to_plaza

    try:
        sync_orphan_employee_agents_to_plaza()
        _PLAZA_ORPHAN_SYNC_AT = time.time()
    except Exception:  # noqa: BLE001 - background sync must not crash the thread
        logger.exception("Background plaza orphan sync failed")
    finally:
        with _PLAZA_ORPHAN_SYNC_LOCK:
            _PLAZA_ORPHAN_SYNC_RUNNING = False


def schedule_orphan_plaza_sync() -> None:
    """Fire-and-forget orphan sync so GET /api/plaza stays fast."""
    global _PLAZA_ORPHAN_SYNC_RUNNING
    now = time.time()
    if now - _PLAZA_ORPHAN_SYNC_AT < _PLAZA_ORPHAN_SYNC_TTL_S:
        return
    with _PLAZA_ORPHAN_SYNC_LOCK:
        if _PLAZA_ORPHAN_SYNC_RUNNING:
            return
        _PLAZA_ORPHAN_SYNC_RUNNING = True
    threading.Thread(
        target=run_orphan_plaza_sync,
        daemon=True,
        name="plaza-orphan-sync",
    ).start()


def maybe_sync_orphan_plaza(*, force: bool = False, blocking: bool = False) -> None:
    """Sync employee agents missing from plaza. Blocking only for write paths."""
    if force or blocking:
        run_orphan_plaza_sync()
        return
    schedule_orphan_plaza_sync()


def _enrich_plaza_item(
    item: dict[str, Any],
    *,
    profiles: dict[str, Any] | None = None,
    employees_by_name: dict[str, dict[str, Any]] | None = None,
    name_index: dict[str, str] | None = None,
) -> dict[str, Any]:
    from .employee_agents import _match_agent_id_by_display_name

    return enrich_plaza_card(
        item,
        profiles=profiles,
        employees_by_name=employees_by_name,
        name_index=name_index,
        load_profiles=lambda: load_config().agents.profiles,
        match_agent_id_by_display_name=_match_agent_id_by_display_name,
    )


def _configured_employee_payloads(
    *,
    profiles: dict[str, Any] | None = None,
    name_index: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    from .employee_agents import (
        _match_agent_id_by_display_name,
        build_agent_display_name_index,
    )

    config = load_config()
    if profiles is None:
        profiles = config.agents.profiles
    if name_index is None:
        name_index = build_agent_display_name_index(profiles)
    return configured_employees(
        profiles=profiles,
        name_index=name_index,
        match_agent_id_by_display_name=_match_agent_id_by_display_name,
    )


def list_plaza_payloads() -> list[dict[str, Any]]:
    from .employee_agents import build_agent_display_name_index

    schedule_orphan_plaza_sync()
    profiles = load_config().agents.profiles
    name_index = build_agent_display_name_index(profiles)
    snapshot = store.read()
    employees_by_name = {
        str(item.get("name") or "").strip(): item
        for item in snapshot.get("employees", [])
        if str(item.get("name") or "").strip()
    }
    plaza = [
        item
        for item in snapshot.get("plaza", [])
        if not is_plaza_hidden_assignee(item.get("name"))
    ]
    if plaza:
        return [
            _enrich_plaza_item(
                enrich_avatar(item, role="employee"),
                profiles=profiles,
                employees_by_name=employees_by_name,
                name_index=name_index,
            )
            for item in plaza
        ]
    return [
        enrich_avatar(
            {
                "name": employee["name"],
                "tags": ["QwenPaw"],
                "desc": employee.get("desc") or "QwenPaw agent",
                "author": "QwenPaw",
                "usage": "作为 AgentDesk 数字员工执行任务",
                "skills": employee.get("skills", []),
                "mcp": employee.get("mcp", []),
                "avatar": employee.get("avatar"),
            },
            role="employee",
        )
        for employee in _configured_employee_payloads(
            profiles=profiles,
            name_index=name_index,
        )
        if not is_plaza_hidden_assignee(employee.get("name"))
    ]


def create_plaza_payload(body: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(body or {})
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    payload.setdefault("tags", [])
    payload = coalesce_desc(payload)
    payload = apply_avatar_on_write(payload, role="employee")
    invalidate_plaza_orphan_sync()
    return store.upsert_by_key("plaza", "name", name, payload)


def join_plaza_payload(name: str) -> dict[str, Any]:
    from .employee_agents import ensure_employee_agent_profile

    maybe_sync_orphan_plaza(force=True, blocking=True)

    item = store.get_by_key("plaza", "name", name) or {"name": name}
    item = coalesce_desc(maybe_persist_avatar("plaza", "name", item))
    employee = employee_record_from_plaza_item(name, item)
    store.upsert_by_key("employees", "name", name, employee)
    if item:
        store.upsert_by_key(
            "plaza",
            "name",
            name,
            {**item, "joined": True},
        )
    agent_id = ensure_employee_agent_profile(name)
    if agent_id:
        employee = store.get_by_key("employees", "name", name) or employee
        employee["agent_id"] = agent_id
    requested_skills = requested_skill_names(employee)
    mounted_skills = mounted_requested_skill_names(
        agent_id or "",
        requested_skills,
        workspace_skill_state=workspace_skill_state,
        agent_skill_names=agent_skill_names,
    )
    return joined_employee_payload(
        employee,
        requested_skills=requested_skills,
        mounted_skills=mounted_skills,
    )


def update_plaza_payload(
    name: str,
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    from .avatars import is_legacy_emoji_avatar

    payload = dict(body or {})
    payload["name"] = str(payload.get("name") or name)
    payload = coalesce_desc(payload)
    if is_legacy_emoji_avatar(str(payload.get("avatar") or "")):
        payload = apply_avatar_on_write(payload, role="employee")
    invalidate_plaza_orphan_sync()
    result = store.upsert_by_key("plaza", "name", name, payload)
    employee = store.get_by_key("employees", "name", name)
    if employee is not None:
        employee_patch = employee_plaza_sync_patch(payload)
        if employee_patch:
            store.upsert_by_key(
                "employees",
                "name",
                name,
                {**employee, **employee_patch},
            )
        if "skills" in payload or "desc" in payload:
            sync_employee_agent_skills(name)
    return result


def delete_plaza_payload(name: str) -> dict[str, Any]:
    from .employee_agents import delete_employee_agent

    trimmed = str(name or "").strip()
    if not trimmed:
        raise ValueError("name is required")

    deleted = delete_employee_agent(trimmed)
    if not deleted:
        raise LookupError(f"Plaza item '{trimmed}' not found")

    invalidate_plaza_orphan_sync()
    return {"deleted": True, "name": trimmed}
