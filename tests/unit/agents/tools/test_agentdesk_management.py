# -*- coding: utf-8 -*-
"""Tests for AgentDesk employee management tools."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx

from qwenpaw.agents.tools import agentdesk_management


class _FakeResponse:
    def __init__(self, json_data=None, status_code=200, text="", headers=None):
        self._json_data = json_data or {}
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.reason_phrase = "OK" if status_code < 400 else "Error"
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

    @property
    def is_success(self) -> bool:
        return self.status_code < 400


class _FakeClient:
    def __init__(
        self,
        responses: list[_FakeResponse],
        get_responses: list[_FakeResponse | Exception] | None = None,
    ):
        self._responses = list(responses)
        self._get_responses = list(get_responses or [_FakeResponse([])])
        self.calls: list[tuple[str, dict]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, path, **kwargs):
        self.calls.append((path, kwargs))
        if not self._responses:
            raise AssertionError("unexpected POST")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def get(self, path, **kwargs):
        self.calls.append((path, kwargs))
        if not self._get_responses:
            raise AssertionError("unexpected GET")
        response = self._get_responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_create_agentdesk_employee_data_plaza_and_join():
    client = _FakeClient(
        [
            _FakeResponse({"name": "研究员", "desc": "数据检索", "skills": []}),
            _FakeResponse(
                {
                    "name": "研究员",
                    "joined": True,
                    "agent_id": "emp_研究员",
                    "mounted_skills": ["make_plan"],
                    "failed_skills": [],
                },
            ),
        ],
    )
    with patch.object(
        agentdesk_management,
        "create_agent_api_client",
        return_value=client,
    ):
        result = agentdesk_management.create_agentdesk_employee_data(
            name="研究员",
            desc="数据检索",
            skills=["make_plan"],
        )

    assert result["joined"] is True
    assert result["agent_id"] == "emp_研究员"
    assert client.calls[0][0] == "/employees"
    assert client.calls[1][0] == "/plaza"
    assert client.calls[1][1]["json"]["skills"] == ["make_plan"]
    assert client.calls[2][0] == "/plaza/%E7%A0%94%E7%A9%B6%E5%91%98/join"


def test_create_agentdesk_employees_data_reuses_client_and_continues_after_failure():
    client = _FakeClient(
        [
            _FakeResponse({"name": "采集工程师"}),
            _FakeResponse(
                {
                    "name": "采集工程师",
                    "joined": True,
                    "agent_id": "emp_collect",
                    "mounted_skills": [],
                    "failed_skills": [],
                },
            ),
            httpx.ReadTimeout("timed out"),
            _FakeResponse({"name": "洞察专家"}),
            _FakeResponse(
                {
                    "name": "洞察专家",
                    "joined": True,
                    "agent_id": "emp_insight",
                    "mounted_skills": [],
                    "failed_skills": [],
                },
            ),
        ],
    )
    with patch.object(
        agentdesk_management,
        "create_agent_api_client",
        return_value=client,
    ):
        result = agentdesk_management.create_agentdesk_employees_data(
            [
                {"name": "采集工程师", "desc": "采集数据"},
                {"name": "分析师", "desc": "分析数据"},
                {"name": "洞察专家", "desc": "输出建议"},
            ],
        )

    assert result["total"] == 3
    assert result["created"] == ["采集工程师", "洞察专家"]
    assert result["failed"][0]["name"] == "分析师"
    assert "timed out" in result["failed"][0]["error"]
    assert [call[0] for call in client.calls].count("/employees") == 1


def test_create_agentdesk_employee_data_rejects_frontend_html():
    client = _FakeClient(
        [],
        get_responses=[
            _FakeResponse(
                status_code=200,
                text="<!doctype html><html></html>",
                headers={"content-type": "text/html"},
            ),
        ],
    )
    with patch.object(
        agentdesk_management,
        "create_agent_api_client",
        return_value=client,
    ):
        try:
            agentdesk_management.create_agentdesk_employee_data(
                name="Analyst",
                desc="Organize data",
            )
        except agentdesk_management.AgentDeskApiProbeError as exc:
            assert "returned HTML" in str(exc)
        else:
            raise AssertionError("expected AgentDeskApiProbeError")


def test_create_agentdesk_employee_data_reports_probe_timeout():
    request = httpx.Request("GET", "http://127.0.0.1:8088/api/employees")
    client = _FakeClient(
        [],
        get_responses=[httpx.ReadTimeout("timed out", request=request)],
    )
    with patch.object(
        agentdesk_management,
        "create_agent_api_client",
        return_value=client,
    ):
        try:
            agentdesk_management.create_agentdesk_employee_data(
                name="Analyst",
                desc="Organize data",
            )
        except agentdesk_management.AgentDeskApiProbeError as exc:
            assert "probe timed out" in str(exc)
        else:
            raise AssertionError("expected AgentDeskApiProbeError")


def test_create_agentdesk_employee_tool_returns_json():
    with patch.object(
        agentdesk_management,
        "create_agentdesk_employee_data",
        return_value={"joined": True, "name": "销售专家"},
    ):
        chunk = asyncio.run(
            agentdesk_management.create_agentdesk_employee(
                name="销售专家",
                desc="负责销售跟进",
            ),
        )
    text = chunk.content[0].text
    assert "销售专家" in text
    assert "joined" in text


def test_create_agentdesk_employee_registers_with_function_tool():
    from agentscope.tool import FunctionTool

    tool = FunctionTool(agentdesk_management.create_agentdesk_employee)
    assert tool.name == "create_agentdesk_employee"


def test_create_agentdesk_employees_registers_with_function_tool():
    from agentscope.tool import FunctionTool

    tool = FunctionTool(agentdesk_management.create_agentdesk_employees)
    assert tool.name == "create_agentdesk_employees"
