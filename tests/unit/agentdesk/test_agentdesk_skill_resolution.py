# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from qwenpaw.agentdesk import skill_resolution


def test_skill_label_matches_exact_casefold_and_substring() -> None:
    assert skill_resolution.skill_label_matches("Search", "Search")
    assert skill_resolution.skill_label_matches("search", "Search")
    assert skill_resolution.skill_label_matches("browser", "browser_visible")
    assert not skill_resolution.skill_label_matches("web", "browser_visible")


def test_resolve_mount_skill_name_matches_alias_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        skill_resolution,
        "serialize_pool_skills",
        lambda: [{"name": "browser_visible", "chat_name": "Web"}],
    )

    assert skill_resolution.resolve_mount_skill_name("Web") == "browser_visible"
    assert skill_resolution.resolve_mount_skill_name("web") == "browser_visible"


def test_resolve_mount_skill_name_rejects_empty_token() -> None:
    with pytest.raises(HTTPException):
        skill_resolution.resolve_mount_skill_name(" ")


def test_find_skill_name_by_label_checks_store_and_pool(monkeypatch) -> None:
    monkeypatch.setattr(
        skill_resolution,
        "serialize_pool_skills",
        lambda: [
            {"name": "PoolSkill", "description": "Pool description", "body": ""},
        ],
    )
    monkeypatch.setattr(
        skill_resolution,
        "store",
        SimpleNamespace(
            list_items=lambda collection: [
                {"name": "StoreSkill", "description": "Store description"},
            ],
        ),
    )

    assert skill_resolution.find_skill_name_by_label("Store") == "StoreSkill"
    assert skill_resolution.find_skill_name_by_label("Pool") == "PoolSkill"


def test_resolve_workspace_skill_name_matches_case_insensitive(monkeypatch) -> None:
    monkeypatch.setattr(
        skill_resolution,
        "workspace_skill_state",
        lambda agent_id: {"SearchSkill": {"enabled": True}},
    )

    assert skill_resolution.resolve_workspace_skill_name("agent-1", "searchskill") == "SearchSkill"


def test_manifest_pool_skill_names_strips_empty_names(monkeypatch) -> None:
    monkeypatch.setattr(
        skill_resolution,
        "read_skill_pool_manifest",
        lambda: {"skills": {" Search ": {}, "": {}, "Write": {}}},
    )

    assert skill_resolution.manifest_pool_skill_names() == {"Search", "Write"}


def test_ensure_agentdesk_store_skill_in_pool_imports_store_skill(monkeypatch) -> None:
    created: list[tuple[str, str, str]] = []
    manifests = [set(), {"StoreSkill"}]

    def _manifest_names() -> set[str]:
        return manifests.pop(0) if manifests else {"StoreSkill"}

    class _Pool:
        def create_skill(self, *, name: str, content: str, installed_from: str) -> str:
            created.append((name, content, installed_from))
            return name

    monkeypatch.setattr(skill_resolution, "manifest_pool_skill_names", _manifest_names)
    monkeypatch.setattr(skill_resolution, "SkillPoolService", lambda: _Pool())
    monkeypatch.setattr(
        skill_resolution,
        "store",
        SimpleNamespace(
            get_by_key=lambda collection, key, value: {
                "name": "StoreSkill",
                "body": "Body",
            },
        ),
    )

    assert skill_resolution.ensure_agentdesk_store_skill_in_pool("StoreSkill") == "StoreSkill"
    assert created == [("StoreSkill", "Body", "agentdesk-employee-mount")]


def test_find_workspace_skill_by_label_reads_workspace_dirs(monkeypatch, tmp_path) -> None:
    skill_dir = tmp_path / "skill-a"
    skill_dir.mkdir()
    monkeypatch.setattr(skill_resolution, "agent_workspace_dir", lambda agent_id: tmp_path)
    monkeypatch.setattr(skill_resolution, "get_workspace_skills_dir", lambda path: path)
    monkeypatch.setattr(
        skill_resolution,
        "read_skill_from_dir",
        lambda path, source: SimpleNamespace(
            name="SearchSkill",
            description="Search the web",
            content="Body",
        ),
    )

    assert skill_resolution.find_workspace_skill_by_label("agent-1", "Search") == "SearchSkill"


def test_ensure_skill_in_pool_for_mount_uploads_workspace_skill(monkeypatch, tmp_path) -> None:
    uploads: list[tuple[Path, str, bool]] = []

    class _Pool:
        def upload_from_workspace(self, workspace_dir: Path, upload_name: str, *, overwrite: bool):
            uploads.append((workspace_dir, upload_name, overwrite))
            return {"success": True, "name": upload_name}

    monkeypatch.setattr(skill_resolution, "manifest_pool_skill_names", lambda: set())
    monkeypatch.setattr(skill_resolution, "ensure_agentdesk_store_skill_in_pool", lambda name: None)
    monkeypatch.setattr(skill_resolution, "resolve_active_agentdesk_agent_id", lambda: "active")
    monkeypatch.setattr(
        skill_resolution,
        "find_workspace_skill_by_label",
        lambda agent_id, name: "WorkspaceSkill" if agent_id == "agent-1" else None,
    )
    monkeypatch.setattr(skill_resolution, "workspace_skill_state", lambda agent_id: {})
    monkeypatch.setattr(skill_resolution, "agent_workspace_dir", lambda agent_id: tmp_path / agent_id)
    monkeypatch.setattr(skill_resolution, "SkillPoolService", lambda: _Pool())

    assert skill_resolution.ensure_skill_in_pool_for_mount("label", "agent-1") == "WorkspaceSkill"
    assert uploads == [(tmp_path / "agent-1", "WorkspaceSkill", True)]


def test_resolve_employee_mount_skill_name_applies_alias(monkeypatch) -> None:
    monkeypatch.setattr(skill_resolution, "resolve_workspace_skill_name", lambda agent_id, token: None)
    monkeypatch.setattr(skill_resolution, "resolve_mount_skill_name", lambda token: token)
    monkeypatch.setattr(skill_resolution, "manifest_pool_skill_names", lambda: {"xlsx"})
    monkeypatch.setattr(skill_resolution, "workspace_skill_state", lambda agent_id: {})
    monkeypatch.setattr(skill_resolution, "find_skill_name_by_label", lambda token: None)
    monkeypatch.setattr(skill_resolution, "find_workspace_skill_by_label", lambda agent_id, token: None)

    assert skill_resolution.resolve_employee_mount_skill_name("agent-1", "excel") == "xlsx"
