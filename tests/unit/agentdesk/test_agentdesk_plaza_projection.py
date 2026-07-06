# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from qwenpaw.agentdesk import plaza_projection


class _FakeStore:
    def __init__(self, employees: list[dict[str, object]]) -> None:
        self.employees = employees

    def list_items(self, collection: str) -> list[dict[str, object]]:
        return self.employees if collection == "employees" else []

    def get_by_key(
        self,
        collection: str,
        key: str,
        value: str,
    ) -> dict[str, object] | None:
        for item in self.list_items(collection):
            if item.get(key) == value:
                return item
        return None


def test_coalesce_desc_joins_unique_alias_values() -> None:
    payload = plaza_projection.coalesce_desc(
        {
            "description": "A",
            "prompt": "A",
            "persona": "B",
        },
    )

    assert payload["desc"] == "A\n\nB"


def test_coalesce_desc_keeps_existing_desc() -> None:
    payload = {"desc": "Existing", "description": "Ignored"}

    assert plaza_projection.coalesce_desc(payload) is payload


def test_enrich_plaza_card_backfills_from_employee_agent(monkeypatch) -> None:
    monkeypatch.setattr(
        plaza_projection,
        "store",
        _FakeStore([{"name": "Writer", "agent_id": "agent-1"}]),
    )
    monkeypatch.setattr(
        plaza_projection,
        "agent_desc_and_skills",
        lambda agent_id: ("Agent desc", ["search"]),
    )

    enriched = plaza_projection.enrich_plaza_card(
        {"name": "Writer"},
        profiles={},
        load_profiles=lambda: {},
        match_agent_id_by_display_name=lambda name, profiles, name_index: None,
    )

    assert enriched["desc"] == "Agent desc"
    assert enriched["skills"] == ["search"]


def test_enrich_plaza_card_uses_profile_match_when_employee_missing(monkeypatch) -> None:
    monkeypatch.setattr(plaza_projection, "store", _FakeStore([]))
    monkeypatch.setattr(
        plaza_projection,
        "agent_desc_and_skills",
        lambda agent_id: ("Matched desc", ["write"]),
    )

    enriched = plaza_projection.enrich_plaza_card(
        {"name": "Writer"},
        profiles={"agent-1": object()},
        load_profiles=lambda: {},
        match_agent_id_by_display_name=(
            lambda name, profiles, name_index: "agent-1"
        ),
    )

    assert enriched["desc"] == "Matched desc"
    assert enriched["skills"] == ["write"]


def test_configured_employees_dedupes_and_enriches(monkeypatch) -> None:
    monkeypatch.setattr(
        plaza_projection,
        "store",
        _FakeStore(
            [
                {"name": "Writer", "agent_id": "agent-1", "tools": ["t"]},
                {"name": "Writer", "agent_id": "agent-duplicate"},
                {"name": ""},
            ],
        ),
    )
    monkeypatch.setattr(
        plaza_projection,
        "agent_desc_and_skills",
        lambda agent_id: ("Agent desc", ["search"]),
    )
    profiles = {
        "agent-1": SimpleNamespace(workspace_dir="workspace", enabled=False),
    }

    employees = plaza_projection.configured_employees(
        profiles=profiles,
        name_index={},
        match_agent_id_by_display_name=lambda name, profiles, name_index: None,
    )

    assert employees == [
        {
            "name": "Writer",
            "id": "agent-1",
            "agent_id": "agent-1",
            "desc": "Agent desc",
            "tools": ["t"],
            "skills": ["search"],
            "mcp": [],
            "avatar": None,
            "workspace_dir": "workspace",
            "enabled": False,
        },
    ]


def test_configured_employees_matches_display_name(monkeypatch) -> None:
    monkeypatch.setattr(
        plaza_projection,
        "store",
        _FakeStore([{"name": "Writer"}]),
    )
    monkeypatch.setattr(
        plaza_projection,
        "agent_desc_and_skills",
        lambda agent_id: ("", []),
    )

    employees = plaza_projection.configured_employees(
        profiles={"agent-1": SimpleNamespace(workspace_dir="", enabled=True)},
        name_index={},
        match_agent_id_by_display_name=lambda name, profiles, name_index: "agent-1",
    )

    assert employees[0]["id"] == "agent-1"
    assert employees[0]["agent_id"] == "agent-1"
