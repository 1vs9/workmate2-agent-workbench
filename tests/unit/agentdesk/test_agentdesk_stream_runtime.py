# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from qwenpaw.agentdesk import stream_runtime


class _FakeApprovalService:
    async def get_pending_by_session(self, task_id: str):
        assert task_id == "task-1"
        return None

    async def get_pending_by_root_session(self, task_id: str):
        assert task_id == "task-1"
        return [
            SimpleNamespace(
                status="pending",
                request_id="req-1",
                tool_name="shell",
                severity="medium",
                result_summary="needs approval",
            ),
        ]


async def test_pending_approval_event_uses_root_session_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        stream_runtime,
        "get_approval_service",
        lambda: _FakeApprovalService(),
    )

    assert await stream_runtime.pending_approval_event("task-1") == {
        "type": "approval_required",
        "task_id": "task-1",
        "request_id": "req-1",
        "tool_name": "shell",
        "severity": "medium",
        "detail": "needs approval",
    }


async def test_pending_approval_event_ignores_empty_task_id() -> None:
    assert await stream_runtime.pending_approval_event("") is None


def test_tag_turn_event_fills_missing_identity_fields() -> None:
    tagged = stream_runtime.tag_turn_event(
        {"type": "message", "sender": "", "actor_id": "", "message_id": ""},
        sender="Analyst",
        agent_id="agent-1",
        message_id="msg-1",
    )

    assert tagged["sender"] == "Analyst"
    assert tagged["actor_id"] == "agent-1"
    assert tagged["message_id"] == "msg-1"


def test_tag_turn_event_preserves_existing_identity_fields() -> None:
    tagged = stream_runtime.tag_turn_event(
        {"type": "message", "sender": "Existing", "actor_id": "a", "message_id": "m"},
        sender="Analyst",
        agent_id="agent-1",
        message_id="msg-1",
    )

    assert tagged["sender"] == "Existing"
    assert tagged["actor_id"] == "a"
    assert tagged["message_id"] == "m"


async def test_iter_with_heartbeat_yields_none_while_waiting() -> None:
    async def _slow_stream():
        await asyncio.sleep(0.03)
        yield "chunk"

    items = []
    async for item in stream_runtime.iter_with_heartbeat(
        _slow_stream().__aiter__(),
        interval_s=0.01,
    ):
        items.append(item)

    assert None in items
    assert items[-1] == "chunk"
