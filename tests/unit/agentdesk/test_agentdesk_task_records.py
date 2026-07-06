# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from qwenpaw.agentdesk import task_records
from qwenpaw.agentdesk.store import AgentDeskStore


def test_create_task_record_rejects_client_workspace_dir(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(task_records, "store", store)

    with pytest.raises(task_records.ClientManagedTaskFieldError):
        task_records.create_task_record(
            {"id": "task-1", "title": "Task", "workspace_dir": str(tmp_path)},
        )

    assert store.get_by_key("tasks", "id", "task-1") is None


def test_create_task_record_uses_default_title(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(task_records, "store", store)

    task = task_records.create_task_record({"id": "task-1", "title": ""})

    assert task["id"] == "task-1"
    assert task["title"] == "New Task"
    assert task["messages"] == []


def test_task_patch_from_payload_accepts_only_user_editable_fields() -> None:
    assert task_records.task_patch_from_payload(
        {
            "title": "",
            "pinned": 1,
            "workspace_dir": "/tmp/ignored",
            "messages": [{"role": "user"}],
        },
    ) == {"title": "New Task", "pinned": True}


def test_update_task_record_returns_existing_for_empty_patch(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(task_records, "store", store)
    existing = store.ensure_task("task-1", title="Old")

    updated = task_records.update_task_record("task-1", {"workspace_dir": "/ignored"})

    assert updated == existing


def test_update_task_record_patches_title_and_pinned(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(task_records, "store", store)
    store.ensure_task("task-1", title="Old")

    updated = task_records.update_task_record(
        "task-1",
        {"title": "New", "pinned": True},
    )

    assert updated["title"] == "New"
    assert updated["pinned"] is True


def test_update_task_record_raises_for_missing_task(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(task_records, "store", store)

    with pytest.raises(LookupError, match="Task not found"):
        task_records.update_task_record("missing", {"title": "New"})


def test_attach_skill_to_task_record_creates_task_and_dedupes(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(task_records, "store", store)

    task_records.attach_skill_to_task_record("task-1", "search")
    updated = task_records.attach_skill_to_task_record("task-1", "search")
    updated = task_records.attach_skill_to_task_record("task-1", "docx")

    assert updated["skill_names"] == ["search", "docx"]
    assert store.get_by_key("tasks", "id", "task-1")["skill_names"] == [
        "search",
        "docx",
    ]


def test_attach_skill_to_task_record_requires_task_and_skill() -> None:
    with pytest.raises(ValueError, match="task_id and skill_name are required"):
        task_records.attach_skill_to_task_record("", "search")

    with pytest.raises(ValueError, match="task_id and skill_name are required"):
        task_records.attach_skill_to_task_record("task-1", " ")
