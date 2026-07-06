# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.config.config import BuiltinToolConfig, ToolsConfig
from qwenpaw.agentdesk import tool_routes


class _Config:
    def __init__(self, tools) -> None:
        self.tools = tools


def test_list_tool_payloads_projects_configured_tools(monkeypatch) -> None:
    tools = ToolsConfig(
        builtin_tools={
            "search": BuiltinToolConfig(
                name="search",
                enabled=False,
                description="Search things",
                async_execution=True,
            ),
        },
    )
    monkeypatch.setattr(tool_routes, "load_config", lambda: _Config(tools))

    result = tool_routes.list_tool_payloads()

    search = next(item for item in result if item["key"] == "search")
    assert search == {
        "key": "search",
        "name": "search",
        "label": "search",
        "description": "Search things",
        "enabled": False,
        "read_only": False,
        "async_execution": True,
    }


def test_list_tool_payloads_uses_defaults_when_tools_missing(monkeypatch) -> None:
    monkeypatch.setattr(tool_routes, "load_config", lambda: _Config(None))

    keys = {item["key"] for item in tool_routes.list_tool_payloads()}

    assert "execute_shell_command" in keys
    assert "create_agentdesk_employee" in keys


def test_list_tool_payloads_refills_empty_tools_config(monkeypatch) -> None:
    empty = ToolsConfig.model_construct(builtin_tools={})
    monkeypatch.setattr(tool_routes, "load_config", lambda: _Config(empty))

    keys = {item["key"] for item in tool_routes.list_tool_payloads()}

    assert "execute_shell_command" in keys
