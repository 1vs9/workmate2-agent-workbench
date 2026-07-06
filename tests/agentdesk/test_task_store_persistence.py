# -*- coding: utf-8 -*-
"""Tests for persisted AgentDesk chat task history."""

import asyncio

import pytest

from qwenpaw.agentdesk.store import AgentDeskStore
from qwenpaw.agentdesk.task_store import TaskStore, _STREAM_PERSIST_DEBOUNCE_S, _TIMELINE_PERSIST_DEBOUNCE_S
from qwenpaw.agentdesk.team_chat import _team_member_session_id


@pytest.mark.asyncio
async def test_task_store_mirrors_messages_to_json_store(tmp_path):
    persistent_store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=persistent_store)

    await task_store.ensure_task("task-1", title="Persist me")
    await task_store.append_user_message("task-1", "hello")
    await task_store.begin_assistant_message("task-1", sender="bot")
    await task_store.append_assistant_delta("task-1", "hi")
    await task_store.finalize_assistant_message("task-1")

    reloaded = AgentDeskStore(tmp_path / "store.json")
    task = reloaded.get_by_key("tasks", "id", "task-1")

    assert task is not None
    assert task["title"] == "Persist me"
    assert [message["role"] for message in task["messages"]] == ["user", "assistant"]
    assert task["messages"][0]["content"] == "hello"
    assert task["messages"][1]["content"] == "hi"


@pytest.mark.asyncio
async def test_append_assistant_delta_debounces_disk_writes(tmp_path):
    persistent_store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=persistent_store)
    write_count = 0
    original_replace = persistent_store.replace_task_messages

    def counting_replace(task_id: str, messages: list) -> None:
        nonlocal write_count
        write_count += 1
        original_replace(task_id, messages)

    persistent_store.replace_task_messages = counting_replace  # type: ignore[method-assign]

    await task_store.ensure_task("task-1")
    await task_store.begin_assistant_message("task-1", sender="bot")
    writes_after_begin = write_count

    for _ in range(12):
        await task_store.append_assistant_delta("task-1", "a")

    assert write_count == writes_after_begin

    await asyncio.sleep(_STREAM_PERSIST_DEBOUNCE_S + 0.1)
    assert write_count == writes_after_begin + 1

    await task_store.finalize_assistant_message("task-1")
    assert write_count == writes_after_begin + 2

    task = persistent_store.get_by_key("tasks", "id", "task-1")
    assert task is not None
    assert task["messages"][-1]["content"] == "a" * 12


@pytest.mark.asyncio
async def test_task_store_get_messages_strips_skill_injection_for_user_turns(tmp_path):
    persistent_store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=persistent_store)
    augmented = (
        "Use the [xiaobei-ppt-style] skill in `/tmp/skills/xiaobei-ppt-style` to fulfill "
        "the user's task: 创建一个ai科普的ppt\n\nFollow red theme.\n"
    )

    await task_store.ensure_task("task-1")
    await task_store.append_user_message("task-1", augmented)
    await asyncio.sleep(_STREAM_PERSIST_DEBOUNCE_S + 0.1)

    stored = persistent_store.get_by_key("tasks", "id", "task-1")
    assert stored["messages"][0]["content"] == augmented

    client_messages = await task_store.get_messages("task-1")
    assert client_messages[0]["content"] == "创建一个ai科普的ppt"


@pytest.mark.asyncio
async def test_finalize_after_early_finalize_keeps_longer_content(tmp_path):
    """Race: run watcher finalizes before SSE consumer drains the queue."""
    persistent_store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=persistent_store)

    await task_store.ensure_task("task-1")
    await task_store.begin_assistant_message("task-1", sender="bot")
    await task_store.append_assistant_delta("task-1", "## 3. 人工智能简史\n- 大模型")
    await task_store.finalize_assistant_message("task-1")

    await task_store.append_assistant_delta("task-1", "时代\n- 更多内容")
    full = "## 3. 人工智能简史\n- 大模型时代\n- 更多内容"
    await task_store.finalize_assistant_message("task-1", content=full)

    messages = await task_store.get_messages("task-1")
    assert messages[-1]["content"] == full
    assert messages[-1]["streaming"] is False


@pytest.mark.asyncio
async def test_ensure_task_restores_streaming_pointer_from_disk(tmp_path):
    persistent_store = AgentDeskStore(tmp_path / "store.json")
    writer = TaskStore(persistent_store=persistent_store)
    await writer.ensure_task("task-1")
    await writer.begin_assistant_message("task-1", sender="bot")
    await writer.append_assistant_delta("task-1", "generating slides")
    await asyncio.sleep(_STREAM_PERSIST_DEBOUNCE_S + 0.1)
    task = persistent_store.get_by_key("tasks", "id", "task-1")
    assert task is not None
    assert task["messages"][-1]["streaming"] is True

    reloaded = TaskStore(persistent_store=persistent_store)
    await reloaded.ensure_task("task-1")
    message_id = await reloaded.current_assistant_message_id("task-1")
    assert message_id == task["messages"][-1]["id"]


@pytest.mark.asyncio
async def test_resume_streaming_assistant_reopens_tail_message(tmp_path):
    persistent_store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=persistent_store)

    await task_store.ensure_task("task-1")
    await task_store.begin_assistant_message("task-1", sender="bot")
    await task_store.append_assistant_delta("task-1", "batch 1 done")
    await task_store.finalize_assistant_message("task-1")

    resumed = await task_store.resume_streaming_assistant("task-1")
    assert resumed is not None
    assert resumed["streaming"] is True
    assert await task_store.current_assistant_message_id("task-1") == resumed["id"]

    stored = persistent_store.get_by_key("tasks", "id", "task-1")
    assert stored["messages"][-1]["streaming"] is True


@pytest.mark.asyncio
async def test_parallel_worker_messages_route_by_message_id(tmp_path):
    """Parallel delegated workers each persist to their OWN bubble."""
    persistent_store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=persistent_store)

    await task_store.ensure_task("task-1")
    # Leader owns the streaming pointer.
    leader = await task_store.begin_assistant_message("task-1", sender="组长·leader")
    await task_store.append_assistant_delta("task-1", "我来安排")

    # Four workers begin detached bubbles (no streaming-pointer hijack).
    writer = await task_store.begin_assistant_message(
        "task-1", sender="主笔", set_streaming=False,
    )
    researcher = await task_store.begin_assistant_message(
        "task-1", sender="研究员", set_streaming=False,
    )
    planner = await task_store.begin_assistant_message(
        "task-1", sender="规划者", set_streaming=False,
    )
    critic = await task_store.begin_assistant_message(
        "task-1", sender="审查官", set_streaming=False,
    )

    # Replies arrive interleaved; each must land on its own message.
    await task_store.append_assistant_delta(
        "task-1", "我是审查官", message_id=critic["id"],
    )
    await task_store.append_assistant_delta(
        "task-1", "我是主笔", message_id=writer["id"],
    )
    await task_store.append_assistant_delta(
        "task-1", "我是研究员", message_id=researcher["id"],
    )
    await task_store.append_assistant_delta(
        "task-1", "我是规划者", message_id=planner["id"],
    )

    # Leader posts a summary AFTER workers — must stay on the leader bubble.
    await task_store.append_assistant_delta("task-1", "，大家都已就位")

    for mid in (writer["id"], researcher["id"], planner["id"], critic["id"]):
        await task_store.finalize_assistant_message("task-1", message_id=mid)
    await task_store.finalize_assistant_message("task-1")

    messages = await task_store.get_messages("task-1")
    by_sender = {m["sender"]: m["content"] for m in messages}
    assert by_sender["组长·leader"] == "我来安排，大家都已就位"
    assert by_sender["主笔"] == "我是主笔"
    assert by_sender["研究员"] == "我是研究员"
    assert by_sender["规划者"] == "我是规划者"
    assert by_sender["审查官"] == "我是审查官"
    assert all(m["streaming"] is False for m in messages if m["role"] == "assistant")
    assert leader["id"] != writer["id"]


@pytest.mark.asyncio
async def test_reset_then_delta_preserves_order(tmp_path):
    task_store = TaskStore(persistent_store=AgentDeskStore(tmp_path / "store.json"))
    await task_store.ensure_task("task-order")
    await task_store.begin_assistant_message("task-order", sender="bot")
    await task_store.append_assistant_delta("task-order", "phase1")
    await task_store.reset_assistant_content("task-order")
    await task_store.append_assistant_delta("task-order", "phase2")
    await task_store.finalize_assistant_message("task-order")
    messages = await task_store.get_messages("task-order")
    assert messages[0]["content"] == "phase2"


@pytest.mark.asyncio
async def test_append_assistant_delta_falls_back_when_message_id_missing(tmp_path):
    """Explicit message_id misses should fall back to the streaming pointer."""
    persistent_store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=persistent_store)

    await task_store.ensure_task("task-1")
    await task_store.begin_assistant_message("task-1", sender="bot")
    await task_store.append_assistant_delta("task-1", "hello", message_id="missing-id")

    messages = await task_store.get_messages("task-1")
    assert messages[-1]["content"] == "hello"


@pytest.mark.asyncio
async def test_append_assistant_delta_after_finalize_appends_to_tail(tmp_path):
    persistent_store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=persistent_store)

    await task_store.ensure_task("task-1")
    await task_store.begin_assistant_message("task-1", sender="bot")
    await task_store.append_assistant_delta("task-1", "part1")
    await task_store.finalize_assistant_message("task-1")
    await task_store.append_assistant_delta("task-1", "part2")

    messages = await task_store.get_messages("task-1")
    assert messages[-1]["content"] == "part1part2"


@pytest.mark.asyncio
async def test_team_timeline_append_debounces_disk_writes(tmp_path):
    persistent_store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=persistent_store)
    write_count = 0
    original_replace = persistent_store.replace_team_timeline

    def counting_replace(task_id: str, timeline: list) -> None:
        nonlocal write_count
        write_count += 1
        original_replace(task_id, timeline)

    persistent_store.replace_team_timeline = counting_replace  # type: ignore[method-assign]

    await task_store.ensure_task("task-1")
    for idx in range(20):
        await task_store.append_team_timeline_entry(
            "task-1",
            {
                "kind": "leader_text",
                "actor": "团队·leader",
                "seq": 1,
                "ts": idx,
                "text": "a",
                "delta": True,
            },
        )

    assert write_count == 0
    await task_store.flush_team_timeline("task-1")
    assert write_count == 1

    task = persistent_store.get_by_key("tasks", "id", "task-1")
    assert task is not None
    assert task["teamTimeline"][-1]["text"] == "a" * 20


@pytest.mark.asyncio
async def test_team_timeline_coalesces_worker_status_phase(tmp_path):
    persistent_store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=persistent_store)

    await task_store.ensure_task("task-1")
    await task_store.append_team_timeline_entry(
        "task-1",
        {
            "kind": "phase",
            "actor": "团队·leader",
            "seq": 1,
            "ts": 1,
            "phase": "worker_status",
            "target": "研究员",
            "label": "研究员正在搜索…",
        },
    )
    await task_store.append_team_timeline_entry(
        "task-1",
        {
            "kind": "phase",
            "actor": "团队·leader",
            "seq": 2,
            "ts": 2,
            "phase": "worker_status",
            "target": "研究员",
            "label": "研究员还在搜索…",
        },
    )

    timeline = await task_store.get_team_timeline("task-1")
    assert len(timeline) == 1
    assert timeline[0]["label"] == "研究员还在搜索…"


@pytest.mark.asyncio
async def test_team_timeline_coalesces_cumulative_leader_text(tmp_path):
    persistent_store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=persistent_store)

    await task_store.ensure_task("task-1")
    await task_store.append_team_timeline_entry(
        "task-1",
        {
            "kind": "leader_text",
            "actor": "团队·leader",
            "seq": 1,
            "ts": 1,
            "text": "团队",
            "delta": True,
        },
    )
    await task_store.append_team_timeline_entry(
        "task-1",
        {
            "kind": "leader_text",
            "actor": "团队·leader",
            "seq": 1,
            "ts": 2,
            "text": "团队都在线，开始派工！",
            "delta": True,
        },
    )

    timeline = await task_store.get_team_timeline("task-1")
    assert len(timeline) == 1
    assert timeline[0]["text"] == "团队都在线，开始派工！"


@pytest.mark.asyncio
async def test_team_timeline_assigns_global_monotonic_seq(tmp_path):
    persistent_store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=persistent_store)

    await task_store.ensure_task("task-1")
    first = await task_store.append_team_timeline_entry(
        "task-1",
        {
            "kind": "user_message",
            "actor": "user",
            "seq": 0,
            "ts": 1,
            "text": "round one",
        },
    )
    await task_store.append_team_timeline_entry(
        "task-1",
        {
            "kind": "leader_text",
            "actor": "团队·leader",
            "seq": 1,
            "ts": 2,
            "text": "answer one",
        },
    )
    second = await task_store.append_team_timeline_entry(
        "task-1",
        {
            "kind": "user_message",
            "actor": "user",
            "seq": 0,
            "ts": 3,
            "text": "round two",
        },
    )

    assert first["seq"] == 0
    assert second["seq"] == 2

    timeline = await task_store.get_team_timeline("task-1")
    assert [entry["seq"] for entry in timeline] == [0, 1, 2]
    assert [entry["text"] for entry in timeline if entry["kind"] == "user_message"] == [
        "round one",
        "round two",
    ]


@pytest.mark.asyncio
async def test_streaming_member_assistant_messages_excludes_leader(tmp_path):
    persistent_store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=persistent_store)

    await task_store.ensure_task("task-team")
    await task_store.begin_assistant_message(
        "task-team",
        sender="增长团队·leader",
    )
    await task_store.begin_assistant_message(
        "task-team",
        sender="Alice",
        set_streaming=False,
        session_id=_team_member_session_id("task-team", "Alice"),
    )

    pending = await task_store.streaming_member_assistant_messages(
        "task-team",
        leader_sender="增长团队·leader",
    )
    assert len(pending) == 1
    assert pending[0]["sender"] == "Alice"
    assert pending[0].get("sessionId") == _team_member_session_id(
        "task-team",
        "Alice",
    )
