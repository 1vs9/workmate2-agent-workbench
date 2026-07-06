# -*- coding: utf-8 -*-
"""AgentDesk knowledge/case endpoint orchestration helpers."""

from __future__ import annotations

from typing import Any

from .document_records import (
    create_document,
    update_document,
)
from .store import store


def list_document_payloads(collection: str) -> list[dict[str, Any]]:
    return store.list_items(collection)


def create_document_payload(
    collection: str,
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    return create_document(collection, dict(body or {}))


def update_document_payload(
    collection: str,
    item_id: str,
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    return update_document(collection, item_id, dict(body or {}))


def delete_document_payload(collection: str, item_id: str) -> dict[str, Any]:
    return {
        "deleted": store.delete_by_key(collection, "id", item_id),
        "id": item_id,
    }
