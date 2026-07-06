# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.agentdesk import trace_events
from qwenpaw.agentdesk.store import AgentDeskStore


def test_to_persisted_trace_normalizes_trace_event() -> None:
    assert trace_events.to_persisted_trace({"type": "reply_start", "label": "go"}) == {
        "type": "trace",
        "label": "go",
        "step": "reply_start",
    }
    assert trace_events.to_persisted_trace({"type": "text_delta"}) is None
    existing = {"type": "trace", "step": "custom"}
    assert trace_events.to_persisted_trace(existing) is existing


def test_slim_event_for_client_omits_large_browser_snapshot() -> None:
    snapshot = "\n".join(f"button role=button [ref={idx}]" for idx in range(80))
    event = {
        "type": "trace",
        "step": "tool_result_end",
        "tool_name": "browser_use",
        "detail": snapshot,
        "result": {"browser_snapshot": snapshot, "url": "https://example.test"},
    }

    slimmed = trace_events.slim_event_for_client(event)

    assert slimmed["detail"] == "[browser snapshot omitted]"
    assert slimmed["result"]["browser_snapshot"] == "[browser snapshot omitted]"
    assert slimmed["result"]["url"] == "https://example.test"


async def test_task_events_snapshot_reads_store_events(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    store.ensure_task("task-1")
    store.append_task_event("task-1", {"type": "trace", "step": "reply_start"})
    monkeypatch.setattr(trace_events, "agentdesk_store", store)

    snapshot = await trace_events.task_events_snapshot("task-1")

    assert len(snapshot) == 1
    assert snapshot[0]["type"] == "trace"
    assert snapshot[0]["step"] == "reply_start"
    assert "created_at" in snapshot[0]
