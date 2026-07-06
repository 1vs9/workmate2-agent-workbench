# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from fastapi import HTTPException

from qwenpaw.agentdesk import employee_agents, employee_routes
from qwenpaw.agentdesk.store import AgentDeskStore


def test_create_employee_payload_requires_name() -> None:
    with pytest.raises(ValueError, match="name is required"):
        employee_routes.create_employee_payload({})


def test_create_employee_payload_persists_normalized_record(
    monkeypatch,
    tmp_path,
) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(employee_routes, "store", store)
    monkeypatch.setattr(
        employee_routes,
        "apply_avatar_on_write",
        lambda payload, *, role: {**payload, "avatar": f"{role}.svg"},
    )

    result = employee_routes.create_employee_payload(
        {"name": "Analyst", "description": "Reads filings"},
    )

    assert result["name"] == "Analyst"
    assert result["desc"] == "Reads filings"
    assert result["avatar"] == "employee.svg"
    assert store.get_by_key("employees", "name", "Analyst")["desc"] == "Reads filings"


def test_mount_employee_requested_skills_reports_mounted_and_failed(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        employee_routes,
        "resolve_employee_mount_skill_name",
        lambda agent_id, skill_name: f"pool-{skill_name}",
    )
    monkeypatch.setattr(
        employee_routes,
        "resolve_workspace_skill_name",
        lambda agent_id, mount_name: mount_name if mount_name == "pool-existing" else None,
    )
    monkeypatch.setattr(
        employee_routes,
        "ensure_skill_in_pool_for_mount",
        lambda mount_name, agent_id: mount_name,
    )

    def _mount(*, skill_name: str, agent_id: str):
        calls.append((skill_name, agent_id))
        if skill_name == "pool-missing":
            raise HTTPException(status_code=404, detail="missing")
        return {"mounted": True}

    monkeypatch.setattr(employee_routes, "ensure_skill_mounted", _mount)

    mounted, failed = employee_routes.mount_employee_requested_skills(
        "agent-1",
        [" existing ", "missing", ""],
    )

    assert mounted == ["existing"]
    assert failed == ["missing"]
    assert calls == [("pool-missing", "agent-1")]


def test_update_employee_payload_syncs_plaza_and_mounts_skills(
    monkeypatch,
    tmp_path,
) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    calls: dict[str, object] = {}
    monkeypatch.setattr(employee_routes, "store", store)
    monkeypatch.setattr(
        employee_agents,
        "invalidate_employee_sync_cache_for_name",
        lambda name: calls.setdefault("invalidated", name),
    )
    monkeypatch.setattr(
        employee_routes,
        "sync_employee_agent_skills",
        lambda name: calls.setdefault("synced", name),
    )
    monkeypatch.setattr(
        employee_routes,
        "resolve_agentdesk_agent_id",
        lambda name: "agent-1",
    )
    monkeypatch.setattr(
        employee_routes,
        "mount_employee_requested_skills",
        lambda agent_id, skills: (["search"], ["write"]),
    )
    store.upsert_by_key(
        "plaza",
        "name",
        "Analyst",
        {"name": "Analyst", "desc": "Old", "tags": ["QwenPaw"]},
    )

    result = employee_routes.update_employee_payload(
        "Analyst",
        {"desc": "New", "skills": ["search", "write"]},
    )

    assert result["requested_skills"] == ["search", "write"]
    assert result["mounted_skills"] == ["search"]
    assert result["failed_skills"] == ["write"]
    assert calls["invalidated"] == "Analyst"
    assert calls["synced"] == "Analyst"
    plaza = store.get_by_key("plaza", "name", "Analyst")
    assert plaza["desc"] == "New"
    assert plaza["skills"] == ["search", "write"]


def test_delete_employee_payload_missing_raises_lookup(monkeypatch) -> None:
    monkeypatch.setattr(employee_agents, "delete_employee_agent", lambda name: False)

    with pytest.raises(LookupError, match="Employee 'Analyst' not found"):
        employee_routes.delete_employee_payload("Analyst")
