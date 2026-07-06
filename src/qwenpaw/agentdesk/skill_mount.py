# -*- coding: utf-8 -*-
"""AgentDesk skill mounting boundary."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..agents.skill_system import SkillPoolService, SkillService
from .agent_workspace import agent_workspace_dir


def ensure_skill_mounted(
    *,
    skill_name: str,
    agent_id: str,
    overwrite: bool = False,
    user_text: str | None = None,
) -> dict[str, Any]:
    from .skill_wizard import ensure_packaged_builtin_in_pool

    ensure_packaged_builtin_in_pool(skill_name, user_text=user_text)
    workspace_dir = agent_workspace_dir(agent_id)
    pool_service = SkillPoolService()
    result = pool_service.download_to_workspace(
        skill_name,
        workspace_dir,
        overwrite=overwrite,
    )
    if not result.get("success") and result.get("reason") not in {"conflict"}:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
    enable_result = SkillService(workspace_dir).enable_skill(skill_name)
    if not enable_result.get("success"):
        raise HTTPException(
            status_code=409,
            detail={
                "skill_name": skill_name,
                "agent_id": agent_id,
                "reason": enable_result.get("reason") or result.get("reason"),
            },
        )
    return {
        "mounted": True,
        "skill_name": skill_name,
        "agent_id": agent_id,
        "workspace_dir": str(workspace_dir),
        "download": result,
        "enabled": enable_result,
    }
