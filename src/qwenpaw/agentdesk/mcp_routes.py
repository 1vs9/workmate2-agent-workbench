# -*- coding: utf-8 -*-
"""AgentDesk MCP endpoint orchestration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .agent_workspace import resolve_active_agentdesk_agent_id
from .mcp_config import (
    delete_mcp_client_for_agent,
    install_mcp_preset_for_agent,
    list_mcp_presets_for_agent,
    merged_mcp_clients,
    serialize_mcp_client,
    upsert_mcp_client_for_agent,
)


@dataclass(frozen=True)
class McpMutationResult:
    agent_id: str
    payload: dict[str, Any]


def list_active_mcp_presets() -> list[dict[str, Any]]:
    agent_id = resolve_active_agentdesk_agent_id()
    return list_mcp_presets_for_agent(agent_id)


def install_active_mcp_preset(preset_id: str) -> McpMutationResult:
    agent_id = resolve_active_agentdesk_agent_id()
    return McpMutationResult(
        agent_id=agent_id,
        payload=install_mcp_preset_for_agent(preset_id, agent_id),
    )


def list_active_mcp_clients() -> list[dict[str, Any]]:
    agent_id = resolve_active_agentdesk_agent_id()
    return [
        serialize_mcp_client(key, client)
        for key, client in merged_mcp_clients(agent_id).items()
    ]


def upsert_active_mcp_client(body: dict[str, Any] | None) -> McpMutationResult:
    payload = dict(body or {})
    client_key = str(payload.get("key") or payload.get("name") or "").strip()
    if not client_key:
        raise ValueError("name is required")
    payload.setdefault("name", client_key)
    payload.setdefault("enabled", True)
    agent_id = resolve_active_agentdesk_agent_id()
    return McpMutationResult(
        agent_id=agent_id,
        payload=upsert_mcp_client_for_agent(client_key, payload, agent_id=agent_id),
    )


def delete_active_mcp_client(name: str) -> McpMutationResult:
    agent_id = resolve_active_agentdesk_agent_id()
    return McpMutationResult(
        agent_id=agent_id,
        payload=delete_mcp_client_for_agent(name, agent_id=agent_id),
    )
