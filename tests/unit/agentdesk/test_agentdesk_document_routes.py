# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from qwenpaw.agentdesk import document_records, document_routes
from qwenpaw.agentdesk.store import AgentDeskStore


@pytest.fixture()
def route_store(tmp_path, monkeypatch) -> AgentDeskStore:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(document_records, "store", store)
    monkeypatch.setattr(document_routes, "store", store)
    return store


def test_list_document_payloads_returns_collection_items(route_store) -> None:
    route_store.upsert_by_key(
        "knowledge",
        "id",
        "doc-1",
        {"id": "doc-1", "title": "Doc"},
    )

    listed = document_routes.list_document_payloads("knowledge")

    assert len(listed) == 1
    assert listed[0]["id"] == "doc-1"
    assert listed[0]["title"] == "Doc"


def test_create_document_payload_delegates_to_document_record(route_store) -> None:
    created = document_routes.create_document_payload(
        "cases",
        {"id": "case-1", "name": "Case Alpha"},
    )

    assert created["id"] == "case-1"
    assert created["title"] == "Case Alpha"
    assert route_store.get_by_key("cases", "id", "case-1") == created


def test_update_document_payload_preserves_missing_as_lookup_error(route_store) -> None:
    with pytest.raises(LookupError, match="Not found"):
        document_routes.update_document_payload(
            "knowledge",
            "missing",
            {"title": "New"},
        )


def test_delete_document_payload_returns_deleted_flag(route_store) -> None:
    route_store.upsert_by_key(
        "cases",
        "id",
        "case-1",
        {"id": "case-1", "title": "Case"},
    )

    assert document_routes.delete_document_payload("cases", "case-1") == {
        "deleted": True,
        "id": "case-1",
    }
    assert route_store.get_by_key("cases", "id", "case-1") is None
