# -*- coding: utf-8 -*-
"""AgentDesk skill management endpoint orchestration helpers."""

from __future__ import annotations

from typing import Any

from ..agents.skill_system import SkillPoolService
from .skill_catalog import serialize_pool_skills
from .skill_records import (
    create_skill_record,
    import_builtin_skill_records,
)
from .store import store


def list_skill_payloads() -> list[dict[str, Any]]:
    return serialize_pool_skills()


def import_builtin_skill_payload(body: dict[str, Any] | None) -> Any:
    return import_builtin_skill_records(dict(body or {}))


def create_skill_payload(body: dict[str, Any] | None) -> dict[str, Any]:
    return create_skill_record(dict(body or {}))


def delete_skill_payload(skill_name: str) -> dict[str, Any]:
    deleted_pool = SkillPoolService().delete_skill(skill_name)
    deleted_store = store.delete_by_key("skills", "name", skill_name)
    return {
        "deleted": deleted_pool or deleted_store,
        "name": skill_name,
    }
