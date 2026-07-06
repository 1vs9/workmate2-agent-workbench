# -*- coding: utf-8 -*-
"""AgentDesk record avatar enrichment helpers."""

from __future__ import annotations

from typing import Any

from .avatars import ensure_record_avatar
from .store import store


def avatar_role_for_collection(collection: str) -> str:
    return "team" if collection == "teams" else "employee"


def maybe_persist_avatar(
    collection: str,
    key_field: str,
    record: dict[str, Any],
    *,
    persist: bool = True,
) -> dict[str, Any]:
    role = avatar_role_for_collection(collection)
    enriched, changed = ensure_record_avatar(record, role=role)
    if persist and changed:
        key_val = str(enriched.get(key_field) or "").strip()
        if key_val:
            store.upsert_by_key(collection, key_field, key_val, enriched)
    return enriched


def enrich_avatar(record: dict[str, Any], *, role: str) -> dict[str, Any]:
    from .avatars import enrich_record_avatar_lazy

    return enrich_record_avatar_lazy(record, role=role)


def apply_avatar_on_write(payload: dict[str, Any], *, role: str) -> dict[str, Any]:
    enriched, _ = ensure_record_avatar(payload, role=role)
    return enriched
