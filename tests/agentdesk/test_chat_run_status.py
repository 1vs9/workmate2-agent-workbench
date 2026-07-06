# -*- coding: utf-8 -*-
"""Tests for AgentDesk chat runStatus lifecycle."""

import asyncio

import pytest

from qwenpaw.agentdesk import chat as agentdesk_chat
from qwenpaw.agentdesk import chat_event_stream
from qwenpaw.agentdesk import run_status, stream_side_effects
from qwenpaw.agentdesk.store import AgentDeskStore
from qwenpaw.agentdesk.task_store import TaskStore


def _mark_running(store: AgentDeskStore, task_id: str) -> None:
    run_status.set_task_run_status(task_id, "running", persistent_store=store)


async def _noop_async(*_args, **_kwargs):
    return None


def _patch_chat_runtime(
    monkeypatch,
    store: AgentDeskStore,
    task_store: TaskStore,
) -> None:
    monkeypatch.setattr(agentdesk_chat, "agentdesk_store", store)
    monkeypatch.setattr(agentdesk_chat, "task_store", task_store)
    monkeypatch.setattr(run_status, "store", store)


def test_set_task_run_status_persists_to_store(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")

    run_status.commit_task_run_status("task-1", "running", persistent_store=store)

    task = store.get_by_key("tasks", "id", "task-1")
    assert task is not None
    assert task["runStatus"] == "running"


@pytest.mark.asyncio
async def test_schedule_task_run_status_persists_without_error(tmp_path, monkeypatch):
    """Async runStatus writes still persist through the run-status owner."""
    store = AgentDeskStore(tmp_path / "store.json")

    await asyncio.to_thread(
        run_status.commit_task_run_status,
        "task-sched",
        "running",
        persistent_store=store,
    )

    task = store.get_by_key("tasks", "id", "task-sched")
    assert task is not None
    assert task["runStatus"] == "running"


def test_stale_scheduled_running_does_not_overwrite_idle(tmp_path, monkeypatch):
    """A late async ``running`` write must not resurrect runStatus after idle."""
    store = AgentDeskStore(tmp_path / "store.json")

    stale_seq = run_status._bump_run_status_seq("task-1")  # noqa: SLF001
    run_status.set_task_run_status(
        "task-1",
        "running",
        seq=stale_seq,
        persistent_store=store,
    )
    run_status.commit_task_run_status("task-1", "idle", persistent_store=store)
    run_status.set_task_run_status(
        "task-1",
        "running",
        seq=stale_seq,
        persistent_store=store,
    )

    task = store.get_by_key("tasks", "id", "task-1")
    assert task is not None
    assert task["runStatus"] == "idle"


@pytest.mark.asyncio
async def test_finalize_watch_marks_task_idle(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    monkeypatch.setattr(stream_side_effects, "task_store", task_store)
    monkeypatch.setattr(
        stream_side_effects,
        "commit_task_run_status",
        lambda task_id, status: run_status.commit_task_run_status(
            task_id,
            status,
            persistent_store=store,
        ),
    )

    class _Tracker:
        def __init__(self) -> None:
            self._status = "running"

        async def get_status(self, _run_key: str) -> str:
            return self._status

    tracker = _Tracker()
    await task_store.ensure_task("task-1")
    await task_store.begin_assistant_message("task-1", sender="bot")
    run_status.set_task_run_status("task-1", "running", persistent_store=store)

    watch = stream_side_effects.schedule_run_finalize_watch(
        task_id="task-1",
        run_key="chat-1",
        tracker=tracker,
    )
    tracker._status = "idle"
    await watch

    task = store.get_by_key("tasks", "id", "task-1")
    assert task is not None
    assert task["runStatus"] == "idle"
    messages = await task_store.get_messages("task-1")
    assert messages[-1]["streaming"] is False


@pytest.mark.asyncio
async def test_finalize_watch_closes_all_streaming_messages(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    monkeypatch.setattr(stream_side_effects, "task_store", task_store)
    monkeypatch.setattr(
        stream_side_effects,
        "commit_task_run_status",
        lambda task_id, status: run_status.commit_task_run_status(
            task_id,
            status,
            persistent_store=store,
        ),
    )

    class _Tracker:
        async def get_status(self, _run_key: str) -> str:
            return "idle"

    await task_store.ensure_task("task-1")
    await task_store.begin_assistant_message(
        "task-1",
        sender="leader",
        set_streaming=True,
    )
    await task_store.begin_assistant_message(
        "task-1",
        sender="Alice",
        set_streaming=False,
    )
    run_status.set_task_run_status("task-1", "running", persistent_store=store)

    watch = stream_side_effects.schedule_run_finalize_watch(
        task_id="task-1",
        run_key="chat-1",
        tracker=_Tracker(),
    )
    await watch

    assert run_status.task_run_status("task-1", persistent_store=store) == "idle"
    messages = await task_store.get_messages("task-1")
    assert messages
    assert all(not msg.get("streaming") for msg in messages)


async def test_emit_translated_events_emits_approval_required_while_waiting(
    tmp_path,
    monkeypatch,
):
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_chat_runtime(monkeypatch, store, task_store)

    async def _approval_event(task_id: str):
        if task_id != "task-1":
            return None
        return {
            "type": "approval_required",
            "task_id": task_id,
            "request_id": "req-approval",
            "tool_name": "execute_shell_command",
            "severity": "HIGH",
            "detail": "Dangerous shell command",
        }

    async def _slow_stream():
        await asyncio.sleep(0.2)
        yield (
            'data: {"object":"content","type":"text","text":"ok","delta":true}\n\n'
        )

    from qwenpaw.agentdesk.models import ChatRequest
    from qwenpaw.agentdesk.stream_protocol import StreamEventSequencer

    await task_store.ensure_task("task-1")
    await task_store.begin_assistant_message("task-1", sender="bot")
    payload = ChatRequest(task_id="task-1", message="hi")
    sequencer = StreamEventSequencer(task_id="task-1")
    lines = [
        line
        async for line in chat_event_stream.emit_translated_events(
            payload=payload,
            sender="bot",
            sequencer=sequencer,
            stream_it=_slow_stream(),
            task_store_obj=task_store,
            pending_approval_event_fn=_approval_event,
            approval_poll_s=0.05,
            schedule_persist_trace_event_fn=lambda *_a, **_k: None,
            persist_trace_event_fn=lambda *_a, **_k: _noop_async(),
            commit_task_run_status_fn=lambda task_id, status: run_status.commit_task_run_status(
                task_id,
                status,
                persistent_store=store,
            ),
        )
    ]

    assert any("approval_required" in line for line in lines)
    assert any("req-approval" in line for line in lines)


@pytest.mark.asyncio
async def test_emit_translated_events_finalizes_without_tracker_tail_wait(
    tmp_path,
    monkeypatch,
):
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_chat_runtime(monkeypatch, store, task_store)

    async def _stream():
        yield (
            'data: {"object":"content","type":"text","text":"plan","delta":true}\n\n'
        )

    from qwenpaw.agentdesk.models import ChatRequest
    from qwenpaw.agentdesk.stream_protocol import StreamEventSequencer

    await task_store.ensure_task("task-1")
    await task_store.begin_assistant_message("task-1", sender="bot")
    _mark_running(store, "task-1")

    payload = ChatRequest(task_id="task-1", message="hi")
    sequencer = StreamEventSequencer(task_id="task-1")
    lines = [
        line
        async for line in chat_event_stream.emit_translated_events(
            payload=payload,
            sender="bot",
            sequencer=sequencer,
            stream_it=_stream(),
            task_store_obj=task_store,
            pending_approval_event_fn=lambda _task_id: _noop_async(),
            schedule_persist_trace_event_fn=lambda *_a, **_k: None,
            persist_trace_event_fn=lambda *_a, **_k: _noop_async(),
            commit_task_run_status_fn=lambda task_id, status: run_status.commit_task_run_status(
                task_id,
                status,
                persistent_store=store,
            ),
        )
    ]

    task = store.get_by_key("tasks", "id", "task-1")
    assert task is not None
    assert task["runStatus"] == "idle"
    assert any('"type": "done"' in line or '"done"' in line for line in lines)


@pytest.mark.asyncio
async def test_emit_translated_events_survives_trace_persist_failure(
    tmp_path,
    monkeypatch,
):
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_chat_runtime(monkeypatch, store, task_store)

    def _boom(*_args, **_kwargs):
        raise PermissionError("lock denied")

    monkeypatch.setattr(store, "append_task_event", _boom)

    class _Tracker:
        async def get_status(self, _run_key: str) -> str:
            return "idle"

    async def _stream():
        yield (
            'data: {"object":"content","type":"text","text":"hello","delta":true}\n\n'
        )
        yield (
            'data: {"object":"message","type":"plugin_call","status":"completed",'
            '"content":[{"type":"data","data":{"name":"read_file","call_id":"c1",'
            '"arguments":{"path":"README.md"}}}]}\n\n'
        )

    from qwenpaw.agentdesk.models import ChatRequest
    from qwenpaw.agentdesk.stream_protocol import StreamEventSequencer

    await task_store.ensure_task("task-1")
    await task_store.begin_assistant_message("task-1", sender="bot")
    _mark_running(store, "task-1")

    payload = ChatRequest(task_id="task-1", message="hi")
    sequencer = StreamEventSequencer(task_id="task-1")
    lines = [
        line
        async for line in agentdesk_chat._emit_translated_events(  # noqa: SLF001
            payload=payload,
            sender="bot",
            sequencer=sequencer,
            stream_it=_stream(),
            tracker=_Tracker(),
            run_key="chat-1",
        )
    ]

    assert any("hello" in line for line in lines)
    assert any('"type": "done"' in line or '"done"' in line for line in lines)
    messages = await task_store.get_messages("task-1")
    assert messages[-1]["content"] == "hello"
    task = store.get_by_key("tasks", "id", "task-1")
    assert task is not None
    assert task["runStatus"] == "idle"


@pytest.mark.asyncio
async def test_emit_translated_events_persists_non_default_agent_reply(
    tmp_path,
    monkeypatch,
):
    """A non-default agent (sender != default brand) must append its streamed
    text and finalize (streaming=false, runStatus=idle) on stream end, exactly
    like the default AgentDesk agent."""
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_chat_runtime(monkeypatch, store, task_store)

    class _Tracker:
        async def get_status(self, _run_key: str) -> str:
            return "idle"

    async def _stream():
        yield (
            'data: {"object":"content","type":"text","text":"你好呀！",'
            '"delta":true}\n\n'
        )
        yield (
            'data: {"object":"content","type":"text",'
            '"text":"我是 Readme编写大师","delta":true}\n\n'
        )

    from qwenpaw.agentdesk.models import ChatRequest
    from qwenpaw.agentdesk.stream_protocol import StreamEventSequencer

    await task_store.ensure_task("task-emp")
    await task_store.begin_assistant_message("task-emp", sender="Readme编写大师")
    _mark_running(store, "task-emp")

    payload = ChatRequest(
        task_id="task-emp",
        message="你好",
        employee_name="Readme编写大师",
    )
    sequencer = StreamEventSequencer(task_id="task-emp")
    lines = [
        line
        async for line in agentdesk_chat._emit_translated_events(  # noqa: SLF001
            payload=payload,
            sender="Readme编写大师",
            sequencer=sequencer,
            stream_it=_stream(),
            tracker=_Tracker(),
            run_key="chat-emp",
        )
    ]

    assert any("text_delta" in line and "你好呀" in line for line in lines)
    messages = await task_store.get_messages("task-emp")
    assert messages[-1]["sender"] == "Readme编写大师"
    assert messages[-1]["content"] == "你好呀！我是 Readme编写大师"
    assert messages[-1]["streaming"] is False
    task = store.get_by_key("tasks", "id", "task-emp")
    assert task is not None
    assert task["runStatus"] == "idle"


@pytest.mark.asyncio
async def test_emit_translated_events_persists_artifact_on_write_file(
    tmp_path,
    monkeypatch,
):
    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_chat_runtime(monkeypatch, store, task_store)

    class _Tracker:
        async def get_status(self, _run_key: str) -> str:
            return "idle"

    async def _stream():
        yield (
            'data: {"object":"message","type":"plugin_call","status":"completed",'
            '"content":[{"type":"data","data":{"name":"write_file","call_id":"call-1",'
            '"arguments":{"file_path":"report.md","content":"# Report"}}}]}'
            "\n\n"
        )
        yield (
            'data: {"object":"message","type":"plugin_call_output","status":"completed",'
            '"content":[{"type":"data","data":{"name":"write_file","call_id":"call-1",'
            '"output":"Wrote report.md","state":"success"}}]}'
            "\n\n"
        )

    from qwenpaw.agentdesk.models import ChatRequest
    from qwenpaw.agentdesk.stream_protocol import StreamEventSequencer

    await task_store.ensure_task("task-artifact")
    draft = await task_store.begin_assistant_message("task-artifact", sender="AgentDesk企伴")
    _mark_running(store, "task-artifact")

    payload = ChatRequest(task_id="task-artifact", message="写报告")
    sequencer = StreamEventSequencer(task_id="task-artifact")
    lines = [
        line
        async for line in agentdesk_chat._emit_translated_events(  # noqa: SLF001
            payload=payload,
            sender="AgentDesk企伴",
            sequencer=sequencer,
            stream_it=_stream(),
            tracker=_Tracker(),
            run_key="chat-artifact",
            stream_message_id=str(draft.get("id") or ""),
        )
    ]

    assert any('"type": "artifact"' in line or '"type":"artifact"' in line for line in lines)
    messages = await task_store.get_messages("task-artifact")
    artifacts = messages[-1].get("artifacts") or []
    assert any(
        str(item.get("path") or "") == "report.md"
        for item in artifacts
        if isinstance(item, dict)
    )


@pytest.mark.asyncio
async def test_emit_translated_events_tags_trace_events_with_sender_and_message_id(
    tmp_path,
    monkeypatch,
):
    """Trace/reply_end events must carry speaker attribution for employee chats."""
    import json

    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_chat_runtime(monkeypatch, store, task_store)

    class _Tracker:
        async def get_status(self, _run_key: str) -> str:
            return "idle"

    async def _stream():
        yield (
            'data: {"object":"content","type":"reasoning","text":"分析中",'
            '"delta":true}\n\n'
        )
        yield (
            'data: {"object":"content","type":"text","text":"今日要闻",'
            '"delta":true}\n\n'
        )

    from qwenpaw.agentdesk.models import ChatRequest
    from qwenpaw.agentdesk.stream_protocol import StreamEventSequencer

    await task_store.ensure_task("task-news")
    draft = await task_store.begin_assistant_message(
        "task-news",
        sender="AI新闻采集专家",
    )
    message_id = str(draft["id"])
    _mark_running(store, "task-news")

    payload = ChatRequest(
        task_id="task-news",
        message="新闻",
        employee_name="AI新闻采集专家",
    )
    sequencer = StreamEventSequencer(task_id="task-news")
    lines = [
        line
        async for line in agentdesk_chat._emit_translated_events(  # noqa: SLF001
            payload=payload,
            sender="AI新闻采集专家",
            sequencer=sequencer,
            stream_it=_stream(),
            tracker=_Tracker(),
            run_key="chat-news",
            stream_message_id=message_id,
            agent_id="agent-news",
        )
    ]

    def _parse_sse(line: str) -> dict:
        payload_text = line.strip().removeprefix("data: ").strip()
        return json.loads(payload_text)

    events = [_parse_sse(line) for line in lines if line.startswith("data:")]
    thinking = next(evt for evt in events if evt.get("type") == "thinking_start")
    reply_end = next(evt for evt in events if evt.get("type") == "reply_end")
    assert thinking["sender"] == "AI新闻采集专家"
    assert thinking["message_id"] == message_id
    assert reply_end["sender"] == "AI新闻采集专家"
    assert reply_end["message_id"] == message_id


@pytest.mark.asyncio
async def test_stream_agent_turn_schedules_finalize_watch(tmp_path, monkeypatch):
    """The team leader turn must arm a producer-tied finalize watch so the
    assistant message is finalized / runStatus closed even if the client
    disconnects mid-run (parity with single-agent chat)."""
    from unittest.mock import MagicMock

    from qwenpaw.agentdesk import team_chat
    from qwenpaw.agentdesk.models import ChatRequest
    from qwenpaw.agentdesk.stream_protocol import StreamEventSequencer

    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    monkeypatch.setattr(team_chat, "task_store", task_store)
    _patch_chat_runtime(monkeypatch, store, task_store)

    scheduled: list[dict] = []
    monkeypatch.setattr(
        team_chat,
        "_arm_leader_finalize_watch",
        lambda **kwargs: scheduled.append(kwargs),
    )

    async def ensure_chat_model_stub(_agent_id):
        return (None, None)

    monkeypatch.setattr(team_chat, "ensure_chat_model", ensure_chat_model_stub)
    monkeypatch.setattr(team_chat, "_schedule_sync_task_workspace", lambda *a, **k: None)

    class _ApprovalService:
        async def get_pending_by_session(self, _sid):
            return None

        async def get_pending_by_root_session(self, _sid):
            return []

    monkeypatch.setattr(
        agentdesk_chat,
        "get_approval_service",
        lambda: _ApprovalService(),
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

            return (_empty(), True)

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

    async def get_agent_for_request_stub(_request, *, agent_id):
        return _Workspace()

    monkeypatch.setattr(
        team_chat,
        "get_agent_for_request",
        get_agent_for_request_stub,
    )

    await task_store.ensure_task("task-leader")
    await task_store.begin_assistant_message(
        "task-leader",
        sender="协同小队·leader",
    )

    payload = ChatRequest(task_id="task-leader", message="你好", mode="team")
    sequencer = StreamEventSequencer(task_id="task-leader")
    turn_result: dict = {"final_text": "", "fatal": False}

    _ = [
        line
        async for line in team_chat._stream_agent_turn(  # noqa: SLF001
            payload=payload,
            request=MagicMock(),
            agent_id="lead_x",
            sender="协同小队·leader",
            agent_message="你好",
            sequencer=sequencer,
            session_suffix="leader-native",
            emit_stream_start=True,
            turn_result=turn_result,
        )
    ]

    assert len(scheduled) == 1
    assert scheduled[0]["run_key"] == "chat-leader"
    assert scheduled[0]["task_id"] == "task-leader"


@pytest.mark.asyncio
async def test_team_leader_finalize_watch_closes_task_after_disconnect(
    tmp_path,
    monkeypatch,
):
    """The leader finalize watch is the disconnect/stale-run safety net."""
    from qwenpaw.agentdesk import stream_side_effects, team_leader_runs

    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    monkeypatch.setattr(stream_side_effects, "task_store", task_store)
    monkeypatch.setattr(
        stream_side_effects,
        "commit_task_run_status",
        lambda task_id, status: run_status.commit_task_run_status(
            task_id,
            status,
            persistent_store=store,
        ),
    )

    class _Tracker:
        def __init__(self) -> None:
            self.status = "running"

        async def get_status(self, _run_key: str) -> str:
            return self.status

    await task_store.ensure_task("task-disconnect")
    await task_store.begin_assistant_message(
        "task-disconnect",
        sender="team-leader",
        set_streaming=True,
    )
    await task_store.begin_assistant_message(
        "task-disconnect",
        sender="worker",
        set_streaming=False,
    )
    run_status.commit_task_run_status(
        "task-disconnect",
        "running",
        persistent_store=store,
    )

    tracker = _Tracker()
    team_leader_runs.arm_leader_finalize_watch(
        task_id="task-disconnect",
        run_key="chat-leader",
        tracker=tracker,
    )
    watch = team_leader_runs._leader_finalize_watches["task-disconnect"]  # noqa: SLF001
    tracker.status = "idle"
    await asyncio.wait_for(watch, timeout=1.0)

    assert run_status.task_run_status(
        "task-disconnect",
        persistent_store=store,
    ) == "idle"
    messages = await task_store.get_messages("task-disconnect")
    assert all(not msg.get("streaming") for msg in messages)


@pytest.mark.asyncio
async def test_stream_chat_yields_stream_start_before_attach_or_start(
    tmp_path,
    monkeypatch,
):
    """stream_start must reach the client while native prep still runs."""
    from unittest.mock import AsyncMock, MagicMock

    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    _patch_chat_runtime(monkeypatch, store, task_store)

    events: list[str] = []
    attach_started = asyncio.Event()
    prep_gate = asyncio.Event()

    async def _empty_queue():
        if False:
            yield ""

    async def slow_prep(*_a, **_k):
        attach_started.set()
        await prep_gate.wait()
        channel = MagicMock()
        channel.resolve_session_id = lambda **kw: kw["channel_meta"]["session_id"]
        ws = MagicMock()
        ws.workspace_dir = str(tmp_path)
        ws.channel_manager.get_channel = AsyncMock(return_value=channel)
        ws.chat_manager.get_or_create_chat = AsyncMock(return_value=MagicMock(id="c1"))
        ws.task_tracker.attach_or_start = AsyncMock(
            side_effect=lambda *a, **k: (_empty_queue(), True),
        )
        ws.task_tracker.stream_from_queue = lambda q, _k: q
        ws.task_tracker.get_status = AsyncMock(return_value="idle")
        from qwenpaw.agentdesk.chat import _SingleChatRuntime

        return _SingleChatRuntime(
            workspace=ws,
            mounted_skills=[],
            model_error=None,
            console_channel=channel,
        )

    monkeypatch.setattr(agentdesk_chat, "_prepare_single_chat_runtime_fast", slow_prep)
    monkeypatch.setattr(agentdesk_chat, "_prepare_single_chat_runtime", slow_prep)
    monkeypatch.setattr(agentdesk_chat, "resolve_agent_id", lambda _n: "agent-1")
    monkeypatch.setattr(agentdesk_chat, "display_sender", lambda _n, _a: "bot")
    monkeypatch.setattr(agentdesk_chat, "_schedule_task_chat_target", lambda *_a: None)
    monkeypatch.setattr(agentdesk_chat, "_schedule_sync_task_workspace", lambda *_a: None)
    monkeypatch.setattr(agentdesk_chat, "_commit_task_run_status", lambda *_a: None)
    monkeypatch.setattr(
        agentdesk_chat,
        "resolve_chat_user_messages",
        lambda *_a, **_k: ("hi", "hi"),
    )
    monkeypatch.setattr(agentdesk_chat, "_schedule_run_finalize_watch", lambda **_k: None)

    class _ApprovalService:
        async def get_pending_by_session(self, _sid):
            return None

        async def get_pending_by_root_session(self, _sid):
            return []

    monkeypatch.setattr(
        agentdesk_chat,
        "get_approval_service",
        lambda: _ApprovalService(),
    )

    from qwenpaw.agentdesk.models import ChatRequest

    payload = ChatRequest(task_id="task-fast", message="hello")
    request = MagicMock()
    request.state = MagicMock()
    request.state.agent_id = None

    async def collect():
        async for line in agentdesk_chat._stream_chat(payload, request):
            events.append(line)
            if "stream_start" in line:
                break

    collector = asyncio.create_task(collect())
    await asyncio.wait_for(attach_started.wait(), timeout=2.0)
    assert any("stream_start" in e for e in events)
    prep_gate.set()
    await asyncio.wait_for(collector, timeout=2.0)


def test_get_task_exposes_run_status(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from qwenpaw.agentdesk.chat import router as chat_router
    from qwenpaw.agentdesk.router import api_router, router

    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr("qwenpaw.agentdesk.task_routes.store", store)

    task = store.ensure_task("task-refresh")
    task["runStatus"] = "running"
    store.upsert_by_key("tasks", "id", "task-refresh", task)

    app = FastAPI()
    app.include_router(router)
    app.include_router(api_router)
    app.include_router(chat_router)
    client = TestClient(app)

    response = client.get("/api/tasks/task-refresh")
    assert response.status_code == 200
    body = response.json()
    assert body["runStatus"] == "running"


@pytest.mark.asyncio
async def test_schedule_task_run_status_respects_commit_idle(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")

    stale_seq = run_status._bump_run_status_seq("task-race")  # noqa: SLF001
    await asyncio.to_thread(
        run_status.set_task_run_status,
        "task-race",
        "running",
        seq=stale_seq,
        persistent_store=store,
    )
    run_status.commit_task_run_status("task-race", "idle", persistent_store=store)
    await asyncio.to_thread(
        run_status.set_task_run_status,
        "task-race",
        "running",
        seq=stale_seq,
        persistent_store=store,
    )

    task = store.get_by_key("tasks", "id", "task-race")
    assert task is not None
    assert task["runStatus"] == "idle"


@pytest.mark.asyncio
async def test_get_task_prefers_live_task_store_messages(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from qwenpaw.agentdesk.router import api_router, router

    store = AgentDeskStore(tmp_path / "store.json")
    task_store = TaskStore(persistent_store=store)
    monkeypatch.setattr("qwenpaw.agentdesk.task_routes.store", store)
    monkeypatch.setattr("qwenpaw.agentdesk.task_store.task_store", task_store)

    task = store.ensure_task("task-live")
    task["messages"] = [
        {
            "id": "a1",
            "role": "assistant",
            "content": "stale disk snapshot",
            "streaming": True,
        },
    ]
    store.upsert_by_key("tasks", "id", "task-live", task)

    await task_store.ensure_task("task-live")
    await task_store.begin_assistant_message("task-live", sender="bot")
    await task_store.append_assistant_delta("task-live", "live in-memory reply")

    app = FastAPI()
    app.include_router(router)
    app.include_router(api_router)
    client = TestClient(app)

    response = client.get("/api/tasks/task-live")
    assert response.status_code == 200
    messages = response.json()["messages"]
    assert messages[-1]["content"] == "live in-memory reply"
