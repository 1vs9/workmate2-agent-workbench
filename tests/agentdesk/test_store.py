# -*- coding: utf-8 -*-
"""Tests for AgentDesk JSON persistence."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from qwenpaw.agentdesk.store import (
    AgentDeskStore,
    _atomic_replace_with_retry,
    format_agentdesk_persistence_error,
    format_agentdesk_stream_error,
)


def test_agentdesk_store_persists_items_by_key(tmp_path):
    store = AgentDeskStore(tmp_path / "store.json")

    created = store.upsert_by_key(
        "knowledge",
        "id",
        "doc-1",
        {"title": "Policy", "content": "Use QwenPaw"},
    )
    updated = store.upsert_by_key(
        "knowledge",
        "id",
        "doc-1",
        {"content": "Use AgentDesk"},
    )

    reloaded = AgentDeskStore(tmp_path / "store.json")
    docs = reloaded.list_items("knowledge")

    assert created["title"] == "Policy"
    assert updated["title"] == "Policy"
    assert updated["content"] == "Use AgentDesk"
    assert docs == [updated]


def test_agentdesk_store_manages_task_messages(tmp_path):
    store = AgentDeskStore(tmp_path / "store.json")

    task = store.ensure_task("task-1", title="Demo task")
    store.append_task_message("task-1", {"role": "user", "content": "hello"})
    store.replace_task_messages(
        "task-1",
        [{"role": "assistant", "content": "hi", "streaming": False}],
    )

    reloaded = AgentDeskStore(tmp_path / "store.json")
    persisted = reloaded.get_by_key("tasks", "id", "task-1")

    assert task["id"] == "task-1"
    assert persisted is not None
    assert persisted["title"] == "Demo task"
    assert persisted["messages"] == [
        {"role": "assistant", "content": "hi", "streaming": False},
    ]


def test_ensure_task_preserves_existing_task_state(tmp_path):
    store = AgentDeskStore(tmp_path / "store.json")
    store.ensure_task("task-1", title="Original")
    store.replace_task_messages("task-1", [{"role": "user", "content": "hello"}])

    task = store.ensure_task("task-1", title="New title")

    assert task["title"] == "Original"
    assert task["messages"] == [{"role": "user", "content": "hello"}]


def test_compact_tasks_archives_cold_payloads(tmp_path):
    store = AgentDeskStore(tmp_path / "store.json")
    now = 1_700_000_000.0
    tasks = []
    for idx in range(65):
        tasks.append(
            {
                "id": f"task-{idx}",
                "title": f"T{idx}",
                "messages": [{"role": "user", "content": f"msg-{idx}"}],
                "events": [],
                "teamTimeline": [],
                "created_at": now + idx,
                "updated_at": now + idx,
            },
        )
    data = store._empty()
    data["tasks"] = tasks
    store.write(data)

    store.ensure_task("task-new", title="fresh")

    with store._exclusive_access():
        raw = store._load_unlocked()
        cold_raw = next(t for t in raw["tasks"] if t.get("id") == "task-0")
        assert cold_raw.get("payloadArchived") is True
        assert cold_raw.get("messages") == []

    hydrated = store.get_by_key("tasks", "id", "task-0")
    assert hydrated is not None
    assert hydrated["messages"] == [{"role": "user", "content": "msg-0"}]
    archive_path = tmp_path / "task_archives" / "task-0.json"
    assert archive_path.is_file()


def test_store_upsert_transactions_preserve_concurrent_writes(tmp_path):
    store = AgentDeskStore(tmp_path / "store.json")

    def write_item(index: int) -> None:
        store.upsert_by_key("knowledge", "id", f"k{index}", {"title": str(index)})

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write_item, range(25)))

    assert len(store.list_items("knowledge")) == 25


def test_atomic_replace_retries_transient_permission_error(tmp_path):
    dst = tmp_path / "store.json"
    src = tmp_path / "store.json.tmp"
    src.write_text("{}", encoding="utf-8")
    attempts = {"count": 0}
    original_replace = Path.replace

    def flaky_replace(self, target):  # noqa: ANN001
        if self == src and target == dst:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise PermissionError(13, "denied")
        return original_replace(self, target)

    with patch.object(Path, "replace", flaky_replace):
        _atomic_replace_with_retry(src, dst)

    assert attempts["count"] == 3
    assert dst.read_text(encoding="utf-8") == "{}"


def test_format_agentdesk_persistence_error_maps_access_denied():
    err = PermissionError(13, "拒绝访问。")
    message = format_agentdesk_persistence_error(err)
    assert message is not None
    assert "QwenPaw" in message


def test_format_agentdesk_stream_error_includes_exception_detail():
    err = AttributeError("'dict' object has no attribute 'task_id'")
    message = format_agentdesk_stream_error(
        err,
        default="团队对话处理失败，请稍后重试。",
    )
    assert "团队对话处理失败" in message
    assert "task_id" in message


def test_separate_store_instances_share_path_safely(tmp_path):
    left = AgentDeskStore(tmp_path / "store.json")
    right = AgentDeskStore(tmp_path / "store.json")

    def write_left(index: int) -> None:
        left.upsert_by_key("knowledge", "id", f"left-{index}", {"title": str(index)})

    def write_right(index: int) -> None:
        right.upsert_by_key("knowledge", "id", f"right-{index}", {"title": str(index)})

    with ThreadPoolExecutor(max_workers=8) as pool:
        pool.map(write_left, range(12))
        pool.map(write_right, range(12))

    reloaded = AgentDeskStore(tmp_path / "store.json")
    assert len(reloaded.list_items("knowledge")) == 24


def test_atomic_replace_raises_after_retry_budget(tmp_path):
    dst = tmp_path / "store.json"
    src = tmp_path / "store.json.tmp"
    src.write_text("{}", encoding="utf-8")

    def always_fail(self, target):  # noqa: ANN001
        raise PermissionError(13, "denied")

    with patch.object(Path, "replace", always_fail):
        with pytest.raises(PermissionError):
            _atomic_replace_with_retry(src, dst)
