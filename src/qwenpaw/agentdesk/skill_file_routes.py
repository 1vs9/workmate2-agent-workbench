# -*- coding: utf-8 -*-
"""AgentDesk skill file endpoint orchestration helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..config.utils import load_config
from .skill_catalog import workspace_skill_state
from .skill_files import (
    build_skill_file_tree,
    read_skill_file_payload,
    resolve_skill_files_root,
)
from .skill_resolution import resolve_mount_skill_name


def resolve_request_skill_files_root(skill_name: str) -> tuple[Path, str, str]:
    """Return normalized skill name plus its on-disk file root and location."""
    normalized = str(skill_name or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="skill_name is required")
    normalized = resolve_mount_skill_name(normalized)
    active_agent = load_config().agents.active_agent or "default"
    workspace_state = workspace_skill_state(active_agent)
    skill_root, location = resolve_skill_files_root(
        normalized,
        active_agent=active_agent,
        workspace_state=workspace_state,
    )
    return normalized, skill_root, location


def list_skill_file_payloads(skill_name: str) -> dict[str, Any]:
    normalized, skill_root, location = resolve_request_skill_files_root(skill_name)
    return {
        "skill_name": normalized,
        "location": location,
        "entries": build_skill_file_tree(skill_root),
    }


def read_request_skill_file_payload(
    skill_name: str,
    file_path: str,
) -> dict[str, Any]:
    normalized, skill_root, location = resolve_request_skill_files_root(skill_name)
    return read_skill_file_payload(
        normalized,
        file_path,
        skill_root=skill_root,
        location=location,
    )
