# -*- coding: utf-8 -*-
"""AgentDesk skill endpoint orchestration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .agent_workspace import agent_workspace_dir, resolve_agentdesk_agent_id
from .skill_mount import ensure_skill_mounted
from .skill_resolution import (
    resolve_mount_skill_name,
    resolve_workspace_skill_name,
)
from .task_records import attach_skill_to_task_record


@dataclass(frozen=True)
class SkillMutationResult:
    agent_id: str
    payload: dict[str, Any]


def mount_skill_for_request(
    skill_name: str,
    body: dict[str, Any] | None,
) -> SkillMutationResult:
    payload = dict(body or {})
    agent_id = str(payload.get("agent_id") or "").strip()
    if not agent_id:
        agent_id = resolve_agentdesk_agent_id(
            str(payload.get("employee_name") or "") or None,
        )

    workspace_resolved = resolve_workspace_skill_name(agent_id, skill_name)
    resolved_name = workspace_resolved or resolve_mount_skill_name(skill_name)
    if workspace_resolved:
        result = {
            "mounted": True,
            "already_mounted": True,
            "skill_name": workspace_resolved,
            "requested_skill": skill_name,
            "agent_id": agent_id,
            "workspace_dir": str(agent_workspace_dir(agent_id)),
        }
    else:
        result = ensure_skill_mounted(
            skill_name=resolved_name,
            agent_id=agent_id,
            overwrite=bool(payload.get("overwrite", False)),
        )
        if resolved_name != skill_name:
            result["requested_skill"] = skill_name

    task_id = str(payload.get("task_id") or "").strip()
    if task_id:
        attach_skill_to_task_record(task_id, resolved_name)

    return SkillMutationResult(agent_id=agent_id, payload=result)
