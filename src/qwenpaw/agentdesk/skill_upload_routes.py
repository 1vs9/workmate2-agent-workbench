# -*- coding: utf-8 -*-
"""AgentDesk skill upload endpoint orchestration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qwenpaw.exceptions import SkillsError

from ..agents.skill_system import SkillPoolService
from ..config.utils import load_config
from .skill_catalog import pool_skill_names, serialize_pool_skills
from .skill_mount import ensure_skill_mounted
from .skill_uploads import SkillUpload, parse_relative_paths, uploads_to_zip_bytes


class SkillUploadConflictError(Exception):
    def __init__(self, detail: dict[str, Any]) -> None:
        super().__init__("skill upload conflict")
        self.detail = detail


@dataclass(frozen=True)
class SkillUploadResult:
    payload: dict[str, Any]
    reload_agent_id: str | None = None


def recover_pool_upload_conflicts(
    *,
    service: SkillPoolService,
    conflicts: list[dict[str, Any]],
    auto_install_safe: bool,
) -> SkillUploadResult | None:
    """Mount skills that already exist in the pool when re-uploading."""
    if not auto_install_safe or not conflicts:
        return None
    pool_names = pool_skill_names(service)
    conflict_names = [
        str(item.get("skill_name") or "").strip()
        for item in conflicts
        if str(item.get("skill_name") or "").strip()
    ]
    if not conflict_names or len(conflict_names) != len(conflicts):
        return None
    if not all(name in pool_names for name in conflict_names):
        return None
    active_agent = load_config().agents.active_agent or "default"
    for name in conflict_names:
        ensure_skill_mounted(skill_name=name, agent_id=active_agent)
    by_name = {item["name"]: item for item in serialize_pool_skills()}
    return SkillUploadResult(
        payload={
            "uploaded": 0,
            "recovered": conflict_names,
            "skills": [by_name.get(name, {"name": name}) for name in conflict_names],
            "mounted": True,
        },
        reload_agent_id=active_agent,
    )


async def upload_skill_payload(
    *,
    file: SkillUpload | None = None,
    files: list[SkillUpload] | None = None,
    relative_paths: str = "[]",
    auto_install_safe: bool = True,
) -> SkillUploadResult:
    uploads = list(files or [])
    if file is not None:
        uploads.append(file)
    if not uploads:
        return SkillUploadResult({"uploaded": 0, "skills": [], "mounted": False})

    service = SkillPoolService()
    try:
        if len(uploads) == 1 and str(uploads[0].filename or "").lower().endswith(".zip"):
            result = service.import_from_zip(await uploads[0].read())
        else:
            result = service.import_from_zip(
                await uploads_to_zip_bytes(
                    uploads,
                    parse_relative_paths(relative_paths),
                ),
            )
    except SkillsError:
        raise

    if result.get("conflicts"):
        recovered = recover_pool_upload_conflicts(
            service=service,
            conflicts=list(result.get("conflicts") or []),
            auto_install_safe=auto_install_safe,
        )
        if recovered:
            return recovered
        raise SkillUploadConflictError(result)

    imported = list(result.get("imported") or [])
    active_agent = load_config().agents.active_agent or "default"
    reload_agent_id: str | None = None
    if auto_install_safe and imported:
        for name in imported:
            ensure_skill_mounted(skill_name=name, agent_id=active_agent)
        reload_agent_id = active_agent
    by_name = {item["name"]: item for item in serialize_pool_skills()}
    return SkillUploadResult(
        payload={
            "uploaded": len(imported),
            "skills": [by_name.get(name, {"name": name}) for name in imported],
            "mounted": bool(auto_install_safe and imported),
        },
        reload_agent_id=reload_agent_id,
    )
