# -*- coding: utf-8 -*-
from __future__ import annotations

import json

from qwenpaw.agentdesk import chat_event_stream
from qwenpaw.agentdesk.models import ChatRequest
from qwenpaw.agentdesk.stream_protocol import StreamEventSequencer


class _TaskStore:
    def __init__(self) -> None:
        self.deltas: list[str] = []
        self.artifacts: list[dict] = []
        self.finalized: list[tuple[str, str | None]] = []

    async def reset_assistant_content(self, _task_id: str) -> None:
        self.deltas.clear()

    async def append_assistant_delta(self, _task_id: str, content: str) -> None:
        self.deltas.append(content)

    async def append_assistant_artifacts(self, _task_id: str, artifacts: list[dict], **_kwargs) -> None:
        self.artifacts.extend(artifacts)

    async def finalize_assistant_message(self, task_id: str, *, content: str | None) -> None:
        self.finalized.append((task_id, content))

    async def get_messages(self, _task_id: str) -> list[dict[str, str]]:
        return [{"role": "assistant", "content": "".join(self.deltas)}]


async def test_emit_translated_events_emits_approval_and_done() -> None:
    task_store = _TaskStore()
    committed: list[tuple[str, str]] = []
    persisted: list[dict] = []

    async def pending_approval(_task_id: str) -> dict:
        return {
            "type": "approval_required",
            "task_id": "task-1",
            "request_id": "req-1",
        }

    async def stream():
        yield 'data: {"object":"content","type":"text","text":"ok","delta":true}\n\n'

    payload = ChatRequest(task_id="task-1", message="hi")
    lines = [
        line
        async for line in chat_event_stream.emit_translated_events(
            payload=payload,
            sender="bot",
            sequencer=StreamEventSequencer(task_id="task-1"),
            stream_it=stream(),
            task_store_obj=task_store,
            pending_approval_event_fn=pending_approval,
            approval_poll_s=0.01,
            schedule_persist_trace_event_fn=lambda _task_id, evt: persisted.append(evt),
            persist_trace_event_fn=lambda _task_id, evt: _persist(persisted, evt),
            commit_task_run_status_fn=lambda task_id, status: committed.append((task_id, status)),
        )
    ]

    events = [json.loads(line.removeprefix("data: ").strip()) for line in lines]
    assert any(evt.get("type") == "approval_required" for evt in events)
    assert events[-1]["type"] == "done"
    assert task_store.finalized == [("task-1", "ok")]
    assert committed == [("task-1", "idle")]
    assert persisted[-1]["type"] == "reply_end"


async def test_emit_translated_events_emits_fatal_error_once() -> None:
    task_store = _TaskStore()
    persisted: list[dict] = []
    committed: list[tuple[str, str]] = []

    async def stream():
        yield 'data: {"error":"Model unknown execution failed"}\n\n'

    payload = ChatRequest(task_id="task-1", message="hi")
    lines = [
        line
        async for line in chat_event_stream.emit_translated_events(
            payload=payload,
            sender="bot",
            sequencer=StreamEventSequencer(task_id="task-1"),
            stream_it=stream(),
            task_store_obj=task_store,
            pending_approval_event_fn=_none,
            schedule_persist_trace_event_fn=lambda _task_id, evt: persisted.append(evt),
            persist_trace_event_fn=lambda _task_id, evt: _persist(persisted, evt),
            commit_task_run_status_fn=lambda task_id, status: committed.append((task_id, status)),
        )
    ]

    events = [json.loads(line.removeprefix("data: ").strip()) for line in lines]
    fatal_errors = [event for event in events if event.get("type") == "error"]
    assert len(fatal_errors) == 1
    assert committed == [("task-1", "idle")]


async def test_emit_translated_events_persists_write_file_artifact() -> None:
    task_store = _TaskStore()
    persisted: list[dict] = []

    async def stream():
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

    payload = ChatRequest(task_id="task-artifact", message="write report")
    lines = [
        line
        async for line in chat_event_stream.emit_translated_events(
            payload=payload,
            sender="bot",
            sequencer=StreamEventSequencer(task_id="task-artifact"),
            stream_it=stream(),
            stream_message_id="msg-1",
            task_store_obj=task_store,
            pending_approval_event_fn=_none,
            schedule_persist_trace_event_fn=lambda _task_id, evt: persisted.append(evt),
            persist_trace_event_fn=lambda _task_id, evt: _persist(persisted, evt),
            commit_task_run_status_fn=lambda *_args: None,
        )
    ]

    events = [json.loads(line.removeprefix("data: ").strip()) for line in lines]
    assert any(event.get("type") == "artifact" for event in events)
    assert any(item.get("path") == "report.md" for item in task_store.artifacts)


async def test_emit_translated_events_tags_trace_with_turn_identity() -> None:
    task_store = _TaskStore()
    persisted: list[dict] = []

    async def stream():
        yield (
            'data: {"object":"content","type":"reasoning","text":"thinking",'
            '"delta":true}\n\n'
        )
        yield 'data: {"object":"content","type":"text","text":"answer","delta":true}\n\n'

    payload = ChatRequest(task_id="task-news", message="news")
    lines = [
        line
        async for line in chat_event_stream.emit_translated_events(
            payload=payload,
            sender="Researcher",
            sequencer=StreamEventSequencer(task_id="task-news"),
            stream_it=stream(),
            stream_message_id="msg-1",
            agent_id="agent-news",
            task_store_obj=task_store,
            pending_approval_event_fn=_none,
            schedule_persist_trace_event_fn=lambda _task_id, evt: persisted.append(evt),
            persist_trace_event_fn=lambda _task_id, evt: _persist(persisted, evt),
            commit_task_run_status_fn=lambda *_args: None,
        )
    ]

    events = [json.loads(line.removeprefix("data: ").strip()) for line in lines]
    thinking = next(event for event in events if event.get("type") == "thinking_start")
    reply_end = next(event for event in events if event.get("type") == "reply_end")
    for event in (thinking, reply_end):
        assert event["sender"] == "Researcher"
        assert event["message_id"] == "msg-1"
        assert event["actor_id"] == "agent-news"
    assert persisted[-1]["type"] == "reply_end"


async def test_emit_translated_events_survives_trace_schedule_failure() -> None:
    task_store = _TaskStore()
    committed: list[tuple[str, str]] = []

    def fail_schedule(*_args, **_kwargs) -> None:
        raise PermissionError("store locked")

    async def stream():
        yield (
            'data: {"object":"message","type":"plugin_call","status":"completed",'
            '"content":[{"type":"data","data":{"name":"read_file","call_id":"call-1",'
            '"arguments":{"path":"README.md"}}}]}'
            "\n\n"
        )
        yield 'data: {"object":"content","type":"text","text":"ok","delta":true}\n\n'

    payload = ChatRequest(task_id="task-locked", message="read")
    lines = [
        line
        async for line in chat_event_stream.emit_translated_events(
            payload=payload,
            sender="bot",
            sequencer=StreamEventSequencer(task_id="task-locked"),
            stream_it=stream(),
            task_store_obj=task_store,
            pending_approval_event_fn=_none,
            schedule_persist_trace_event_fn=fail_schedule,
            persist_trace_event_fn=lambda *_args, **_kwargs: _none(),
            commit_task_run_status_fn=lambda task_id, status: committed.append((task_id, status)),
        )
    ]

    events = [json.loads(line.removeprefix("data: ").strip()) for line in lines]
    assert any(event.get("type") == "text_delta" and event.get("content") == "ok" for event in events)
    assert events[-1]["type"] == "done"
    assert task_store.finalized == [("task-locked", "ok")]
    assert committed == [("task-locked", "idle")]


async def _none(*_args, **_kwargs):
    return None


async def _persist(target: list[dict], evt: dict) -> None:
    target.append(evt)
