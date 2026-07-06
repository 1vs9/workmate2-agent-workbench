# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from qwenpaw.agentdesk import skill_records


class _FakeStore:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, str, str, dict[str, object]]] = []

    def upsert_by_key(
        self,
        collection: str,
        key: str,
        value: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        self.upserts.append((collection, key, value, payload))
        return payload


class _FakePool:
    def __init__(self, created_name: str | None = "Created") -> None:
        self.created_name = created_name
        self.calls: list[dict[str, object]] = []

    def create_skill(self, **kwargs):
        self.calls.append(kwargs)
        return self.created_name


def test_import_builtin_skill_records_requires_skill_names() -> None:
    with pytest.raises(
        skill_records.InvalidSkillPayloadError,
        match="skill_names is required",
    ):
        skill_records.import_builtin_skill_records({"skill_names": []})


def test_import_builtin_skill_records_strips_blank_names(monkeypatch) -> None:
    imported: list[list[dict[str, str]]] = []
    monkeypatch.setattr(
        skill_records,
        "import_builtin_skills",
        lambda items: imported.append(items) or {"ok": True},
    )

    result = skill_records.import_builtin_skill_records(
        {"skill_names": [" Search ", "", "Write"]},
    )

    assert result == {"ok": True}
    assert imported == [[{"skill_name": "Search"}, {"skill_name": "Write"}]]


def test_create_skill_record_requires_name() -> None:
    with pytest.raises(skill_records.InvalidSkillPayloadError, match="name is required"):
        skill_records.create_skill_record({"body": "Body"})


def test_create_skill_record_raises_when_pool_reports_duplicate(monkeypatch) -> None:
    monkeypatch.setattr(skill_records, "validate_skill_content", lambda content: None)
    monkeypatch.setattr(
        skill_records,
        "skill_content_from_payload",
        lambda payload: "Rendered body",
    )
    monkeypatch.setattr(skill_records, "SkillPoolService", lambda: _FakePool(None))

    with pytest.raises(skill_records.SkillAlreadyExistsError):
        skill_records.create_skill_record({"name": "Search"})


def test_create_skill_record_returns_catalog_item_and_persists_store(monkeypatch) -> None:
    store = _FakeStore()
    pool = _FakePool("Search")
    monkeypatch.setattr(skill_records, "store", store)
    monkeypatch.setattr(skill_records, "SkillPoolService", lambda: pool)
    monkeypatch.setattr(skill_records, "validate_skill_content", lambda content: None)
    monkeypatch.setattr(
        skill_records,
        "skill_content_from_payload",
        lambda payload: "Rendered body",
    )
    monkeypatch.setattr(
        skill_records,
        "serialize_pool_skills",
        lambda: [
            {
                "name": "Search",
                "description": "Catalog desc",
                "body": "Catalog body",
                "source": "agentdesk",
            },
        ],
    )

    created = skill_records.create_skill_record(
        {"name": "Search", "description": "Payload desc", "config": {"a": 1}},
    )

    assert created == {
        "name": "Search",
        "description": "Catalog desc",
        "body": "Catalog body",
        "source": "agentdesk",
    }
    assert pool.calls == [
        {
            "name": "Search",
            "content": "Rendered body",
            "config": {"a": 1},
            "installed_from": "agentdesk",
        },
    ]
    assert store.upserts == [
        (
            "skills",
            "name",
            "Search",
            {
                "name": "Search",
                "description": "Catalog desc",
                "body": "Catalog body",
                "source": "agentdesk",
            },
        ),
    ]


def test_create_skill_record_falls_back_when_catalog_item_missing(monkeypatch) -> None:
    store = _FakeStore()
    monkeypatch.setattr(skill_records, "store", store)
    monkeypatch.setattr(skill_records, "SkillPoolService", lambda: _FakePool("Search"))
    monkeypatch.setattr(skill_records, "validate_skill_content", lambda content: None)
    monkeypatch.setattr(
        skill_records,
        "skill_content_from_payload",
        lambda payload: "Rendered body",
    )
    monkeypatch.setattr(skill_records, "serialize_pool_skills", lambda: [])

    created = skill_records.create_skill_record(
        {"name": "Search", "description": "Payload desc"},
    )

    assert created == {
        "name": "Search",
        "description": "Payload desc",
        "body": "Rendered body",
    }
    assert store.upserts[0][3]["body"] == "Rendered body"
