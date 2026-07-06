# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from qwenpaw.config.config import MCPClientConfig, MCPConfig
from qwenpaw.agentdesk import mcp_config


def test_merged_mcp_clients_prefers_agent_override(monkeypatch) -> None:
    root_client = MCPClientConfig(name="root", command="root-cmd")
    override_client = MCPClientConfig(name="agent", command="agent-cmd")
    agent_only = MCPClientConfig(name="agent-only", command="agent-only-cmd")

    monkeypatch.setattr(
        mcp_config,
        "load_config",
        lambda: SimpleNamespace(mcp=MCPConfig(clients={"shared": root_client})),
    )
    monkeypatch.setattr(
        mcp_config,
        "load_agent_config",
        lambda _agent_id: SimpleNamespace(
            mcp=MCPConfig(clients={"shared": override_client, "extra": agent_only}),
        ),
    )

    merged = mcp_config.merged_mcp_clients("default")

    assert merged["shared"].command == "agent-cmd"
    assert merged["extra"].command == "agent-only-cmd"


def test_build_filesystem_preset_uses_agent_workspace(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_config,
        "agent_workspace_dir",
        lambda _agent_id: tmp_path,
    )

    client = mcp_config.build_preset_client("filesystem", "default")

    assert client.command == "npx"
    assert client.args == [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        str(tmp_path),
    ]


def test_mcp_client_from_payload_defaults_stdio() -> None:
    client = mcp_config.mcp_client_from_payload(
        {
            "key": "fetch",
            "description": "Fetch pages",
            "command": "npx",
            "args": ["-y", "pkg"],
            "env": {"A": "B"},
        },
    )

    assert client.name == "fetch"
    assert client.transport == "stdio"
    assert client.enabled is True
    assert client.command == "npx"
    assert client.args == ["-y", "pkg"]
    assert client.env == {"A": "B"}


def test_serialize_mcp_client_omits_env() -> None:
    client = MCPClientConfig(
        name="tavily",
        command="npx",
        args=["-y", "tavily"],
        env={"TAVILY_API_KEY": "secret"},
    )

    payload = mcp_config.serialize_mcp_client("tavily_search", client)

    assert payload["key"] == "tavily_search"
    assert payload["command"] == "npx"
    assert "env" not in payload
