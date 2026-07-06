# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from qwenpaw.agentdesk import skill_file_routes


class _Config:
    class Agents:
        active_agent = "agent-1"

    agents = Agents()


def test_resolve_request_skill_files_root_uses_active_agent_state(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {}
    skill_root = tmp_path / "skill"

    monkeypatch.setattr(skill_file_routes, "load_config", lambda: _Config())
    monkeypatch.setattr(
        skill_file_routes,
        "resolve_mount_skill_name",
        lambda name: f"{name}-resolved",
    )
    monkeypatch.setattr(
        skill_file_routes,
        "workspace_skill_state",
        lambda agent_id: {"agent_id": agent_id},
    )

    def _resolve(skill_name: str, *, active_agent: str, workspace_state: dict[str, object]):
        calls["skill_name"] = skill_name
        calls["active_agent"] = active_agent
        calls["workspace_state"] = workspace_state
        return skill_root, "workspace"

    monkeypatch.setattr(skill_file_routes, "resolve_skill_files_root", _resolve)

    assert skill_file_routes.resolve_request_skill_files_root(" Search ") == (
        "Search-resolved",
        skill_root,
        "workspace",
    )
    assert calls == {
        "skill_name": "Search-resolved",
        "active_agent": "agent-1",
        "workspace_state": {"agent_id": "agent-1"},
    }


def test_resolve_request_skill_files_root_rejects_empty_name() -> None:
    with pytest.raises(HTTPException) as exc:
        skill_file_routes.resolve_request_skill_files_root(" ")

    assert exc.value.status_code == 400


def test_list_skill_file_payloads_returns_tree(monkeypatch, tmp_path) -> None:
    skill_root = tmp_path / "skill"
    monkeypatch.setattr(
        skill_file_routes,
        "resolve_request_skill_files_root",
        lambda skill_name: ("search", skill_root, "pool"),
    )
    monkeypatch.setattr(
        skill_file_routes,
        "build_skill_file_tree",
        lambda root: [{"name": root.name, "type": "directory"}],
    )

    assert skill_file_routes.list_skill_file_payloads("search") == {
        "skill_name": "search",
        "location": "pool",
        "entries": [{"name": "skill", "type": "directory"}],
    }


def test_read_request_skill_file_payload_delegates_to_reader(monkeypatch, tmp_path) -> None:
    skill_root = tmp_path / "skill"
    calls: dict[str, object] = {}
    monkeypatch.setattr(
        skill_file_routes,
        "resolve_request_skill_files_root",
        lambda skill_name: ("search", skill_root, "workspace"),
    )

    def _read(skill_name: str, file_path: str, *, skill_root: Path, location: str):
        calls["skill_name"] = skill_name
        calls["file_path"] = file_path
        calls["skill_root"] = skill_root
        calls["location"] = location
        return {"content": "hello"}

    monkeypatch.setattr(skill_file_routes, "read_skill_file_payload", _read)

    assert skill_file_routes.read_request_skill_file_payload(
        "Search",
        "SKILL.md",
    ) == {"content": "hello"}
    assert calls == {
        "skill_name": "search",
        "file_path": "SKILL.md",
        "skill_root": skill_root,
        "location": "workspace",
    }
