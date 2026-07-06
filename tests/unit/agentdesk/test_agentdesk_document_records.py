# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from qwenpaw.agentdesk import document_records
from qwenpaw.agentdesk.store import AgentDeskStore


def test_create_document_adds_defaults(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(document_records, "store", store)

    created = document_records.create_document(
        "knowledge",
        {"id": "doc-1", "body": "Body"},
    )

    assert created["id"] == "doc-1"
    assert created["body"] == "Body"
    assert created["title"] == "Untitled"
    assert created["tags"] == []
    assert store.get_by_key("knowledge", "id", "doc-1") == created


def test_create_document_uses_name_as_default_title(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(document_records, "store", store)

    created = document_records.create_document(
        "cases",
        {"id": "case-1", "name": "Case Alpha"},
    )

    assert created["title"] == "Case Alpha"
    assert created["tags"] == []


def test_update_document_merges_existing_record(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(document_records, "store", store)
    store.upsert_by_key(
        "knowledge",
        "id",
        "doc-1",
        {"id": "doc-1", "title": "Old", "tags": ["a"], "body": "Old body"},
    )

    updated = document_records.update_document(
        "knowledge",
        "doc-1",
        {"title": "New"},
    )

    assert updated["id"] == "doc-1"
    assert updated["title"] == "New"
    assert updated["tags"] == ["a"]
    assert updated["body"] == "Old body"


def test_update_document_raises_for_missing_record(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(document_records, "store", store)

    with pytest.raises(LookupError, match="Not found"):
        document_records.update_document("knowledge", "missing", {"title": "New"})
