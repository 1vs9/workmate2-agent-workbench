# -*- coding: utf-8 -*-
"""Tests for agent discovery and inter-agent chat helpers."""

from __future__ import annotations

import asyncio

import httpx
from agentscope.tool import Toolkit

from agentscope.tool import FunctionTool
from qwenpaw.agents.tools import agent_management
from qwenpaw.runtime.worker_stream_bus import WORKER_STREAM_DONE_SENTINEL


class _FakeResponse:
    def __init__(self, json_data=None, lines=None, status_code=200):
        self._json_data = json_data or {}
        self._lines = lines or []
        self.status_code = status_code
        self.request = httpx.Request("GET", "http://test/api")

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "request failed",
                request=self.request,
                response=httpx.Response(
                    self.status_code,
                    request=self.request,
                ),
            )

    def iter_lines(self):
        yield from self._lines


class _FakeStreamContext:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self._response

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeClient:
    def __init__(
        self,
        get_response=None,
        post_response=None,
        stream_response=None,
    ):
        self.get_response = get_response or _FakeResponse()
        self.post_response = post_response or _FakeResponse()
        self.stream_response = stream_response or _FakeResponse(lines=[])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, *_args, **_kwargs):
        return self.get_response

    def post(self, *_args, **_kwargs):
        return self.post_response

    def stream(self, *_args, **_kwargs):
        return _FakeStreamContext(self.stream_response)


def test_build_agent_chat_request_adds_identity_prefix():
    (
        session_id,
        payload,
        prefix_added,
    ) = agent_management.build_agent_chat_request(
        "bot_b",
        "Need a summary",
        from_agent="bot_a",
    )

    assert session_id.startswith("bot_a:to:bot_b:")
    assert prefix_added is True
    assert payload["session_id"] == session_id
    assert payload["input"][0]["content"][0]["text"].startswith(
        "[Agent bot_a requesting] ",
    )


def test_build_agent_chat_request_discovers_calling_agent(monkeypatch):
    monkeypatch.setattr(
        agent_management,
        "resolve_calling_agent_id",
        lambda _from_agent=None: "auto_bot",
    )

    (
        session_id,
        payload,
        prefix_added,
    ) = agent_management.build_agent_chat_request(
        "bot_b",
        "Need a summary",
        from_agent=None,
    )

    assert session_id.startswith("auto_bot:to:bot_b:")
    assert payload["input"][0]["content"][0]["text"].startswith(
        "[Agent auto_bot requesting] ",
    )
    assert prefix_added is True


def test_build_agent_chat_request_reuses_session_id_when_provided():
    (
        session_id,
        payload,
        prefix_added,
    ) = agent_management.build_agent_chat_request(
        "bot_b",
        "Need a summary",
        session_id="existing-session",
        from_agent="bot_a",
    )

    assert session_id == "existing-session"
    assert payload["session_id"] == "existing-session"
    assert prefix_added is True


def test_list_agents_data_uses_shared_client(monkeypatch):
    fake_client = _FakeClient(
        get_response=_FakeResponse(
            json_data={
                "agents": [
                    {"id": "default", "name": "Default", "enabled": True},
                ],
            },
        ),
    )
    monkeypatch.setattr(
        agent_management,
        "create_agent_api_client",
        lambda _base_url: fake_client,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.settings.is_agentdesk_enabled",
        lambda: False,
    )

    result = agent_management.list_agents_data("http://127.0.0.1:8088")

    assert result["agents"][0]["id"] == "default"


def test_list_agents_data_hides_builtin_qa_in_agentdesk(monkeypatch):
    fake_client = _FakeClient(
        get_response=_FakeResponse(
            json_data={
                "agents": [
                    {"id": "default", "name": "AgentDesk企伴", "enabled": True},
                    {
                        "id": "QwenPaw_QA_Agent_0.2",
                        "name": "QA Agent",
                        "enabled": True,
                    },
                    {"id": "emp_analyst", "name": "Analyst", "enabled": True},
                ],
            },
        ),
    )
    monkeypatch.setattr(
        agent_management,
        "create_agent_api_client",
        lambda _base_url: fake_client,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.settings.is_agentdesk_enabled",
        lambda: True,
    )

    result = agent_management.list_agents_data("http://127.0.0.1:8088")

    listed_ids = {agent["id"] for agent in result["agents"]}
    assert listed_ids == {"emp_analyst"}


def test_agent_exists_blocks_builtin_qa_in_agentdesk(monkeypatch):
    monkeypatch.setattr(
        agent_management,
        "list_agents_data",
        lambda _base_url=None: {
            "agents": [
                {
                    "id": "QwenPaw_QA_Agent_0.2",
                    "name": "QA Agent",
                    "enabled": True,
                },
            ],
        },
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.settings.is_agentdesk_enabled",
        lambda: True,
    )

    assert agent_management.agent_exists("QwenPaw_QA_Agent_0.2") is False


async def test_chat_with_agent_blocks_builtin_qa_in_agentdesk(monkeypatch):
    monkeypatch.setattr(
        agent_management,
        "resolve_agent_target",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        agent_management,
        "_available_agent_targets",
        lambda *_args, **_kwargs: "",
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.settings.is_agentdesk_enabled",
        lambda: True,
    )

    response = await agent_management.chat_with_agent(
        to_agent="QwenPaw_QA_Agent_0.2",
        text="What model are you using?",
    )

    assert "not exists" in response.content[0].text


def test_resolve_agent_target_matches_by_id_and_display_name(monkeypatch):
    monkeypatch.setattr(
        agent_management,
        "list_agents_data",
        lambda _base_url=None: {
            "agents": [
                {"id": "emp_planner", "name": "规划者"},
                {"id": "emp_searcher", "name": "研究员"},
            ],
        },
    )

    assert agent_management.resolve_agent_target("emp_planner") == "emp_planner"
    assert agent_management.resolve_agent_target("规划者") == "emp_planner"
    assert agent_management.resolve_agent_target("研究员") == "emp_searcher"
    assert agent_management.resolve_agent_target("EMP_PLANNER") == "emp_planner"


def test_resolve_agent_target_returns_none_for_invented_id(monkeypatch):
    monkeypatch.setattr(
        agent_management,
        "list_agents_data",
        lambda _base_url=None: {
            "agents": [
                {"id": "emp_planner", "name": "规划者"},
            ],
        },
    )

    assert agent_management.resolve_agent_target("planner_5051d9f4") is None


def test_extract_agent_ids_normalizes_values():
    result = agent_management.extract_agent_ids(
        {
            "agents": [
                {"id": "bot_a"},
                {"id": "bot_b"},
                {"id": None},
                "invalid",
            ],
        },
    )

    assert result == {"bot_a", "bot_b"}


def test_resolve_agent_api_base_url_uses_last_api(monkeypatch):
    monkeypatch.setattr(
        agent_management,
        "read_last_api",
        lambda: ("192.168.1.8", 18088),
    )

    result = agent_management.resolve_agent_api_base_url()

    assert result == "http://192.168.1.8:18088"


def test_resolve_agent_api_base_url_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(agent_management, "read_last_api", lambda: None)

    result = agent_management.resolve_agent_api_base_url()

    assert result == agent_management.DEFAULT_AGENT_API_BASE_URL


def test_collect_final_agent_chat_response_keeps_last_sse_payload(monkeypatch):
    fake_lines = [
        'data: {"output": [{"content": [{"type": "text", "text": "first"}]}]}',
        (
            'data: {"output": [{"content": '
            '[{"type": "text", "text": "second"}]}]}'
        ),
    ]
    fake_client = _FakeClient(stream_response=_FakeResponse(lines=fake_lines))
    monkeypatch.setattr(
        agent_management,
        "create_agent_api_client",
        lambda _base_url, default_timeout=30: fake_client,
    )

    result = agent_management.collect_final_agent_chat_response(
        "http://127.0.0.1:8088",
        {"session_id": "sid", "input": []},
        "bot_b",
        30,
    )

    assert result is not None
    assert agent_management.extract_agent_text_content(result) == "second"


def test_extract_agent_text_content_promotes_reasoning_when_no_text():
    result = {
        "output": [
            {
                "content": [
                    {"type": "reasoning", "text": "思考结论"},
                ],
            },
        ],
    }
    assert (
        agent_management.extract_agent_text_content(result) == "思考结论"
    )


def test_is_empty_agent_reply_text():
    assert agent_management.is_empty_agent_reply_text("(No text content in response)")
    assert not agent_management.is_empty_agent_reply_text("hello")


async def test_collect_final_agent_chat_response_publishes_reply_to_bus(
    monkeypatch,
):
    # The worker's whole SSE stream — including its final reply text — must be
    # forwarded to the worker bus so the team stream can surface the worker's
    # answer (not just its trace) live under its own bubble.
    from qwenpaw.runtime.worker_stream_bus import worker_stream_bus

    fake_lines = [
        (
            'data: {"object": "content", "type": "text", '
            '"delta": true, "text": "hello"}'
        ),
        'data: {"output": [{"content": [{"type": "text", "text": "hello"}]}]}',
    ]
    fake_client = _FakeClient(stream_response=_FakeResponse(lines=fake_lines))
    monkeypatch.setattr(
        agent_management,
        "create_agent_api_client",
        lambda _base_url, default_timeout=30: fake_client,
    )

    queue = worker_stream_bus.subscribe("root:sess")
    try:
        result = agent_management.collect_final_agent_chat_response(
            None,
            {"session_id": "sid", "input": []},
            "bot_b",
            30,
            publish_key="root:sess",
        )
        # Let the cross-thread-safe publish callbacks run on this loop.
        await asyncio.sleep(0)
        delivered = []
        while not queue.empty():
            delivered.append(queue.get_nowait())
    finally:
        worker_stream_bus.unsubscribe("root:sess", queue)

    assert result is not None
    # Every published item is a (worker_agent_id, raw_sse_line) tuple.
    assert delivered
    assert all(
        isinstance(item, tuple) and item[0] == "bot_b" for item in delivered
    )
    assert [item[1] for item in delivered[:-1]] == fake_lines
    assert delivered[-1][1] == WORKER_STREAM_DONE_SENTINEL
    # The worker's reply text is among the forwarded lines.
    assert any("hello" in item[1] for item in delivered)


def test_collect_final_agent_chat_response_skips_publish_without_subscriber(
    monkeypatch,
):
    # No subscriber => no publishing work, but the final payload is still
    # collected and returned to the delegating caller.
    fake_lines = [
        'data: {"output": [{"content": [{"type": "text", "text": "done"}]}]}',
    ]
    fake_client = _FakeClient(stream_response=_FakeResponse(lines=fake_lines))
    monkeypatch.setattr(
        agent_management,
        "create_agent_api_client",
        lambda _base_url, default_timeout=30: fake_client,
    )

    published: list = []
    monkeypatch.setattr(
        agent_management.worker_stream_bus,
        "publish",
        lambda *args, **kwargs: published.append(args),
    )

    result = agent_management.collect_final_agent_chat_response(
        None,
        {"session_id": "sid", "input": []},
        "bot_b",
        30,
        publish_key="nobody-listening",
    )

    assert result is not None
    assert agent_management.extract_agent_text_content(result) == "done"
    assert published == []


async def test_agent_management_tools_can_be_registered_in_toolkit():
    toolkit = Toolkit(
        tools=[
            FunctionTool(agent_management.list_agents),
            FunctionTool(agent_management.chat_with_agent),
        ],
    )

    schemas = await toolkit.get_tool_schemas()
    schema_names = {schema["function"]["name"] for schema in schemas}

    assert "list_agents" in schema_names
    assert "chat_with_agent" in schema_names


async def test_list_agents_uses_to_thread(monkeypatch):
    monkeypatch.setattr(
        agent_management,
        "list_agents_data",
        lambda _base_url: {"agents": [{"id": "bot_a"}]},
    )

    calls = []

    async def fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    monkeypatch.setattr(agent_management.asyncio, "to_thread", fake_to_thread)

    response = await agent_management.list_agents()

    assert calls
    assert calls[0][0] is agent_management.list_agents_data
    assert '"id": "bot_a"' in response.content[0].text


async def test_check_agent_task_formats_finished_background_result(
    monkeypatch,
):
    monkeypatch.setattr(
        agent_management,
        "get_agent_chat_task_status",
        lambda *_args, **_kwargs: {
            "status": "finished",
            "result": {
                "status": "completed",
                "session_id": "sid-1",
                "output": [
                    {
                        "content": [
                            {"type": "text", "text": "Background reply"},
                        ],
                    },
                ],
            },
        },
    )

    response = await agent_management.check_agent_task("task-1")

    text = response.content[0].text
    assert "[TASK_ID: task-1]" in text
    assert "Background reply" in text


async def test_chat_with_agent_uses_to_thread_for_final_mode(monkeypatch):
    monkeypatch.setattr(
        agent_management,
        "collect_final_agent_chat_response",
        lambda *_args, **_kwargs: {
            "output": [
                {
                    "content": [
                        {"type": "text", "text": "reply from peer"},
                    ],
                },
            ],
        },
    )

    calls = []

    async def fake_to_thread(func, *args, **kwargs):
        calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    monkeypatch.setattr(agent_management.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(
        agent_management,
        "resolve_calling_agent_id",
        lambda _from_agent=None: "auto_bot",
    )
    monkeypatch.setattr(
        agent_management,
        "resolve_agent_target",
        lambda _to_agent, _base_url=None: "bot_b",
    )

    response = await agent_management.chat_with_agent(
        to_agent="bot_b",
        text="Need help",
    )

    assert calls
    assert calls[-1][0] is agent_management.collect_final_agent_chat_response
    assert "reply from peer" in response.content[0].text


async def test_chat_with_agent_normalizes_agent_ids(monkeypatch):
    captured = {}

    def fake_collect_final(
        _base_url,
        request_payload,
        to_agent,
        _timeout,
        _publish_key=None,
    ):
        captured["to_agent"] = to_agent
        captured["session_id"] = request_payload["session_id"]
        captured["text"] = request_payload["input"][0]["content"][0]["text"]
        return {
            "output": [
                {
                    "content": [
                        {"type": "text", "text": "reply from peer"},
                    ],
                },
            ],
        }

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(
        agent_management,
        "collect_final_agent_chat_response",
        fake_collect_final,
    )
    monkeypatch.setattr(agent_management.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(
        agent_management,
        "resolve_agent_target",
        lambda _to_agent, _base_url=None: "bot_b",
    )
    monkeypatch.setattr(
        agent_management,
        "resolve_calling_agent_id",
        lambda _from_agent=None: "bot_a",
    )

    response = await agent_management.chat_with_agent(
        to_agent='  "bot_b"  ',
        text="Need help",
    )

    assert captured["to_agent"] == "bot_b"
    assert captured["session_id"].startswith("bot_a:to:bot_b:")
    assert captured["text"].startswith("[Agent bot_a requesting] ")
    assert "reply from peer" in response.content[0].text


async def test_chat_with_agent_returns_clear_error_when_agent_missing(
    monkeypatch,
):
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(agent_management.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(
        agent_management,
        "resolve_agent_target",
        lambda _to_agent, _base_url=None: None,
    )
    monkeypatch.setattr(
        agent_management,
        "_available_agent_targets",
        lambda _base_url=None: "",
    )

    response = await agent_management.chat_with_agent(
        to_agent='  "missing_bot"  ',
        text="Need help",
    )

    assert response.content[0].text == "Agent [missing_bot] not exists."


def test_list_agents_data_scopes_to_team_roster_for_leader(monkeypatch):
    fake_client = _FakeClient(
        get_response=_FakeResponse(
            json_data={
                "agents": [
                    {"id": "emp_planner", "name": "规划者", "enabled": True},
                    {"id": "emp_trends", "name": "行业趋势洞察大师", "enabled": True},
                ],
            },
        ),
    )
    monkeypatch.setattr(
        agent_management,
        "create_agent_api_client",
        lambda _base_url: fake_client,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.settings.is_agentdesk_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_leader_agents.team_roster_for_leader_agent",
        lambda _leader_id: ["规划者", "研究员"],
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_leader_agents.agent_matches_team_roster",
        lambda agent_id, roster: agent_id == "emp_planner",
    )
    monkeypatch.setattr(
        "qwenpaw.app.agent_context.get_current_agent_id",
        lambda: "lead_research01",
    )

    result = agent_management.list_agents_data("http://127.0.0.1:8088")

    assert [agent["id"] for agent in result["agents"]] == ["emp_planner"]


def test_list_agents_data_returns_empty_for_team_worker(monkeypatch):
    fake_client = _FakeClient(
        get_response=_FakeResponse(
            json_data={
                "agents": [
                    {"id": "emp_planner", "name": "规划者", "enabled": True},
                    {"id": "emp_trends", "name": "行业趋势洞察大师", "enabled": True},
                ],
            },
        ),
    )
    monkeypatch.setattr(
        agent_management,
        "create_agent_api_client",
        lambda _base_url: fake_client,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_leader_agents.team_roster_for_worker_agent",
        lambda _agent_id: ["规划者"],
    )
    monkeypatch.setattr(
        "qwenpaw.app.agent_context.get_current_agent_id",
        lambda: "emp_planner",
    )

    result = agent_management.list_agents_data("http://127.0.0.1:8088")

    assert result["agents"] == []


async def test_chat_with_agent_blocks_team_worker_delegation(monkeypatch):
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(agent_management.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(
        agent_management,
        "resolve_agent_target",
        lambda _to_agent, _base_url=None: "emp_trends",
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_leader_agents.team_roster_for_worker_agent",
        lambda _agent_id: ["规划者"],
    )
    monkeypatch.setattr(
        "qwenpaw.app.agent_context.get_current_agent_id",
        lambda: "emp_planner",
    )

    response = await agent_management.chat_with_agent(
        to_agent="emp_trends",
        text="delegate",
    )

    assert "Team workers cannot delegate" in response.content[0].text


async def test_submit_to_agent_blocks_team_leader_outside_roster(monkeypatch):
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(agent_management.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(
        agent_management,
        "resolve_agent_target",
        lambda _to_agent, _base_url=None: "emp_trends",
    )
    monkeypatch.setattr(
        agent_management,
        "_team_delegation_violation",
        lambda _agent_id: (
            "ERROR: Agent [emp_trends] is not a member of this team. "
            "Delegate only to team workers: 规划者 (emp_planner)."
        ),
    )

    response = await agent_management.submit_to_agent(
        to_agent="emp_trends",
        text="research",
    )

    assert "not a member of this team" in response.content[0].text


def test_merge_agent_sse_snapshot_prefers_completed_response():
    in_progress = {
        "object": "response",
        "status": "in_progress",
        "output": [
            {
                "object": "message",
                "content": [
                    {
                        "type": "data",
                        "data": {"name": "web_search", "output": "results"},
                    },
                ],
            },
        ],
    }
    completed = {
        "object": "response",
        "status": "completed",
        "output": [
            *in_progress["output"],
            {
                "object": "message",
                "content": [{"type": "text", "text": "Research summary."}],
            },
        ],
    }

    merged = agent_management.merge_agent_sse_snapshot(in_progress, completed)
    assert merged is completed
    assert agent_management.extract_agent_text_content(merged) == "Research summary."


def test_merge_agent_sse_snapshot_keeps_completed_over_later_heartbeat():
    completed = {
        "object": "response",
        "status": "completed",
        "output": [
            {
                "content": [{"type": "text", "text": "Final worker reply"}],
            },
        ],
    }
    heartbeat = {
        "object": "response",
        "status": "in_progress",
        "output": completed["output"],
    }

    merged = agent_management.merge_agent_sse_snapshot(completed, heartbeat)
    assert merged is completed


async def test_check_agent_task_surfaces_finished_worker_text(monkeypatch):
    """Regression: finished background tasks must expose non-empty worker text."""
    monkeypatch.setattr(
        agent_management,
        "get_agent_chat_task_status",
        lambda *_args, **_kwargs: {
            "status": "finished",
            "result": {
                "status": "completed",
                "session_id": "lead:to:researcher:1:abc",
                "output": [
                    {
                        "content": [
                            {"type": "data", "data": {"name": "web_search"}},
                        ],
                    },
                    {
                        "content": [
                            {"type": "text", "text": "Network search findings."},
                        ],
                    },
                ],
            },
        },
    )

    response = await agent_management.check_agent_task("task-research-1")
    text = response.content[0].text

    assert "[STATUS: finished]" in text
    assert "Network search findings." in text
    assert "(No text content in response)" not in text
