# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.agentdesk import record_avatars


class _FakeStore:
    def __init__(self) -> None:
        self.upserts: list[tuple[str, str, str, dict[str, object]]] = []

    def upsert_by_key(
        self,
        collection: str,
        key_field: str,
        key_val: str,
        record: dict[str, object],
    ) -> dict[str, object]:
        self.upserts.append((collection, key_field, key_val, record))
        return record


def test_avatar_role_for_collection_maps_teams_to_team() -> None:
    assert record_avatars.avatar_role_for_collection("teams") == "team"
    assert record_avatars.avatar_role_for_collection("employees") == "employee"


def test_maybe_persist_avatar_upserts_when_changed(monkeypatch) -> None:
    fake_store = _FakeStore()
    monkeypatch.setattr(record_avatars, "store", fake_store)
    monkeypatch.setattr(
        record_avatars,
        "ensure_record_avatar",
        lambda record, *, role: ({**record, "avatar": f"{role}-avatar"}, True),
    )

    enriched = record_avatars.maybe_persist_avatar(
        "teams",
        "id",
        {"id": "team-1"},
    )

    assert enriched == {"id": "team-1", "avatar": "team-avatar"}
    assert fake_store.upserts == [
        ("teams", "id", "team-1", {"id": "team-1", "avatar": "team-avatar"}),
    ]


def test_maybe_persist_avatar_skips_persist_when_unchanged(monkeypatch) -> None:
    fake_store = _FakeStore()
    monkeypatch.setattr(record_avatars, "store", fake_store)
    monkeypatch.setattr(
        record_avatars,
        "ensure_record_avatar",
        lambda record, *, role: (record, False),
    )

    assert record_avatars.maybe_persist_avatar(
        "employees",
        "name",
        {"name": "Writer"},
    ) == {"name": "Writer"}
    assert fake_store.upserts == []


def test_maybe_persist_avatar_respects_persist_false(monkeypatch) -> None:
    fake_store = _FakeStore()
    monkeypatch.setattr(record_avatars, "store", fake_store)
    monkeypatch.setattr(
        record_avatars,
        "ensure_record_avatar",
        lambda record, *, role: ({**record, "avatar": "avatar"}, True),
    )

    record_avatars.maybe_persist_avatar(
        "employees",
        "name",
        {"name": "Writer"},
        persist=False,
    )

    assert fake_store.upserts == []


def test_apply_avatar_on_write_returns_enriched_without_persisting(monkeypatch) -> None:
    monkeypatch.setattr(
        record_avatars,
        "ensure_record_avatar",
        lambda record, *, role: ({**record, "avatar": f"{role}-avatar"}, True),
    )

    assert record_avatars.apply_avatar_on_write({"id": "team-1"}, role="team") == {
        "id": "team-1",
        "avatar": "team-avatar",
    }
