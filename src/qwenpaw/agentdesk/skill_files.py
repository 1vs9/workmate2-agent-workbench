# -*- coding: utf-8 -*-
"""AgentDesk skill file browsing boundary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException

from qwenpaw.exceptions import SkillsError

from ..agents.skill_system import SkillPoolService
from ..agents.skill_system.store import (
    get_skill_pool_dir,
    get_workspace_skills_dir,
    safe_skill_dir,
)
from ..agents.utils.file_handling import read_text_file_with_encoding_fallback
from ..config.utils import load_config
from .agent_workspace import agent_workspace_dir


def find_skill_dir_on_disk(skill_name: str) -> tuple[Path, str] | None:
    """Locate a skill directory in the pool or any agent workspace."""
    try:
        pool_skill_dir = safe_skill_dir(get_skill_pool_dir(), skill_name)
        if pool_skill_dir.is_dir():
            return pool_skill_dir, "pool"
    except SkillsError:
        pass

    config = load_config()
    for profile in config.agents.profiles.values():
        workspace_raw = str(getattr(profile, "workspace_dir", "") or "").strip()
        if not workspace_raw:
            continue
        workspace_dir = Path(workspace_raw).expanduser()
        try:
            skill_dir = safe_skill_dir(get_workspace_skills_dir(workspace_dir), skill_name)
        except SkillsError:
            continue
        if skill_dir.is_dir():
            return skill_dir, "workspace"
    return None


def resolve_skill_files_root(
    skill_name: str,
    *,
    active_agent: str | None = None,
    workspace_state: dict[str, Any] | None = None,
) -> tuple[Path, str]:
    """Return the on-disk skill directory and its location."""
    normalized = str(skill_name or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="skill_name is required")
    try:
        pool_names = {skill.name for skill in SkillPoolService().list_all_skills()}
    except SkillsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    config = load_config()
    resolved_agent = active_agent or config.agents.active_agent or "default"
    workspace_dir = agent_workspace_dir(resolved_agent)
    workspace_skills_dir = get_workspace_skills_dir(workspace_dir)

    if workspace_state is not None and normalized in workspace_state:
        workspace_skill_dir = safe_skill_dir(workspace_skills_dir, normalized)
        if workspace_skill_dir.is_dir():
            return workspace_skill_dir, "workspace"

    if normalized in pool_names:
        pool_skill_dir = safe_skill_dir(get_skill_pool_dir(), normalized)
        if pool_skill_dir.is_dir():
            return pool_skill_dir, "pool"

    workspace_skill_dir = safe_skill_dir(workspace_skills_dir, normalized)
    if workspace_skill_dir.is_dir():
        return workspace_skill_dir, "workspace"

    pool_skill_dir = safe_skill_dir(get_skill_pool_dir(), normalized)
    if pool_skill_dir.is_dir():
        return pool_skill_dir, "pool"

    found = find_skill_dir_on_disk(normalized)
    if found is not None:
        return found

    raise HTTPException(status_code=404, detail=f"Skill '{normalized}' not found")


def safe_skill_relative_path(skill_root: Path, raw_path: str) -> Path:
    raw = str(raw_path or "").replace("\\", "/")
    candidate_rel = Path(raw)
    if (
        candidate_rel.is_absolute()
        or candidate_rel.drive
        or candidate_rel.root
        or ".." in candidate_rel.parts
    ):
        raise HTTPException(status_code=400, detail="Invalid file path")
    rel = Path(raw.strip("/"))
    candidate = (skill_root / rel).resolve()
    try:
        candidate.relative_to(skill_root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid file path") from exc
    return candidate


def build_skill_file_tree(skill_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(
        skill_dir.iterdir(),
        key=lambda item: (not item.is_dir(), item.name.lower()),
    ):
        rel = path.relative_to(skill_dir).as_posix()
        if path.is_dir():
            entries.append(
                {
                    "name": path.name,
                    "path": rel,
                    "type": "directory",
                    "children": build_skill_file_tree(path),
                },
            )
            continue
        if path.is_file():
            entries.append(
                {
                    "name": path.name,
                    "path": rel,
                    "type": "file",
                },
            )
    return entries


def read_skill_file_payload(
    skill_name: str,
    file_path: str,
    *,
    skill_root: Path,
    location: str,
) -> dict[str, Any]:
    target = safe_skill_relative_path(skill_root, file_path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"File '{file_path}' not found")
    try:
        content = read_text_file_with_encoding_fallback(target)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {exc}") from exc
    lower_name = target.name.lower()
    return {
        "skill_name": skill_name,
        "location": location,
        "path": target.relative_to(skill_root).as_posix(),
        "content": content,
        "size": target.stat().st_size,
        "is_markdown": lower_name.endswith(".md"),
    }
