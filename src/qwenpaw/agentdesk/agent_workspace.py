# -*- coding: utf-8 -*-
"""AgentDesk agent profile and workspace helpers."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from ..config.utils import load_config
from .agents import resolve_agent_id


def agent_workspace_dir(agent_id: str, *, create: bool = True) -> Path:
    config = load_config()
    ref = config.agents.profiles.get(agent_id)
    if ref is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    workspace_dir = Path(getattr(ref, "workspace_dir", "")).expanduser()
    if create:
        workspace_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir


def resolve_agentdesk_agent_id(employee_name: str | None) -> str:
    return resolve_agent_id(employee_name)


def resolve_active_agentdesk_agent_id() -> str:
    """Agent profile used for Skills page install state and auto-mount."""

    config = load_config()
    active = config.agents.active_agent or "default"
    profiles = config.agents.profiles
    return active if active in profiles else "default"
