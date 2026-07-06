# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from qwenpaw.agentdesk import skill_upload_routes


class _Upload:
    def __init__(self, filename: str, content: bytes = b"payload") -> None:
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


class _Config:
    class Agents:
        active_agent = "agent-1"

    agents = Agents()


def test_recover_pool_upload_conflicts_mounts_existing_pool_skills(monkeypatch) -> None:
    mounted: list[tuple[str, str]] = []
    monkeypatch.setattr(skill_upload_routes, "pool_skill_names", lambda service: {"search"})
    monkeypatch.setattr(skill_upload_routes, "load_config", lambda: _Config())
    monkeypatch.setattr(
        skill_upload_routes,
        "ensure_skill_mounted",
        lambda *, skill_name, agent_id: mounted.append((skill_name, agent_id)),
    )
    monkeypatch.setattr(
        skill_upload_routes,
        "serialize_pool_skills",
        lambda: [{"name": "search", "desc": "Search"}],
    )

    result = skill_upload_routes.recover_pool_upload_conflicts(
        service=object(),
        conflicts=[{"skill_name": "search"}],
        auto_install_safe=True,
    )

    assert result is not None
    assert result.reload_agent_id == "agent-1"
    assert result.payload == {
        "uploaded": 0,
        "recovered": ["search"],
        "skills": [{"name": "search", "desc": "Search"}],
        "mounted": True,
    }
    assert mounted == [("search", "agent-1")]


@pytest.mark.asyncio
async def test_upload_skill_payload_returns_empty_without_uploads() -> None:
    result = await skill_upload_routes.upload_skill_payload(files=[])

    assert result.payload == {"uploaded": 0, "skills": [], "mounted": False}
    assert result.reload_agent_id is None


@pytest.mark.asyncio
async def test_upload_skill_payload_imports_and_mounts(monkeypatch) -> None:
    mounted: list[tuple[str, str]] = []

    class Pool:
        def import_from_zip(self, payload: bytes):
            assert payload
            return {"imported": ["search"]}

    monkeypatch.setattr(skill_upload_routes, "SkillPoolService", lambda: Pool())
    monkeypatch.setattr(skill_upload_routes, "load_config", lambda: _Config())
    monkeypatch.setattr(
        skill_upload_routes,
        "ensure_skill_mounted",
        lambda *, skill_name, agent_id: mounted.append((skill_name, agent_id)),
    )
    monkeypatch.setattr(
        skill_upload_routes,
        "serialize_pool_skills",
        lambda: [{"name": "search", "desc": "Search"}],
    )
    async def _zip_bytes(uploads, relative_paths):
        return b"zip-bytes"

    monkeypatch.setattr(skill_upload_routes, "uploads_to_zip_bytes", _zip_bytes)

    result = await skill_upload_routes.upload_skill_payload(
        files=[_Upload("SKILL.md")],
        relative_paths='["SKILL.md"]',
    )

    assert result.reload_agent_id == "agent-1"
    assert result.payload == {
        "uploaded": 1,
        "skills": [{"name": "search", "desc": "Search"}],
        "mounted": True,
    }
    assert mounted == [("search", "agent-1")]


@pytest.mark.asyncio
async def test_upload_skill_payload_raises_conflict_when_unrecoverable(monkeypatch) -> None:
    class Pool:
        def import_from_zip(self, payload: bytes):
            return {"conflicts": [{"skill_name": "missing"}]}

    monkeypatch.setattr(skill_upload_routes, "SkillPoolService", lambda: Pool())
    monkeypatch.setattr(skill_upload_routes, "pool_skill_names", lambda service: set())

    with pytest.raises(skill_upload_routes.SkillUploadConflictError) as exc:
        await skill_upload_routes.upload_skill_payload(
            files=[_Upload("bundle.zip")],
        )

    assert exc.value.detail == {"conflicts": [{"skill_name": "missing"}]}
