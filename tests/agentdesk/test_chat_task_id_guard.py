# -*- coding: utf-8 -*-
"""Tests for the AgentDesk chat-stream ``task_id`` guard.

Every AgentDesk conversation maps 1:1 to a QwenPaw session via
``meta.session_id = task_id``. An empty / whitespace ``task_id`` would collapse
every conversation onto the shared ``console:agentdesk`` session and cause
cross-talk between chats, so the endpoint must reject it up front.
"""

import pytest
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from unittest.mock import MagicMock

from qwenpaw.agentdesk.chat import post_chat_stream
from qwenpaw.agentdesk.models import ChatRequest


class _Request:
    """Minimal stand-in for ``fastapi.Request`` (never iterated here)."""

    state = MagicMock()

    async def is_disconnected(self) -> bool:  # pragma: no cover - not exercised
        return False


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_task_id", ["", "   ", "\t\n"])
async def test_post_chat_stream_rejects_blank_task_id(bad_task_id: str) -> None:
    payload = ChatRequest(task_id=bad_task_id, message="hi")

    with pytest.raises(HTTPException) as excinfo:
        await post_chat_stream(payload, _Request())  # type: ignore[arg-type]

    assert excinfo.value.status_code == 400
    assert "task_id" in str(excinfo.value.detail)


@pytest.mark.asyncio
async def test_post_chat_stream_accepts_real_task_id() -> None:
    # A valid task_id must not raise. The async generator passed to
    # StreamingResponse is constructed lazily and never iterated here, so no
    # chat side effects run.
    payload = ChatRequest(task_id="task-123", message="hi")

    response = await post_chat_stream(payload, _Request())  # type: ignore[arg-type]

    assert isinstance(response, StreamingResponse)
    assert response.media_type == "text/event-stream"
