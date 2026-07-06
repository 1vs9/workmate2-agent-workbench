# -*- coding: utf-8 -*-
"""Skill mounting helpers for AgentDesk chat payloads."""

from __future__ import annotations

import asyncio

from fastapi import Request

from .models import ChatRequest
from .skill_mount import ensure_skill_mounted
from .skill_wizard import (
    EMPLOYEE_CREATOR_SKILL,
    ensure_employee_creator_mounted,
    ensure_packaged_builtin_in_pool,
)
from .store import store as agentdesk_store


def dedupe_skill_names(skill_names: list[str]) -> list[str]:
    """Normalize selected skill names while preserving user order."""
    return list(dict.fromkeys(str(name).strip() for name in skill_names if str(name).strip()))


def ensure_payload_skills_mounted_sync(
    payload: ChatRequest,
    *,
    agent_id: str,
) -> list[str]:
    """Disk-bound skill mount work safe to run in a worker thread."""
    skill_names = dedupe_skill_names(payload.skill_names)
    if not skill_names:
        return []

    mounted: list[str] = []
    user_text = (payload.message or "").strip()
    for skill_name in skill_names:
        if skill_name == EMPLOYEE_CREATOR_SKILL:
            ensure_employee_creator_mounted(
                agent_id=agent_id,
                request=None,
                user_text=user_text,
            )
        else:
            ensure_packaged_builtin_in_pool(skill_name, user_text=user_text)
            ensure_skill_mounted(
                skill_name=skill_name,
                agent_id=agent_id,
                overwrite=False,
                user_text=user_text,
            )
        mounted.append(skill_name)

    task = agentdesk_store.get_by_key("tasks", "id", payload.task_id) or agentdesk_store.ensure_task(
        payload.task_id,
    )
    task["skill_names"] = mounted
    agentdesk_store.upsert_by_key("tasks", "id", payload.task_id, task)
    return mounted


async def ensure_payload_skills_mounted(
    payload: ChatRequest,
    *,
    agent_id: str,
    request: Request | None,
) -> list[str]:
    skill_names = dedupe_skill_names(payload.skill_names)
    if not skill_names:
        return []

    mounted = await asyncio.to_thread(
        ensure_payload_skills_mounted_sync,
        payload,
        agent_id=agent_id,
    )
    if request is not None:
        from ..app.utils import schedule_agent_reload

        for _skill_name in mounted:
            schedule_agent_reload(request, agent_id)
    return mounted
