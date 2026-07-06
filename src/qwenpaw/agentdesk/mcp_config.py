# -*- coding: utf-8 -*-
"""AgentDesk MCP preset and client configuration helpers."""

from __future__ import annotations

import os
from typing import Any

from fastapi import HTTPException

from ..config.config import (
    MCPClientConfig,
    MCPConfig,
    load_agent_config,
    save_agent_config,
)
from ..config.utils import load_config
from .agent_workspace import agent_workspace_dir


AGENTDESK_MCP_PRESETS: dict[str, dict[str, Any]] = {
    "tavily_search": {
        "id": "tavily_search",
        "name": "Tavily 搜索",
        "description": "专为 AI 优化的实时网页搜索，需配置 TAVILY_API_KEY",
        "requiresApiKey": "TAVILY_API_KEY",
    },
    "fetch": {
        "id": "fetch",
        "name": "Fetch",
        "description": "获取网页内容并转换为 Markdown",
        "requiresApiKey": None,
    },
    "memory": {
        "id": "memory",
        "name": "Memory",
        "description": "持久化键值记忆，跨会话保留上下文",
        "requiresApiKey": None,
    },
    "sequential-thinking": {
        "id": "sequential-thinking",
        "name": "Sequential Thinking",
        "description": "分步推理工具，帮助复杂问题拆解与思考",
        "requiresApiKey": None,
    },
    "filesystem": {
        "id": "filesystem",
        "name": "Filesystem",
        "description": "访问当前智能体工作区内的文件与目录",
        "requiresApiKey": None,
    },
}


def serialize_mcp_client(key: str, client: MCPClientConfig) -> dict[str, Any]:
    return {
        "key": key,
        "name": client.name,
        "description": client.description,
        "enabled": client.enabled,
        "transport": client.transport,
        "url": client.url,
        "command": client.command,
        "args": client.args,
    }


def merged_mcp_clients(agent_id: str) -> dict[str, MCPClientConfig]:
    """Merge root config MCP defaults with active agent overrides."""
    root_cfg = load_config()
    agent_cfg = load_agent_config(agent_id)
    merged: dict[str, MCPClientConfig] = {}
    root_mcp = getattr(root_cfg, "mcp", None)
    if root_mcp is not None and root_mcp.clients:
        merged.update(root_mcp.clients)
    agent_mcp = getattr(agent_cfg, "mcp", None)
    if agent_mcp is not None and agent_mcp.clients:
        merged.update(agent_mcp.clients)
    return merged


def list_mcp_presets_for_agent(agent_id: str) -> list[dict[str, Any]]:
    installed_keys = set(merged_mcp_clients(agent_id).keys())
    return [
        {
            **meta,
            "installed": meta["id"] in installed_keys,
        }
        for meta in AGENTDESK_MCP_PRESETS.values()
    ]


def build_preset_client(preset_id: str, agent_id: str) -> MCPClientConfig:
    workspace = str(agent_workspace_dir(agent_id))
    if preset_id == "tavily_search":
        return MCPClientConfig(
            name="tavily_mcp",
            description="Tavily web search for AI agents",
            enabled=True,
            command="npx",
            args=["-y", "tavily-mcp@latest"],
            env={"TAVILY_API_KEY": os.environ.get("TAVILY_API_KEY", "")},
        )
    if preset_id == "fetch":
        return MCPClientConfig(
            name="fetch",
            description="Fetch web pages and convert to markdown",
            enabled=True,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-fetch"],
        )
    if preset_id == "memory":
        return MCPClientConfig(
            name="memory",
            description="Persistent key-value memory across sessions",
            enabled=True,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-memory"],
        )
    if preset_id == "sequential-thinking":
        return MCPClientConfig(
            name="sequential-thinking",
            description="Step-by-step reasoning for complex problems",
            enabled=True,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
        )
    if preset_id == "filesystem":
        return MCPClientConfig(
            name="filesystem",
            description="Access files in the agent workspace",
            enabled=True,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", workspace],
        )
    raise HTTPException(status_code=404, detail=f"Unknown MCP preset '{preset_id}'")


def mcp_client_from_payload(payload: dict[str, Any]) -> MCPClientConfig:
    return MCPClientConfig(
        name=str(payload.get("name") or payload.get("key") or "").strip(),
        description=str(payload.get("description") or ""),
        enabled=bool(payload.get("enabled", True)),
        transport=payload.get("transport") or "stdio",
        url=str(payload.get("url") or ""),
        command=str(payload.get("command") or ""),
        args=list(payload.get("args") or []),
        env=dict(payload.get("env") or {}),
        cwd=str(payload.get("cwd") or ""),
    )


def install_mcp_preset_for_agent(preset_id: str, agent_id: str) -> dict[str, Any]:
    if preset_id not in AGENTDESK_MCP_PRESETS:
        raise HTTPException(status_code=404, detail=f"Unknown MCP preset '{preset_id}'")
    agent_config = load_agent_config(agent_id)
    if agent_config.mcp is None:
        agent_config.mcp = MCPConfig()
    client = build_preset_client(preset_id, agent_id)
    agent_config.mcp.clients[preset_id] = client
    save_agent_config(agent_id, agent_config)
    return serialize_mcp_client(preset_id, client)


def upsert_mcp_client_for_agent(
    client_key: str,
    payload: dict[str, Any],
    *,
    agent_id: str,
) -> dict[str, Any]:
    try:
        client = mcp_client_from_payload(payload)
    except Exception as exc:  # noqa: BLE001 - surface MCP validation errors
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    agent_config = load_agent_config(agent_id)
    if agent_config.mcp is None:
        agent_config.mcp = MCPConfig()
    agent_config.mcp.clients[client_key] = client
    save_agent_config(agent_id, agent_config)
    return serialize_mcp_client(client_key, client)


def delete_mcp_client_for_agent(name: str, *, agent_id: str) -> dict[str, Any]:
    agent_config = load_agent_config(agent_id)
    mcp_cfg = getattr(agent_config, "mcp", None)
    if mcp_cfg is None or name not in (mcp_cfg.clients or {}):
        raise HTTPException(status_code=404, detail=f"MCP client '{name}' not found")
    del agent_config.mcp.clients[name]
    save_agent_config(agent_id, agent_config)
    return {"deleted": True, "name": name}
