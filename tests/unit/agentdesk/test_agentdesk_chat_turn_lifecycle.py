# -*- coding: utf-8 -*-
from __future__ import annotations

import qwenpaw.agentdesk.chat_turn_lifecycle as chat_turn_lifecycle
from qwenpaw.agentdesk import run_status
from qwenpaw.agentdesk.store import AgentDeskStore
from qwenpaw.agentdesk.task_store import TaskStore


def _patch_lifecycle_stores(monkeypatch, store: AgentDeskStore) -> TaskStore:
    task_store = TaskStore(persistent_store=store)
    monkeypatch.setattr(chat_turn_lifecycle, "task_store", task_store)
    monkeypatch.setattr(
        chat_turn_lifecycle,
        "commit_task_run_status",
        lambda task_id, status: run_status.commit_task_run_status(
            task_id,
            status,
            persistent_store=store,
        ),
    )
    return task_store


async def test_finalize_failed_turn_creates_and_closes_pre_stream_message(
    tmp_path,
    monkeypatch,
) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = _patch_lifecycle_stores(monkeypatch, store)

    await chat_turn_lifecycle.finalize_failed_turn(
        "task-1",
        sender="Analyst",
        content="failed",
        stream_turn_started=False,
    )

    messages = await task_store.get_messages("task-1")
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["sender"] == "Analyst"
    assert messages[-1]["content"] == "failed"
    assert run_status.task_run_status("task-1", persistent_store=store) == "idle"


async def test_finalize_failed_turn_closes_existing_stream_message(
    tmp_path,
    monkeypatch,
) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = _patch_lifecycle_stores(monkeypatch, store)
    await task_store.begin_assistant_message("task-2", sender="Bot")

    await chat_turn_lifecycle.finalize_failed_turn(
        "task-2",
        sender="Ignored",
        content="mid-stream failure",
        stream_turn_started=True,
    )

    messages = await task_store.get_messages("task-2")
    assert len(messages) == 1
    assert messages[0]["sender"] == "Bot"
    assert messages[0]["content"] == "mid-stream failure"
    assert run_status.task_run_status("task-2", persistent_store=store) == "idle"
