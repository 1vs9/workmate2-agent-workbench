# -*- coding: utf-8 -*-
"""AgentDesk skill name resolution and mount preparation helpers."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..agents.skill_system import SkillPoolService
from ..agents.skill_system.store import (
    get_workspace_skills_dir,
    read_skill_from_dir,
    read_skill_pool_manifest,
)
from .agent_workspace import (
    agent_workspace_dir,
    resolve_active_agentdesk_agent_id,
)
from .skill_catalog import serialize_pool_skills, workspace_skill_state
from .store import store

EMPLOYEE_SKILL_MOUNT_ALIASES: dict[str, str] = {
    "excel": "xlsx",
    "web": "browser_visible",
}


def resolve_mount_skill_name(requested: str) -> str:
    """Resolve mount path token to canonical skill name."""
    token = str(requested or "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="skill_name is required")

    items = serialize_pool_skills()
    if any(item.get("name") == token for item in items):
        return token

    def _matches(item: dict[str, Any], *, ignore_case: bool) -> bool:
        values = [
            item.get("name"),
            item.get("id"),
            item.get("pool_name"),
            item.get("poolName"),
            item.get("skill_name"),
            item.get("chat_name"),
        ]
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            if ignore_case:
                if text.lower() == token.lower():
                    return True
            elif text == token:
                return True
        return False

    for item in items:
        if _matches(item, ignore_case=False):
            return str(item.get("name") or token)
    for item in items:
        if _matches(item, ignore_case=True):
            return str(item.get("name") or token)
    token_fold = token.casefold()
    for item in items:
        for field in ("name", "description", "body", "content"):
            text = str(item.get(field) or "").strip()
            if text and (text == token or text.casefold() == token_fold):
                return str(item.get("name") or token)
    return token


def skill_label_matches(token: str, text: str) -> bool:
    """True when *text* equals or clearly refers to the user-facing skill label."""
    label = str(text or "").strip()
    if not label:
        return False
    if label == token:
        return True
    token_fold = token.casefold()
    label_fold = label.casefold()
    if token_fold == label_fold:
        return True
    if len(token) >= 4 and token_fold in label_fold:
        return True
    if len(label) >= 4 and label_fold in token_fold:
        return True
    return False


def find_skill_name_by_label(token: str) -> str | None:
    """Resolve a display label to a canonical pool / store skill name."""
    trimmed = str(token or "").strip()
    if not trimmed:
        return None

    pool_names = {str(item.get("name") or "") for item in serialize_pool_skills()}
    if trimmed in pool_names:
        return trimmed

    for item in store.list_items("skills"):
        name = str(item.get("name") or "").strip()
        for field in ("name", "description", "body"):
            if skill_label_matches(trimmed, str(item.get(field) or "")):
                return name or None

    for item in serialize_pool_skills():
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        for field in ("name", "description", "body", "content"):
            if skill_label_matches(trimmed, str(item.get(field) or "")):
                return name

    return None


def find_workspace_skill_by_label(agent_id: str, token: str) -> str | None:
    """Match a user-facing label against skills already on an agent workspace."""
    trimmed = str(token or "").strip()
    if not trimmed:
        return None
    try:
        workspace_dir = agent_workspace_dir(agent_id)
    except HTTPException:
        return None
    skill_root = get_workspace_skills_dir(workspace_dir)
    if not skill_root.is_dir():
        return None
    for path in sorted(skill_root.iterdir()):
        if not path.is_dir():
            continue
        skill = read_skill_from_dir(path, "agent")
        if skill is None:
            continue
        for text in (skill.name, skill.description, skill.content):
            if skill_label_matches(trimmed, text):
                return skill.name
    return None


def manifest_pool_skill_names() -> set[str]:
    """Canonical skill ids from the shared pool manifest (not UI-only store rows)."""
    manifest = read_skill_pool_manifest()
    return {
        str(name).strip()
        for name in (manifest.get("skills") or {})
        if str(name).strip()
    }


def ensure_agentdesk_store_skill_in_pool(skill_name: str) -> str | None:
    """Import a AgentDesk store skill into the shared pool when missing."""
    name = str(skill_name or "").strip()
    if not name:
        return None
    if name in manifest_pool_skill_names():
        return name
    record = store.get_by_key("skills", "name", name)
    if record is None:
        return None
    content = str(record.get("body") or record.get("content") or "").strip()
    if not content:
        return None
    pool = SkillPoolService()
    created = pool.create_skill(
        name=name,
        content=content,
        installed_from="agentdesk-employee-mount",
    )
    if created:
        return created
    return name if name in manifest_pool_skill_names() else None


def ensure_skill_in_pool_for_mount(skill_name: str, agent_id: str) -> str:
    """Ensure a skill exists in the shared pool before mounting onto an agent."""
    name = str(skill_name or "").strip()
    if not name:
        return name
    if name in manifest_pool_skill_names():
        return name

    imported = ensure_agentdesk_store_skill_in_pool(name)
    if imported and imported in manifest_pool_skill_names():
        return imported

    pool = SkillPoolService()
    candidate_agents: list[str] = []
    for candidate in (agent_id, resolve_active_agentdesk_agent_id()):
        if candidate and candidate not in candidate_agents:
            candidate_agents.append(candidate)

    for candidate_agent in candidate_agents:
        workspace_match = find_workspace_skill_by_label(candidate_agent, name)
        if workspace_match is None and name not in workspace_skill_state(candidate_agent):
            continue
        try:
            workspace_dir = agent_workspace_dir(candidate_agent)
        except HTTPException:
            continue
        upload_name = workspace_match or name
        result = pool.upload_from_workspace(
            workspace_dir,
            upload_name,
            overwrite=True,
        )
        if result.get("success"):
            return str(result.get("name") or upload_name)

    return name


def resolve_employee_mount_skill_name(agent_id: str, requested: str) -> str:
    """Resolve employee-configured skill labels to a mountable pool skill name."""
    token = str(requested or "").strip()
    if not token:
        return token
    existing = resolve_workspace_skill_name(agent_id, token)
    if existing:
        return existing
    aliased = EMPLOYEE_SKILL_MOUNT_ALIASES.get(token.casefold(), token)
    resolved = resolve_mount_skill_name(aliased)
    if resolved in manifest_pool_skill_names():
        return resolved
    workspace_state = workspace_skill_state(agent_id)
    if resolved in workspace_state:
        return resolved

    by_label = find_skill_name_by_label(token)
    if by_label:
        return by_label

    workspace_match = find_workspace_skill_by_label(agent_id, token)
    if workspace_match:
        return workspace_match

    return resolved


def resolve_workspace_skill_name(agent_id: str, requested: str) -> str | None:
    """Resolve a mounted workspace skill by exact/case-insensitive name."""
    token = str(requested or "").strip()
    if not token:
        return None
    workspace_state = workspace_skill_state(agent_id)
    if token in workspace_state:
        return token
    lowered = token.lower()
    for name in workspace_state:
        if str(name).lower() == lowered:
            return str(name)
    return None
