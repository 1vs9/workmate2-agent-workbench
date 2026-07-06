# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from qwenpaw.agentdesk import employee_agents, plaza_routes
from qwenpaw.agentdesk.store import AgentDeskStore


def test_create_plaza_payload_requires_name() -> None:
    with pytest.raises(ValueError, match="name is required"):
        plaza_routes.create_plaza_payload({})


def test_create_plaza_payload_persists_avatar_and_invalidates(
    monkeypatch,
    tmp_path,
) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    calls: list[str] = []
    monkeypatch.setattr(plaza_routes, "store", store)
    monkeypatch.setattr(plaza_routes, "invalidate_plaza_orphan_sync", lambda: calls.append("invalidated"))
    monkeypatch.setattr(
        plaza_routes,
        "apply_avatar_on_write",
        lambda payload, *, role: {**payload, "avatar": f"{role}.svg"},
    )

    result = plaza_routes.create_plaza_payload(
        {"name": "Analyst", "description": "整理数据"},
    )

    assert result["name"] == "Analyst"
    assert result["desc"] == "整理数据"
    assert result["tags"] == []
    assert result["avatar"] == "employee.svg"
    assert calls == ["invalidated"]


def test_join_plaza_payload_creates_employee_and_marks_joined(
    monkeypatch,
    tmp_path,
) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(plaza_routes, "store", store)
    monkeypatch.setattr(plaza_routes, "maybe_sync_orphan_plaza", lambda **kwargs: None)
    monkeypatch.setattr(plaza_routes, "maybe_persist_avatar", lambda collection, key, item: item)
    monkeypatch.setattr(
        employee_agents,
        "ensure_employee_agent_profile",
        lambda name: "agent-1",
    )
    monkeypatch.setattr(
        plaza_routes,
        "workspace_skill_state",
        lambda agent_id: {"search": {"enabled": True}},
    )
    monkeypatch.setattr(plaza_routes, "agent_skill_names", lambda agent_id: [])
    store.upsert_by_key(
        "plaza",
        "name",
        "Analyst",
        {
            "name": "Analyst",
            "desc": "整理数据",
            "skills": ["search", "write"],
            "mcp": ["fs"],
        },
    )

    result = plaza_routes.join_plaza_payload("Analyst")

    assert result["joined"] is True
    assert result["agent_id"] == "agent-1"
    assert result["requested_skills"] == ["search", "write"]
    assert result["mounted_skills"] == ["search"]
    assert result["failed_skills"] == ["write"]
    assert store.get_by_key("employees", "name", "Analyst")["skills"] == [
        "search",
        "write",
    ]
    assert store.get_by_key("plaza", "name", "Analyst")["joined"] is True


def test_update_plaza_payload_syncs_employee_and_agent(monkeypatch, tmp_path) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    calls: dict[str, str] = {}
    monkeypatch.setattr(plaza_routes, "store", store)
    monkeypatch.setattr(plaza_routes, "invalidate_plaza_orphan_sync", lambda: calls.setdefault("invalidated", "yes"))
    monkeypatch.setattr(
        plaza_routes,
        "sync_employee_agent_skills",
        lambda name: calls.setdefault("synced", name),
    )
    store.upsert_by_key(
        "employees",
        "name",
        "Analyst",
        {"name": "Analyst", "desc": "Old"},
    )

    result = plaza_routes.update_plaza_payload(
        "Analyst",
        {"desc": "New", "skills": ["search"]},
    )

    assert result["desc"] == "New"
    employee = store.get_by_key("employees", "name", "Analyst")
    assert employee["desc"] == "New"
    assert employee["skills"] == ["search"]
    assert calls == {"invalidated": "yes", "synced": "Analyst"}


def test_delete_plaza_payload_missing_raises_lookup(monkeypatch) -> None:
    monkeypatch.setattr(employee_agents, "delete_employee_agent", lambda name: False)

    with pytest.raises(LookupError, match="Plaza item 'Analyst' not found"):
        plaza_routes.delete_plaza_payload("Analyst")
