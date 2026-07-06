# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.agentdesk.store import AgentDeskStore
from qwenpaw.agentdesk.task_transcript_cache import TaskTranscriptCache


async def test_task_transcript_cache_replaces_messages_with_copy(tmp_path) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    cache = TaskTranscriptCache(store)
    await cache.ensure_task("task-1", title="Task 1")
    messages = [
        {
            "role": "assistant",
            "content": "hello",
            "artifacts": [{"path": "a.txt"}],
        },
    ]

    await cache.replace_messages("task-1", messages)
    messages[0]["content"] = "mutated"
    messages[0]["artifacts"][0]["path"] = "mutated.txt"

    task = await cache.load_task("task-1")
    assert task is not None
    assert task["messages"][0]["content"] == "hello"
    assert task["messages"][0]["artifacts"][0]["path"] == "a.txt"


async def test_task_transcript_cache_replaces_team_timeline(tmp_path) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    cache = TaskTranscriptCache(store)
    timeline = [{"kind": "phase", "label": "planning"}]

    await cache.replace_team_timeline("task-1", timeline)
    timeline[0]["label"] = "mutated"

    assert await cache.get_team_timeline("task-1") == [
        {"kind": "phase", "label": "planning"},
    ]
