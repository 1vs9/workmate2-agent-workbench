# -*- coding: utf-8 -*-
"""Shared record helpers for AgentDesk knowledge/case documents."""

from __future__ import annotations

import uuid
from typing import Any

from .store import store


def create_document(collection: str, body: dict[str, Any] | None) -> dict[str, Any]:
    """Create a knowledge/case document with AgentDesk-compatible defaults."""
    payload = dict(body or {})
    item_id = str(payload.get("id") or uuid.uuid4().hex)
    payload.setdefault("title", payload.get("name") or "Untitled")
    payload.setdefault("tags", [])
    return store.upsert_by_key(collection, "id", item_id, payload)


def update_document(
    collection: str,
    item_id: str,
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    """Patch a knowledge/case document, raising LookupError when missing."""
    existing = store.get_by_key(collection, "id", item_id)
    if existing is None:
        raise LookupError("Not found")
    return store.upsert_by_key(
        collection,
        "id",
        item_id,
        {**existing, **dict(body or {})},
    )
