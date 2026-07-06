# -*- coding: utf-8 -*-
"""Ordered AgentDesk stream event envelopes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

_TERMINAL_EVENT_TYPES = frozenset({"done", "error"})
_TEAM_EVENT_TYPES = frozenset(
    {"team_phase", "worker_start", "worker_done", "plan_update", "timeline_entry"},
)


def infer_stream_source(evt: dict[str, Any]) -> str:
    evt_type = str(evt.get("type") or "")
    if evt_type in _TEAM_EVENT_TYPES:
        return "team"
    if evt_type in {"text_delta", "message"}:
        return "assistant"
    if evt_type == "trace":
        return "runtime"
    if evt_type == "artifact":
        return "artifact"
    return "chat"


_ARTIFACT_PAYLOAD_KEYS = (
    "type",
    "kind",
    "role",
    "path",
    "name",
    "summary",
    "op",
    "tool",
)


def artifact_payload_from_evt(evt: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a stream ``artifact`` event for message persistence."""
    if str(evt.get("type") or "") != "artifact":
        return None
    payload = {
        key: evt.get(key) for key in _ARTIFACT_PAYLOAD_KEYS if evt.get(key) is not None
    }
    if not str(payload.get("path") or "").strip():
        return None
    return payload


def infer_source_member(evt: dict[str, Any]) -> str | None:
    for key in ("source_member", "worker", "sender"):
        value = evt.get(key)
        if value:
            return str(value)
    return None


@dataclass
class StreamEventSequencer:
    """Attach monotonic ordering metadata to SSE event payloads."""

    task_id: str
    round_id: str | None = None
    next_seq: int = 0

    def __post_init__(self) -> None:
        if not self.round_id:
            self.round_id = uuid.uuid4().hex

    def wrap(
        self,
        evt: dict[str, Any],
        *,
        source: str | None = None,
        source_member: str | None = None,
    ) -> dict[str, Any]:
        payload = dict(evt)
        payload.setdefault("task_id", self.task_id)
        payload.setdefault("round_id", self.round_id)
        payload.setdefault("seq", self.next_seq)
        payload.setdefault("source", source or infer_stream_source(payload))
        member = source_member or infer_source_member(payload)
        if member:
            payload.setdefault("source_member", member)
        payload.setdefault("is_terminal", self._is_terminal(payload))
        self.next_seq += 1
        return payload

    @staticmethod
    def _is_terminal(evt: dict[str, Any]) -> bool:
        evt_type = str(evt.get("type") or "")
        if evt_type == "error":
            return evt.get("fatal") is not False
        if evt_type in _TERMINAL_EVENT_TYPES:
            return True
        if evt_type == "team_phase" and str(evt.get("phase") or "") == "done":
            return True
        return False
