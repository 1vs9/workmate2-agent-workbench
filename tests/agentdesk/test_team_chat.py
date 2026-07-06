# -*- coding: utf-8 -*-
"""Tests for AgentDesk team-mode chat native delegation translation."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock

import pytest

from qwenpaw.agentdesk import chat as agentdesk_chat
from qwenpaw.agentdesk import chat_task_target
from qwenpaw.agentdesk import run_status as agentdesk_run_status
from qwenpaw.agents.tools import agent_management as agent_tools
from qwenpaw.agentdesk.models import ChatRequest
from qwenpaw.agentdesk.stream_protocol import StreamEventSequencer
from qwenpaw.agentdesk.store import AgentDeskStore
from qwenpaw.agentdesk.task_store import TaskStore
from qwenpaw.agentdesk.team_chat import (
    _NativeTeamEventBridge,
    _begin_worker_assistant_message,
    _run_coordinated_team_round,
    _stream_agent_turn,
    _team_member_session_id,
    _team_session_id,
    _TEAM_LEADER_SESSION_SUFFIX,
    resolve_team_record,
    stream_team_chat as _stream_team_chat,
)


def _parse_sse_events(lines: list[str]) -> list[dict]:
    events: list[dict] = []
    for line in lines:
        if not line.startswith("data:"):
            continue
        events.append(json.loads(line[5:].strip()))
    return events


def _patch_team_stores(monkeypatch, store, task_store):
    monkeypatch.setattr(agentdesk_run_status, "store", store)
    monkeypatch.setattr("qwenpaw.agentdesk.session_routing.agentdesk_store", store)
    monkeypatch.setattr("qwenpaw.agentdesk.team_records.agentdesk_store", store)
    monkeypatch.setattr(chat_task_target, "agentdesk_store", store)
    monkeypatch.setattr("qwenpaw.agentdesk.team_chat.task_store", task_store)
    monkeypatch.setattr("qwenpaw.agentdesk.chat.task_store", task_store)
    monkeypatch.setattr("qwenpaw.agentdesk.stream_side_effects.task_store", task_store)
    monkeypatch.setattr("qwenpaw.agentdesk.team_completion.task_store", task_store)
    monkeypatch.setattr("qwenpaw.agentdesk.team_worker_messages.task_store", task_store)


def test_native_team_bridge_maps_worker_lifecycle():
    bridge = _NativeTeamEventBridge(members=["Alice"], leader_sender="团队·leader")
    start = bridge.map_event(
        {
            "type": "tool_call_start",
            "tool_name": "chat_with_agent",
            "tool_call_id": "c1",
            "tool_arguments": {"to_agent": "Alice"},
        },
    )
    assert any(evt.get("type") == "worker_start" and evt.get("worker") == "Alice" for evt in start)

    done = bridge.map_event(
        {
            "type": "tool_result_end",
            "tool_name": "chat_with_agent",
            "tool_call_id": "c1",
            "detail": "[SESSION: s1]\n\nAlice 完成子任务",
        },
    )
    assert any(evt.get("type") == "worker_done" and evt.get("worker") == "Alice" for evt in done)
    assert not any(
        evt.get("type") == "text_delta" and evt.get("sender") == "Alice" for evt in done
    )

    bus_done = bridge.emit_worker_done_from_bus("Alice")
    assert any(
        evt.get("type") == "worker_done" and evt.get("worker") == "Alice" for evt in bus_done
    )

    synth = bridge.map_event({"type": "text_delta", "sender": "团队·leader", "content": "汇总"})
    assert any(evt.get("type") == "team_phase" and evt.get("phase") == "synthesizing" for evt in synth)


def test_native_team_bridge_tags_delegation_with_member_name():
    bridge = _NativeTeamEventBridge(members=["Alice"], leader_sender="团队·leader")
    mapped = bridge.map_event(
        {
            "type": "tool_call_end",
            "tool_name": "chat_with_agent",
            "tool_call_id": "c1",
            "tool_arguments": {"to_agent": "Alice", "text": "请做自我介绍"},
        },
    )
    tagged = [
        evt
        for evt in mapped
        if evt.get("type") == "tool_call_end"
        and evt.get("tool_name") == "chat_with_agent"
    ]
    assert tagged and tagged[0].get("member_name") == "Alice"


def test_resolve_team_record_by_id(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr("qwenpaw.agentdesk.team_records.agentdesk_store", store)
    store.upsert_by_key("teams", "id", "team-1", {"name": "增长团队", "members": ["Alice"]})
    payload = ChatRequest(task_id="t1", message="hi", team_id="team-1")
    found = resolve_team_record(payload)
    assert found is not None
    assert found["name"] == "增长团队"


def test_resolve_team_record_by_name(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr("qwenpaw.agentdesk.team_records.agentdesk_store", store)
    store.upsert_by_key("teams", "id", "team-2", {"name": "研发组", "members": []})
    payload = ChatRequest(task_id="t1", message="hi", team_name="研发组")
    found = resolve_team_record(payload)
    assert found is not None
    assert found["id"] == "team-2"


@pytest.mark.asyncio
async def test_stream_chat_routes_team_mode(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_team_stores(monkeypatch, store, task_store)
    store.upsert_by_key("teams", "id", "team-route", {"name": "路由团队", "members": ["Alice"]})

    calls: list[dict] = []

    def fake_sync(_team):
        return {"agent_id": "lead_route", "leader_name": "路由团队·leader"}

    async def fake_stream_agent_turn(**kwargs):
        if False:
            yield ""
        calls.append(kwargs)
        await task_store.append_assistant_delta(kwargs["payload"].task_id, "ok")
        await task_store.finalize_assistant_message(kwargs["payload"].task_id, content="ok")
        kwargs["turn_result"]["final_text"] = "ok"
        kwargs["turn_result"]["fatal"] = False

    monkeypatch.setattr("qwenpaw.agentdesk.team_chat.sync_team_leader_agent", fake_sync)
    monkeypatch.setattr("qwenpaw.agentdesk.team_chat._stream_agent_turn", fake_stream_agent_turn)

    payload = ChatRequest(task_id="task-route", message="hello", mode="team", team_id="team-route")
    lines = [line async for line in agentdesk_chat._stream_chat(payload, MagicMock())]
    events = _parse_sse_events(lines)

    assert any(evt.get("type") == "team_phase" and evt.get("phase") == "planning" for evt in events)
    assert any(evt.get("type") == "team_phase" and evt.get("phase") == "done" for evt in events)
    assert any(evt.get("type") == "done" for evt in events)
    assert len(calls) == 1
    assert calls[0]["session_suffix"] == "leader-native"
    assert "@Alice" not in calls[0]["agent_message"]


@pytest.mark.asyncio
async def test_stream_chat_rejects_single_route_for_established_team_task(
    tmp_path,
    monkeypatch,
):
    """Established team sessions are locked to the team conversation.

    If the frontend tries to send a single/default turn for the same task, the
    backend must surface a visible error instead of silently switching routing.
    """
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_team_stores(monkeypatch, store, task_store)
    store.upsert_by_key("teams", "id", "team-route", {"name": "路由团队", "members": ["Alice"]})
    # The task was previously established as a team task.
    store.upsert_by_key(
        "tasks",
        "id",
        "task-established",
        {"id": "task-established", "mode": "team", "team_id": "team-route"},
    )

    calls: list[dict] = []

    def fake_sync(_team):
        return {"agent_id": "lead_route", "leader_name": "路由团队·leader"}

    async def fake_stream_agent_turn(**kwargs):
        if False:
            yield ""
        calls.append(kwargs)
        await task_store.append_assistant_delta(kwargs["payload"].task_id, "ok")
        await task_store.finalize_assistant_message(kwargs["payload"].task_id, content="ok")
        kwargs["turn_result"]["final_text"] = "ok"
        kwargs["turn_result"]["fatal"] = False

    monkeypatch.setattr("qwenpaw.agentdesk.team_chat.sync_team_leader_agent", fake_sync)
    monkeypatch.setattr("qwenpaw.agentdesk.team_chat._stream_agent_turn", fake_stream_agent_turn)

    # The frontend mis-sends this as a single/default turn (no team metadata).
    payload = ChatRequest(task_id="task-established", message="你好", mode="single")
    events = _parse_sse_events(
        [line async for line in agentdesk_chat._stream_chat(payload, MagicMock())],
    )

    assert calls == []
    assert any(
        evt.get("type") == "error"
        and evt.get("fatal")
        and "新开一个 session" in str(evt.get("content") or "")
        for evt in events
    )
    persisted = store.get_by_key("tasks", "id", "task-established")
    assert persisted is not None
    assert persisted.get("mode") == "team"
    assert str(persisted.get("team_id") or "") == "team-route"


def test_persist_task_chat_target_preserves_established_team(tmp_path, monkeypatch):
    """A stray single-mode turn must not erase a task's team association."""
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr("qwenpaw.agentdesk.chat.agentdesk_store", store)
    store.upsert_by_key(
        "tasks",
        "id",
        "task-keep-team",
        {"id": "task-keep-team", "mode": "team", "team_id": "team-x", "team_name": "X团队"},
    )

    chat_task_target.persist_task_chat_target(
        ChatRequest(task_id="task-keep-team", message="你好", mode="single"),
    )

    task = store.get_by_key("tasks", "id", "task-keep-team")
    assert task is not None
    assert task.get("mode") == "team"
    assert task.get("team_id") == "team-x"
    assert task.get("team_name") == "X团队"


@pytest.mark.asyncio
async def test_stream_team_chat_unknown_team(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_team_stores(monkeypatch, store, task_store)
    payload = ChatRequest(task_id="task-unknown", message="你好", mode="team", team_id="missing")
    events = _parse_sse_events([line async for line in _stream_team_chat(payload, MagicMock())])
    assert any(evt.get("type") == "error" and evt.get("fatal") for evt in events)


@pytest.mark.asyncio
async def test_stream_team_chat_reconnect_keeps_running_status(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_team_stores(monkeypatch, store, task_store)
    store.upsert_by_key(
        "teams",
        "id",
        "team-r",
        {"name": "协同小队", "members": ["Alice"], "desc": "协同处理任务"},
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat.sync_team_leader_agent",
        lambda _team: {"agent_id": "lead_teamr", "leader_name": "协同小队·leader"},
    )
    await task_store.ensure_task("task-reconnect")
    await task_store.append_user_message("task-reconnect", "你好")
    await task_store.begin_assistant_message("task-reconnect", sender="协同小队·leader")
    await task_store.append_assistant_delta("task-reconnect", "处理中")
    agentdesk_run_status.set_task_run_status(
        "task-reconnect",
        "running",
        persistent_store=store,
    )

    async def _fake_worker_reconnect(**_kwargs):
        if False:
            yield ""
        yield 'data: {"type":"heartbeat"}\n\n'

    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat._resolve_team_leader_chat",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat._stream_team_worker_reconnect",
        _fake_worker_reconnect,
    )

    payload = ChatRequest(
        task_id="task-reconnect",
        message="",
        mode="team",
        team_id="team-r",
        team_name="协同小队",
        reconnect=True,
    )
    events = _parse_sse_events([line async for line in _stream_team_chat(payload, MagicMock())])
    assert not any(evt.get("type") == "done" for evt in events)
    task = store.get_by_key("tasks", "id", "task-reconnect") or {}
    assert str(task.get("runStatus") or "") == "running"
    messages = await task_store.get_messages("task-reconnect")
    leader = next(m for m in messages if m.get("role") == "assistant")
    assert leader.get("streaming") is True


@pytest.mark.asyncio
async def test_build_done_event_can_skip_finalize(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_team_stores(monkeypatch, store, task_store)
    await task_store.ensure_task("task-done")
    await task_store.begin_assistant_message("task-done", sender="Alice")
    from qwenpaw.agentdesk.team_chat import _build_done_event

    snapshot = await _build_done_event("task-done", finalize=False)
    assert snapshot["type"] == "done"
    messages = await task_store.get_messages("task-done")
    assert messages[0].get("streaming") is True

    terminal = await _build_done_event("task-done", finalize=True)
    assert terminal["type"] == "done"
    messages = await task_store.get_messages("task-done")
    assert messages[0].get("streaming") is False


@pytest.mark.asyncio
async def test_stream_team_chat_maps_native_tool_events(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_team_stores(monkeypatch, store, task_store)
    store.upsert_by_key(
        "teams",
        "id",
        "team-1",
        {"name": "增长团队", "members": ["Alice"], "desc": "协调增长任务"},
    )

    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat.sync_team_leader_agent",
        lambda _team: {"agent_id": "lead_team1", "leader_name": "增长团队·leader"},
    )

    async def fake_stream_agent_turn(**kwargs):
        mapper = kwargs["event_mapper"]
        sequencer = kwargs["sequencer"]
        for native_evt in [
            {"type": "text_delta", "sender": "增长团队·leader", "content": "先拆解"},
            {
                "type": "tool_call_start",
                "tool_name": "chat_with_agent",
                "tool_call_id": "call-1",
                "tool_arguments": {"to_agent": "Alice"},
            },
            {
                "type": "tool_result_end",
                "tool_name": "chat_with_agent",
                "tool_call_id": "call-1",
                "detail": "[SESSION: s1]\n\nAlice 完成子任务",
            },
            {"type": "text_delta", "sender": "增长团队·leader", "content": "汇总中"},
        ]:
            for mapped in mapper(native_evt):
                yield f"data: {json.dumps(sequencer.wrap(mapped), ensure_ascii=False)}\n\n"
        await task_store.begin_assistant_message(
            kwargs["payload"].task_id,
            sender="Alice",
        )
        await task_store.append_assistant_delta(
            kwargs["payload"].task_id,
            "Alice 完成子任务",
        )
        await task_store.finalize_assistant_message(
            kwargs["payload"].task_id,
            content="Alice 完成子任务",
        )
        await task_store.begin_assistant_message(
            kwargs["payload"].task_id,
            sender="增长团队·leader",
        )
        await task_store.append_assistant_delta(
            kwargs["payload"].task_id,
            "先拆解汇总中",
        )
        await task_store.finalize_assistant_message(
            kwargs["payload"].task_id,
            content="先拆解汇总中",
        )
        kwargs["turn_result"]["final_text"] = "先拆解汇总中"
        kwargs["turn_result"]["fatal"] = False

    monkeypatch.setattr("qwenpaw.agentdesk.team_chat._stream_agent_turn", fake_stream_agent_turn)
    payload = ChatRequest(
        task_id="task-native-tools",
        message="请协作",
        mode="team",
        team_id="team-1",
        team_name="增长团队",
    )
    events = _parse_sse_events([line async for line in _stream_team_chat(payload, MagicMock())])

    assert any(evt.get("type") == "worker_start" and evt.get("worker") == "Alice" for evt in events)
    assert any(evt.get("type") == "worker_done" and evt.get("worker") == "Alice" for evt in events)
    assert any(evt.get("type") == "team_phase" and evt.get("phase") == "synthesizing" for evt in events)
    assert not any(
        evt.get("type") == "text_delta"
        and evt.get("sender") == "Alice"
        for evt in events
    )
    done = next(evt for evt in events if evt.get("type") == "done")
    worker_msgs = [
        msg
        for msg in done["messages"]
        if msg.get("role") == "assistant" and msg.get("sender") == "Alice"
    ]
    assert worker_msgs
    assert done["messages"][-1]["sender"] == "增长团队·leader"
    rebuilt = await task_store.get_messages("task-native-tools")
    assert any(
        msg.get("role") == "assistant" and msg.get("sender") == "Alice"
        for msg in rebuilt
    )


class _FakeChat:
    id = "chat-team-worker"


class _FakeChannel:
    def resolve_session_id(self, sender_id, channel_meta=None):
        if channel_meta and channel_meta.get("session_id"):
            return channel_meta["session_id"]
        return f"console:{sender_id}"

    async def stream_one(self, _payload):  # pragma: no cover - never awaited
        if False:
            yield ""


class _FakeChannelManager:
    def __init__(self, channel):
        self._channel = channel

    async def get_channel(self, _name):
        return self._channel


class _FakeChatManager:
    async def get_or_create_chat(self, *_args, **_kwargs):
        return _FakeChat()


class _FakeTracker:
    def __init__(self, scripted):
        self._scripted = scripted

    async def attach_or_start(self, _run_key, _payload, _stream_fn):
        return asyncio.Queue(), False

    def stream_from_queue(self, _queue, _run_key):
        scripted = self._scripted

        async def _gen():
            for item in scripted:
                if callable(item):
                    await item()
                    continue
                yield item

        return _gen()

    async def get_status(self, _run_key):
        return "idle"


class _FakeWorkspace:
    def __init__(self, tracker, channel):
        self.workspace_dir = "/tmp/ws"
        self.channel_manager = _FakeChannelManager(channel)
        self.chat_manager = _FakeChatManager()
        self.task_tracker = tracker


@pytest.mark.asyncio
async def test_stream_agent_turn_forwards_worker_reply_and_dedups_echo(
    tmp_path,
    monkeypatch,
):
    """The worker's own clean reply renders under its bubble exactly once.

    Regression: live worker observability dropped the worker's NORMAL final
    reply (only its trace showed). The worker's reply now streams from its own
    bus stream (clean text), the leader's delegation-result echo is suppressed
    to avoid duplication, and the reply is persisted onto the worker's message.
    """
    import asyncio as _asyncio

    from qwenpaw.runtime.worker_stream_bus import worker_stream_bus

    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_team_stores(monkeypatch, store, task_store)

    # Keep the bridge member resolution and worker-name lookup offline/stable.
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat.resolve_agent_id",
        lambda name: name,
    )

    def _raise_cfg(_aid):
        raise ValueError("no config in test")

    monkeypatch.setattr("qwenpaw.config.config.load_agent_config", _raise_cfg)

    async def _fake_ensure_model(_agent_id):
        return (object(), None)

    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat.ensure_chat_model",
        _fake_ensure_model,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat._schedule_sync_task_workspace",
        lambda *a, **k: None,
    )

    task_id = "task-worker-reply"
    session_suffix = "leader-native"
    bus_key = _team_session_id(task_id, session_suffix)

    plugin_call = (
        'data: {"object": "message", "type": "plugin_call", '
        '"status": "completed", "content": [{"type": "data", "data": '
        '{"name": "chat_with_agent", "call_id": "c1", '
        '"arguments": {"to_agent": "Alice"}}}]}'
    )
    plugin_output = (
        'data: {"object": "message", "type": "plugin_call_output", '
        '"status": "completed", "content": [{"type": "data", "data": '
        '{"name": "chat_with_agent", "call_id": "c1", '
        '"output": "[SESSION: s1]\\n\\n\\u7ed3\\u679c", '
        '"state": "success"}}]}'
    )

    async def _publish_worker_reply():
        # Publish the worker's own clean reply BEFORE the leader's tool result
        # so the dedup flag is set before the echo is processed.
        worker_stream_bus.publish(
            bus_key,
            (
                "Alice",
                'data: {"object": "content", "type": "text", '
                '"delta": true, "text": "\\u7ed3\\u679c"}',
            ),
        )
        await _asyncio.sleep(0)
        await _asyncio.sleep(0)

    tracker = _FakeTracker([plugin_call, _publish_worker_reply, plugin_output])
    workspace = _FakeWorkspace(tracker, _FakeChannel())

    async def _fake_get_agent(_request, agent_id=None):
        return workspace

    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat.get_agent_for_request",
        _fake_get_agent,
    )

    await task_store.ensure_task(task_id)
    await task_store.begin_assistant_message(task_id, sender="增长团队·leader")

    sequencer = StreamEventSequencer(task_id=task_id)
    bridge = _NativeTeamEventBridge(members=["Alice"], leader_sender="增长团队·leader")
    payload = ChatRequest(task_id=task_id, message="请协作", mode="team")
    turn_result: dict = {"final_text": "", "fatal": False}

    lines = [
        line
        async for line in _stream_agent_turn(
            payload=payload,
            request=MagicMock(),
            agent_id="lead_team1",
            sender="增长团队·leader",
            agent_message="请协作",
            sequencer=sequencer,
            session_suffix=session_suffix,
            emit_stream_start=True,
            turn_result=turn_result,
            event_mapper=bridge.map_event,
            delegation_bridge=bridge,
        )
    ]
    events = _parse_sse_events(lines)

    alice_text = [
        evt
        for evt in events
        if evt.get("type") == "text_delta"
        and evt.get("sender") == "Alice"
        and str(evt.get("content") or "")
    ]
    # The worker reply renders exactly once, with clean text (no SESSION header).
    assert len(alice_text) == 1
    assert alice_text[0]["content"] == "结果"
    assert not any(
        "[SESSION" in str(evt.get("content") or "") for evt in events
    )
    assert any(evt.get("type") == "worker_done" and evt.get("worker") == "Alice" for evt in events)

    # The worker's reply is persisted onto its own (Alice) assistant message.
    messages = await task_store.get_messages(task_id)
    alice_msgs = [
        msg
        for msg in messages
        if msg.get("role") == "assistant" and msg.get("sender") == "Alice"
    ]
    assert alice_msgs
    assert "结果" in str(alice_msgs[-1].get("content") or "")


@pytest.mark.asyncio
async def test_stream_agent_turn_completion_wait_does_not_poll_status(tmp_path, monkeypatch):
    """Team turn completion should rely on stream signals, not check_agent_task polls."""
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_team_stores(monkeypatch, store, task_store)

    monkeypatch.setattr("qwenpaw.agentdesk.team_chat.resolve_agent_id", lambda name: name)
    monkeypatch.setattr(
        "qwenpaw.config.config.load_agent_config",
        lambda _aid: (_ for _ in ()).throw(ValueError("no config in test")),
    )

    async def _fake_ensure_model(_agent_id):
        return (object(), None)

    monkeypatch.setattr("qwenpaw.agentdesk.team_chat.ensure_chat_model", _fake_ensure_model)
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat._schedule_sync_task_workspace",
        lambda *a, **k: None,
    )

    def _unexpected_poll(*_args, **_kwargs):
        raise AssertionError("check_agent_task polling should not run on hot path")


    plugin_call = (
        'data: {"object": "message", "type": "plugin_call", '
        '"status": "completed", "content": [{"type": "data", "data": '
        '{"name": "chat_with_agent", "call_id": "c1", '
        '"arguments": {"to_agent": "Alice"}}}]}'
    )
    plugin_output = (
        'data: {"object": "message", "type": "plugin_call_output", '
        '"status": "completed", "content": [{"type": "data", "data": '
        '{"name": "chat_with_agent", "call_id": "c1", '
        '"output": "[SESSION: s1]\\n\\nTask completed.", '
        '"state": "success"}}]}'
    )
    tracker = _FakeTracker([plugin_call, plugin_output])
    workspace = _FakeWorkspace(tracker, _FakeChannel())

    async def _fake_get_agent(_request, agent_id=None):
        return workspace

    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat.get_agent_for_request",
        _fake_get_agent,
    )

    task_id = "task-worker-no-poll"
    await task_store.ensure_task(task_id)
    await task_store.begin_assistant_message(task_id, sender="增长团队·leader")

    sequencer = StreamEventSequencer(task_id=task_id)
    bridge = _NativeTeamEventBridge(members=["Alice"], leader_sender="增长团队·leader")
    payload = ChatRequest(task_id=task_id, message="请协作", mode="team")
    turn_result: dict = {"final_text": "", "fatal": False}

    lines = [
        line
        async for line in _stream_agent_turn(
            payload=payload,
            request=MagicMock(),
            agent_id="lead_team1",
            sender="增长团队·leader",
            agent_message="请协作",
            sequencer=sequencer,
            session_suffix="leader-native",
            emit_stream_start=True,
            turn_result=turn_result,
            event_mapper=bridge.map_event,
            delegation_bridge=bridge,
        )
    ]
    events = _parse_sse_events(lines)
    assert any(
        evt.get("type") == "worker_done" and evt.get("worker") == "Alice"
        for evt in events
    )


@pytest.mark.asyncio
async def test_stream_agent_turn_forwards_delta_less_worker_final_message(
    tmp_path,
    monkeypatch,
):
    """A worker that emits ONLY a final ``message`` (no text_delta) still has its
    normal reply surfaced under its own bubble and persisted.

    Regression for the reported bug: multi-agent conversations showed each
    worker's observable PROCESS (thinking/tool traces) but NOT the worker's
    normal final reply text. Some workers never stream incremental
    ``text_delta`` chunks and only produce a single completed ``message`` at the
    end; that path must also forward the worker's reply (see the ``message``
    branch in ``_drain_worker_events``).
    """
    import asyncio as _asyncio

    from qwenpaw.runtime.worker_stream_bus import worker_stream_bus

    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_team_stores(monkeypatch, store, task_store)

    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat.resolve_agent_id",
        lambda name: name,
    )

    def _raise_cfg(_aid):
        raise ValueError("no config in test")

    monkeypatch.setattr("qwenpaw.config.config.load_agent_config", _raise_cfg)

    async def _fake_ensure_model(_agent_id):
        return (object(), None)

    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat.ensure_chat_model",
        _fake_ensure_model,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat._schedule_sync_task_workspace",
        lambda *a, **k: None,
    )

    task_id = "task-worker-final-message"
    session_suffix = "leader-native"
    bus_key = _team_session_id(task_id, session_suffix)

    plugin_call = (
        'data: {"object": "message", "type": "plugin_call", '
        '"status": "completed", "content": [{"type": "data", "data": '
        '{"name": "chat_with_agent", "call_id": "c1", '
        '"arguments": {"to_agent": "Alice"}}}]}'
    )
    plugin_output = (
        'data: {"object": "message", "type": "plugin_call_output", '
        '"status": "completed", "content": [{"type": "data", "data": '
        '{"name": "chat_with_agent", "call_id": "c1", '
        '"output": "[SESSION: s1]\\n\\n\\u7ed3\\u679c", '
        '"state": "success"}}]}'
    )

    async def _publish_worker_process_and_reply():
        # 1) Observable PROCESS: a worker thinking trace.
        worker_stream_bus.publish(
            bus_key,
            (
                "Alice",
                'data: {"object": "message", "type": "reasoning", '
                '"id": "r1", "status": "in_progress", "content": []}',
            ),
        )
        worker_stream_bus.publish(
            bus_key,
            (
                "Alice",
                'data: {"object": "message", "type": "reasoning", '
                '"id": "r1", "status": "completed", "content": '
                '[{"type": "text", "text": "\\u601d\\u8003"}]}',
            ),
        )
        # 2) The worker's NORMAL final reply, delivered as a single completed
        # ``message`` with NO preceding ``text_delta`` chunks.
        worker_stream_bus.publish(
            bus_key,
            (
                "Alice",
                'data: {"object": "message", "role": "assistant", '
                '"status": "completed", "content": '
                '[{"type": "text", "text": "\\u7ed3\\u679c"}]}',
            ),
        )
        await _asyncio.sleep(0)
        await _asyncio.sleep(0)

    tracker = _FakeTracker(
        [plugin_call, _publish_worker_process_and_reply, plugin_output],
    )
    workspace = _FakeWorkspace(tracker, _FakeChannel())

    async def _fake_get_agent(_request, agent_id=None):
        return workspace

    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat.get_agent_for_request",
        _fake_get_agent,
    )

    await task_store.ensure_task(task_id)
    await task_store.begin_assistant_message(task_id, sender="增长团队·leader")

    sequencer = StreamEventSequencer(task_id=task_id)
    bridge = _NativeTeamEventBridge(members=["Alice"], leader_sender="增长团队·leader")
    payload = ChatRequest(task_id=task_id, message="请协作", mode="team")
    turn_result: dict = {"final_text": "", "fatal": False}

    lines = [
        line
        async for line in _stream_agent_turn(
            payload=payload,
            request=MagicMock(),
            agent_id="lead_team1",
            sender="增长团队·leader",
            agent_message="请协作",
            sequencer=sequencer,
            session_suffix=session_suffix,
            emit_stream_start=True,
            turn_result=turn_result,
            event_mapper=bridge.map_event,
            delegation_bridge=bridge,
        )
    ]
    events = _parse_sse_events(lines)

    # The worker's observable PROCESS surfaced under its own actor.
    assert any(
        evt.get("type") in {"thinking_start", "thinking_end"}
        and evt.get("sender") == "Alice"
        for evt in events
    )

    # The worker's normal final reply surfaced exactly once with clean text.
    alice_reply = [
        evt
        for evt in events
        if evt.get("type") in {"message", "text_delta"}
        and evt.get("sender") == "Alice"
        and str(evt.get("content") or "")
    ]
    assert len(alice_reply) == 1
    assert alice_reply[0]["content"] == "结果"
    # The raw delegation-result echo (with SESSION header) is suppressed.
    assert not any(
        "[SESSION" in str(evt.get("content") or "") for evt in events
    )
    assert any(
        evt.get("type") == "worker_done" and evt.get("worker") == "Alice"
        for evt in events
    )

    # The reply is persisted onto the worker's own (Alice) assistant message.
    messages = await task_store.get_messages(task_id)
    alice_msgs = [
        msg
        for msg in messages
        if msg.get("role") == "assistant" and msg.get("sender") == "Alice"
    ]
    assert alice_msgs
    assert "结果" in str(alice_msgs[-1].get("content") or "")


@pytest.mark.asyncio
async def test_stream_team_chat_surfaces_visible_error(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_team_stores(monkeypatch, store, task_store)
    store.upsert_by_key(
        "teams",
        "id",
        "team-1",
        {"name": "增长团队", "members": ["Alice"], "desc": "协调增长任务"},
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat.sync_team_leader_agent",
        lambda _team: {"agent_id": "lead_team1", "leader_name": "增长团队·leader"},
    )

    async def fake_stream_agent_turn(**kwargs):
        yield 'data: {"type":"error","content":"native failed","fatal":true}\n\n'
        kwargs["turn_result"]["final_text"] = ""
        kwargs["turn_result"]["fatal"] = True

    monkeypatch.setattr("qwenpaw.agentdesk.team_chat._stream_agent_turn", fake_stream_agent_turn)
    payload = ChatRequest(task_id="task-team-fail", message="请协作", mode="team", team_id="team-1")
    events = _parse_sse_events([line async for line in _stream_team_chat(payload, MagicMock())])
    assert any(evt.get("type") == "error" and evt.get("fatal") for evt in events)
    assert any(evt.get("type") == "done" for evt in events)


@pytest.mark.asyncio
async def test_stream_team_chat_forwards_turn_events_incrementally(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_team_stores(monkeypatch, store, task_store)
    store.upsert_by_key("teams", "id", "team-stream", {"name": "流式团队", "members": []})
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat.sync_team_leader_agent",
        lambda _team: {"agent_id": "lead_stream", "leader_name": "流式团队·leader"},
    )

    async def fake_stream_agent_turn(**kwargs):
        if kwargs["session_suffix"] != "leader-native":
            kwargs["turn_result"]["final_text"] = ""
            kwargs["turn_result"]["fatal"] = False
            return
        yield 'data: {"type":"text_delta","sender":"流式团队·leader","content":"你"}\n\n'
        yield 'data: {"type":"text_delta","sender":"流式团队·leader","content":"好"}\n\n'
        kwargs["turn_result"]["final_text"] = "你好"
        kwargs["turn_result"]["fatal"] = False

    monkeypatch.setattr("qwenpaw.agentdesk.team_chat._stream_agent_turn", fake_stream_agent_turn)
    payload = ChatRequest(task_id="task-stream", message="你好", mode="team", team_id="team-stream")
    stream = _stream_team_chat(payload, MagicMock())
    text_delta_lines: list[str] = []
    while len(text_delta_lines) < 2:
        line = await stream.__anext__()
        if "text_delta" in line:
            text_delta_lines.append(line)
    assert "你" in text_delta_lines[0]
    assert "好" in text_delta_lines[1]
    events = _parse_sse_events([*text_delta_lines, *[line async for line in stream]])
    assert any(evt.get("type") == "done" for evt in events)


@pytest.mark.asyncio
async def test_stream_agent_turn_emit_stream_start_does_not_shadow_chat_request(
    tmp_path,
    monkeypatch,
):
    """``emit_stream_start`` must not reuse the ``payload`` name for SSE dicts."""
    from unittest.mock import MagicMock

    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_team_stores(monkeypatch, store, task_store)

    scheduled: list[tuple] = []

    def _record_sync(task_id, agent_id, workspace_dir, *, employee_name=None):
        scheduled.append((task_id, agent_id, employee_name))

    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat._schedule_sync_task_workspace",
        _record_sync,
    )

    async def _fake_ensure_model(_agent_id):
        return (object(), None)

    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat.ensure_chat_model",
        _fake_ensure_model,
    )

    class _Channel:
        def resolve_session_id(self, *, sender_id, channel_meta):
            return channel_meta.get("session_id", "sess")

        async def stream_one(self, _payload):
            if False:
                yield ""

    class _Chat:
        id = "chat-leader"

    class _ChatManager:
        async def get_or_create_chat(self, *a, **k):
            return _Chat()

    class _Tracker:
        async def attach_or_start(self, _run_key, _payload, _stream_fn):
            async def _empty():
                if False:
                    yield ""

            return (_empty(), False)

        def stream_from_queue(self, queue, _run_key):
            return queue

        async def get_status(self, _run_key):
            return "idle"

    class _ChannelManager:
        async def get_channel(self, _name):
            return _Channel()

    class _Workspace:
        workspace_dir = str(tmp_path)
        channel_manager = _ChannelManager()
        chat_manager = _ChatManager()
        task_tracker = _Tracker()

    async def _fake_get_agent(_request, agent_id=None):
        return _Workspace()

    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat.get_agent_for_request",
        _fake_get_agent,
    )

    task_id = "task-shadow"
    await task_store.ensure_task(task_id)
    payload = ChatRequest(task_id=task_id, message="你好", mode="team", team_id="team-1")
    sequencer = StreamEventSequencer(task_id=task_id)
    turn_result: dict = {"final_text": "", "fatal": False}

    lines = [
        line
        async for line in _stream_agent_turn(
            payload=payload,
            request=MagicMock(),
            agent_id="lead_shadow",
            sender="团队·leader",
            agent_message="你好",
            sequencer=sequencer,
            session_suffix="leader-native",
            emit_stream_start=True,
            stream_message_id="msg-leader",
            turn_result=turn_result,
        )
    ]

    events = _parse_sse_events(lines)
    assert any(evt.get("type") == "stream_start" for evt in events)
    assert scheduled == [(task_id, "lead_shadow", None)]


def test_emit_worker_done_from_bus():
    bridge = _NativeTeamEventBridge(members=["Alice"], leader_sender="团队·leader")
    bridge.map_event(
        {
            "type": "tool_result_end",
            "tool_name": "chat_with_agent",
            "tool_call_id": "c1",
            "detail": "[SESSION: s1]\n\nAlice 完成",
            "tool_arguments": {"to_agent": "Alice"},
        },
    )

    done = bridge.emit_worker_done_from_bus("Alice")
    assert any(evt.get("type") == "worker_done" for evt in done)


def test_bridge_worker_results_seen_after_sync_delegation():
    bridge = _NativeTeamEventBridge(members=["Alice"], leader_sender="团队·leader")
    bridge.map_event(
        {
            "type": "tool_result_end",
            "tool_name": "chat_with_agent",
            "tool_call_id": "c1",
            "detail": "[SESSION: s1]\n\nAlice 完成",
            "tool_arguments": {"to_agent": "Alice"},
        },
    )
    assert bridge.worker_results_seen() is True


@pytest.mark.asyncio
async def test_run_coordinated_team_round_completes_after_worker_followup(
    tmp_path,
    monkeypatch,
):
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_team_stores(monkeypatch, store, task_store)
    store.upsert_by_key(
        "teams",
        "id",
        "team-follow",
        {"name": "跟进团队", "members": ["Alice"], "desc": "协调"},
    )

    turn_calls: list[str] = []

    async def fake_stream_agent_turn(**kwargs):
        turn_calls.append(kwargs["agent_message"][:20])
        mapper = kwargs.get("event_mapper")
        sequencer = kwargs["sequencer"]
        is_followup = "团队成员本轮产出" in kwargs["agent_message"]
        if mapper is not None and not is_followup:
            for mapped in mapper(
                {
                    "type": "tool_result_end",
                    "tool_name": "chat_with_agent",
                    "tool_call_id": "c1",
                    "detail": "[SESSION: s1]\n\nAlice 完成",
                    "tool_arguments": {"to_agent": "Alice"},
                },
            ):
                yield f"data: {json.dumps(sequencer.wrap(mapped), ensure_ascii=False)}\n\n"
        else:
            yield (
                'data: {"type":"text_delta","sender":"跟进团队·leader",'
                '"content":"整合汇报"}\n\n'
            )
        if not is_followup:
            alice_msg = await task_store.begin_assistant_message(
                kwargs["payload"].task_id,
                sender="Alice",
                set_streaming=False,
            )
            await task_store.append_assistant_delta(
                kwargs["payload"].task_id,
                "Alice 完成",
                message_id=str(alice_msg.get("id") or ""),
            )
            await task_store.finalize_assistant_message(
                kwargs["payload"].task_id,
                message_id=str(alice_msg.get("id") or ""),
            )
        else:
            await task_store.append_assistant_delta(
                kwargs["payload"].task_id,
                "整合汇报",
                message_id=kwargs.get("stream_message_id"),
            )
        kwargs["turn_result"]["final_text"] = (
            "整合汇报" if is_followup else "已派发"
        )
        kwargs["turn_result"]["fatal"] = False

    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat._stream_agent_turn",
        fake_stream_agent_turn,
    )

    payload = ChatRequest(
        task_id="task-follow",
        message="请协作",
        mode="team",
        team_id="team-follow",
    )
    await task_store.ensure_task(payload.task_id)
    leader_draft = await task_store.begin_assistant_message(
        payload.task_id,
        sender="跟进团队·leader",
    )
    sequencer = StreamEventSequencer(task_id=payload.task_id)
    events = _parse_sse_events(
        [
            line
            async for line in _run_coordinated_team_round(
                payload=payload,
                request=MagicMock(),
                sequencer=sequencer,
                team_name="跟进团队",
                leader_sender="跟进团队·leader",
                leader_agent_id="lead_follow",
                user_text="请协作",
                leader_message_id=str(leader_draft.get("id") or ""),
                members=["Alice"],
            )
        ],
    )

    assert len(turn_calls) == 1
    assert any(evt.get("type") == "team_phase" and evt.get("phase") == "done" for evt in events)
    assert any(evt.get("type") == "done" for evt in events)
    task = store.get_by_key("tasks", "id", "task-follow") or {}
    assert str(task.get("runStatus") or "") == "idle"


@pytest.mark.asyncio
async def test_stream_team_chat_no_phantom_synthesizing_at_end(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_team_stores(monkeypatch, store, task_store)
    store.upsert_by_key(
        "teams",
        "id",
        "team-end",
        {"name": "收尾团队", "members": [], "desc": ""},
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat.sync_team_leader_agent",
        lambda _team: {"agent_id": "lead_end", "leader_name": "收尾团队·leader"},
    )

    async def fake_stream_agent_turn(**kwargs):
        yield (
            'data: {"type":"text_delta","sender":"收尾团队·leader",'
            '"content":"直接回答"}\n\n'
        )
        kwargs["turn_result"]["final_text"] = "直接回答"
        kwargs["turn_result"]["fatal"] = False
        await task_store.append_assistant_delta(
            kwargs["payload"].task_id,
            "直接回答",
        )
        await task_store.finalize_assistant_message(
            kwargs["payload"].task_id,
            content="直接回答",
        )

    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_chat._stream_agent_turn",
        fake_stream_agent_turn,
    )

    payload = ChatRequest(
        task_id="task-end",
        message="你好",
        mode="team",
        team_id="team-end",
    )
    events = _parse_sse_events(
        [line async for line in _stream_team_chat(payload, MagicMock())],
    )
    synth_events = [
        evt
        for evt in events
        if evt.get("type") == "team_phase" and evt.get("phase") == "synthesizing"
    ]
    done_idx = next(i for i, evt in enumerate(events) if evt.get("type") == "done")
    assert not any(
        i > done_idx
        for i, evt in enumerate(events)
        if evt.get("type") == "team_phase" and evt.get("phase") == "synthesizing"
    )
    assert events[-1].get("type") == "done"
