# -*- coding: utf-8 -*-
"""AgentDesk skill catalog serialization helpers."""

from __future__ import annotations

from typing import Any

from ..agents.skill_system import SkillPoolService
from ..agents.skill_system.store import (
    get_workspace_skills_dir,
    read_skill_from_dir,
    read_skill_manifest,
    render_skill_md,
)
from ..config.utils import load_config
from .agent_workspace import agent_workspace_dir
from .store import store


def skill_content_from_payload(payload: dict[str, Any]) -> str:
    name = str(payload.get("name") or "").strip()
    description = str(payload.get("description") or payload.get("desc") or "").strip()
    raw_content = str(payload.get("content") or payload.get("body") or "").strip()
    if raw_content.startswith("---"):
        return raw_content
    return render_skill_md(
        proposed_name=name,
        description=description or "WorkBuddy skill",
        body=raw_content or "Use this skill when the user requests this capability.",
    )


def agentdesk_skill_item(skill: Any) -> dict[str, Any]:
    source = str(getattr(skill, "source", "") or "")
    if source == "builtin":
        source = "agentdesk"
    return {
        "name": skill.name,
        "description": skill.description,
        "body": skill.content,
        "content": skill.content,
        "source": source,
        "version_text": getattr(skill, "version_text", ""),
        "icon": getattr(skill, "icon", "") or "",
        "emoji": getattr(skill, "emoji", ""),
    }


def pool_skill_names(service: SkillPoolService) -> set[str]:
    return {skill.name for skill in service.list_all_skills()}


def workspace_skill_state(agent_id: str) -> dict[str, dict[str, Any]]:
    try:
        workspace_dir = agent_workspace_dir(agent_id)
        return read_skill_manifest(workspace_dir).get("skills", {})
    except Exception:  # noqa: BLE001
        return {}


def workspace_only_skill_items(
    agent_id: str,
    *,
    existing_names: set[str],
    workspace_state: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Skills mounted on the agent workspace but missing from the shared pool."""
    if not workspace_state:
        return {}
    try:
        workspace_dir = agent_workspace_dir(agent_id)
    except Exception:  # noqa: BLE001
        return {}
    skill_root = get_workspace_skills_dir(workspace_dir)
    items: dict[str, dict[str, Any]] = {}
    for skill_name, ws_entry in workspace_state.items():
        if skill_name in existing_names:
            continue
        skill = read_skill_from_dir(skill_root / skill_name, "agent")
        if skill is None:
            continue
        item = agentdesk_skill_item(skill)
        item["source"] = "workspace"
        item["installed"] = True
        item["enabled"] = bool(ws_entry.get("enabled", False))
        items[skill.name] = item
    return items


def serialize_pool_skills() -> list[dict[str, Any]]:
    active_agent = load_config().agents.active_agent or "default"
    workspace_state = workspace_skill_state(active_agent)
    items: dict[str, dict[str, Any]] = {}
    for skill in SkillPoolService().list_all_skills():
        item = agentdesk_skill_item(skill)
        ws_entry = workspace_state.get(skill.name) or {}
        item["installed"] = bool(ws_entry)
        item["enabled"] = bool(ws_entry.get("enabled", False))
        items[skill.name] = item
    items.update(
        workspace_only_skill_items(
            active_agent,
            existing_names=set(items),
            workspace_state=workspace_state,
        ),
    )
    for item in store.list_items("skills"):
        name = str(item.get("name") or item.get("id") or "").strip()
        if name and name not in items:
            items[name] = {
                "name": name,
                "description": item.get("description", ""),
                "body": item.get("body", ""),
                "content": item.get("body", ""),
                "source": "agentdesk",
                "installed": False,
                "enabled": False,
                **item,
            }
    return sorted(items.values(), key=lambda item: item["name"].lower())
