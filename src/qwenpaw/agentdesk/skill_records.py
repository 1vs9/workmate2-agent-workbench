# -*- coding: utf-8 -*-
"""AgentDesk skill create/import record helpers."""

from __future__ import annotations

from typing import Any

from qwenpaw.exceptions import SkillsError

from ..agents.skill_system import SkillPoolService
from ..agents.skill_system.registry import import_builtin_skills
from ..agents.skill_system.store import validate_skill_content
from .skill_catalog import serialize_pool_skills, skill_content_from_payload
from .store import store


class InvalidSkillPayloadError(ValueError):
    """Raised when the AgentDesk skill request payload is invalid."""


class SkillAlreadyExistsError(RuntimeError):
    """Raised when the shared skill pool rejects a duplicate skill name."""


def import_builtin_skill_records(body: dict[str, Any] | None) -> Any:
    """Import built-in skills from a AgentDesk-compatible payload."""
    payload = dict(body or {})
    skill_names = payload.get("skill_names")
    if not isinstance(skill_names, list) or not skill_names:
        raise InvalidSkillPayloadError("skill_names is required")
    return import_builtin_skills(
        [{"skill_name": str(name).strip()} for name in skill_names if str(name).strip()],
    )


def create_skill_record(body: dict[str, Any] | None) -> dict[str, Any]:
    """Create a pool skill and persist a AgentDesk fallback skill card."""
    payload = dict(body or {})
    name = str(payload.get("name") or "").strip()
    if not name:
        raise InvalidSkillPayloadError("name is required")

    content = skill_content_from_payload(payload)
    validate_skill_content(content)
    created_name = SkillPoolService().create_skill(
        name=name,
        content=content,
        config=payload.get("config") if isinstance(payload.get("config"), dict) else None,
        installed_from="agentdesk",
    )
    if created_name is None:
        raise SkillAlreadyExistsError("Skill already exists")

    created_item: dict[str, Any] | None = None
    for item in serialize_pool_skills():
        if item["name"] == created_name:
            created_item = item
            break

    description = str(payload.get("description") or "").strip()
    body_text = content
    if created_item:
        description = str(created_item.get("description") or description)
        body_text = str(created_item.get("body") or body_text)

    store.upsert_by_key(
        "skills",
        "name",
        created_name,
        {
            "name": created_name,
            "description": description,
            "body": body_text,
            "source": "agentdesk",
        },
    )
    if created_item:
        return created_item
    return {"name": created_name, "description": description, "body": body_text}
