# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.agentdesk import skill_management_routes


def test_list_skill_payloads_uses_catalog(monkeypatch) -> None:
    monkeypatch.setattr(
        skill_management_routes,
        "serialize_pool_skills",
        lambda: [{"name": "Search"}],
    )

    assert skill_management_routes.list_skill_payloads() == [{"name": "Search"}]


def test_import_builtin_skill_payload_normalizes_empty_body(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        skill_management_routes,
        "import_builtin_skill_records",
        lambda body: calls.append(body) or {"ok": True},
    )

    assert skill_management_routes.import_builtin_skill_payload(None) == {"ok": True}
    assert calls == [{}]


def test_create_skill_payload_normalizes_body(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        skill_management_routes,
        "create_skill_record",
        lambda body: calls.append(body) or {"name": body["name"]},
    )

    assert skill_management_routes.create_skill_payload({"name": "Search"}) == {
        "name": "Search",
    }
    assert calls == [{"name": "Search"}]


def test_delete_skill_payload_deletes_pool_or_store(monkeypatch) -> None:
    deleted: list[tuple[str, str, str]] = []

    class Pool:
        def delete_skill(self, skill_name: str) -> bool:
            deleted.append(("pool", "name", skill_name))
            return False

    class Store:
        def delete_by_key(self, collection: str, key: str, value: str) -> bool:
            deleted.append((collection, key, value))
            return True

    monkeypatch.setattr(skill_management_routes, "SkillPoolService", lambda: Pool())
    monkeypatch.setattr(skill_management_routes, "store", Store())

    assert skill_management_routes.delete_skill_payload("Search") == {
        "deleted": True,
        "name": "Search",
    }
    assert deleted == [
        ("pool", "name", "Search"),
        ("skills", "name", "Search"),
    ]
