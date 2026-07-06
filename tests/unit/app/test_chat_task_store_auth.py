# -*- coding: utf-8 -*-
"""Authorization tests for background ``/console/chat/task`` polling."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from qwenpaw.app.chat_task_store import (
    ChatTaskRecord,
    ChatTaskStore,
    build_task_allowed_readers,
)
from qwenpaw.app.routers.console import (
    _normalize_task_timeout,
    _resolve_request_agent_id,
)


class _Request:
    def __init__(self, *, agent_id: str | None = None, header_agent: str | None = None):
        self.state = type("State", (), {"agent_id": agent_id})()
        self.headers = {"X-Agent-Id": header_agent} if header_agent else {}


def test_build_task_allowed_readers_includes_executor_and_submitter() -> None:
    allowed = build_task_allowed_readers(
        executor_agent_id="worker-a",
        request_data={
            "request_context": {"root_agent_id": "leader-b"},
        },
    )
    assert allowed == frozenset({"worker-a", "leader-b"})


def test_chat_task_record_is_readable_by_bound_agents_only() -> None:
    record = ChatTaskRecord(
        task_id="abc",
        executor_agent_id="worker-a",
        allowed_reader_agent_ids=frozenset({"worker-a", "leader-b"}),
    )
    assert record.is_readable_by("worker-a")
    assert record.is_readable_by("leader-b")
    assert not record.is_readable_by("intruder")


@pytest.mark.asyncio
async def test_chat_task_store_create_records_allowed_readers() -> None:
    store = ChatTaskStore()
    record = await store.create(
        executor_agent_id="worker-a",
        allowed_reader_agent_ids=frozenset({"worker-a", "leader-b"}),
    )
    loaded = await store.get(record.task_id)
    assert loaded is not None
    assert loaded.executor_agent_id == "worker-a"
    assert loaded.is_readable_by("leader-b")
    assert not loaded.is_readable_by("other")


def test_resolve_request_agent_id_prefers_state_over_header() -> None:
    request = _Request(agent_id="state-agent", header_agent="header-agent")
    assert _resolve_request_agent_id(request) == "state-agent"


@pytest.mark.parametrize(
    "raw_timeout",
    [float("inf"), float("nan"), 0, -1],
)
def test_normalize_task_timeout_rejects_non_finite_or_non_positive(
    raw_timeout: float,
) -> None:
    with pytest.raises(HTTPException) as excinfo:
        _normalize_task_timeout(raw_timeout)
    assert excinfo.value.status_code == 400


def test_normalize_task_timeout_accepts_finite_positive() -> None:
    assert _normalize_task_timeout(120) == 120.0
