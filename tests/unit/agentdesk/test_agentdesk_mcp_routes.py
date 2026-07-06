# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

import pytest

from qwenpaw.agentdesk import mcp_routes


def test_list_active_mcp_presets_uses_active_agent(monkeypatch) -> None:
    monkeypatch.setattr(mcp_routes, "resolve_active_agentdesk_agent_id", lambda: "agent-1")
    monkeypatch.setattr(
        mcp_routes,
        "list_mcp_presets_for_agent",
        lambda agent_id: [{"agent_id": agent_id}],
    )

    assert mcp_routes.list_active_mcp_presets() == [{"agent_id": "agent-1"}]


def test_install_active_mcp_preset_returns_reload_agent(monkeypatch) -> None:
    monkeypatch.setattr(mcp_routes, "resolve_active_agentdesk_agent_id", lambda: "agent-1")
    monkeypatch.setattr(
        mcp_routes,
        "install_mcp_preset_for_agent",
        lambda preset_id, agent_id: {"preset_id": preset_id, "agent_id": agent_id},
    )

    result = mcp_routes.install_active_mcp_preset("fetch")

    assert result.agent_id == "agent-1"
    assert result.payload == {"preset_id": "fetch", "agent_id": "agent-1"}


def test_list_active_mcp_clients_serializes_merged_clients(monkeypatch) -> None:
    client = SimpleNamespace(name="Fetch")
    monkeypatch.setattr(mcp_routes, "resolve_active_agentdesk_agent_id", lambda: "agent-1")
    monkeypatch.setattr(
        mcp_routes,
        "merged_mcp_clients",
        lambda agent_id: {"fetch": client},
    )
    monkeypatch.setattr(
        mcp_routes,
        "serialize_mcp_client",
        lambda key, value: {"key": key, "name": value.name},
    )

    assert mcp_routes.list_active_mcp_clients() == [{"key": "fetch", "name": "Fetch"}]


def test_upsert_active_mcp_client_defaults_name_and_enabled(monkeypatch) -> None:
    captured: list[tuple[str, dict[str, object], str]] = []
    monkeypatch.setattr(mcp_routes, "resolve_active_agentdesk_agent_id", lambda: "agent-1")

    def _upsert(client_key: str, payload: dict[str, object], *, agent_id: str):
        captured.append((client_key, payload, agent_id))
        return {"key": client_key, "enabled": payload["enabled"]}

    monkeypatch.setattr(mcp_routes, "upsert_mcp_client_for_agent", _upsert)

    result = mcp_routes.upsert_active_mcp_client({"key": "fetch"})

    assert result.agent_id == "agent-1"
    assert result.payload == {"key": "fetch", "enabled": True}
    assert captured == [
        ("fetch", {"key": "fetch", "name": "fetch", "enabled": True}, "agent-1"),
    ]


def test_upsert_active_mcp_client_requires_key_or_name() -> None:
    with pytest.raises(ValueError, match="name is required"):
        mcp_routes.upsert_active_mcp_client({})


def test_delete_active_mcp_client_returns_reload_agent(monkeypatch) -> None:
    monkeypatch.setattr(mcp_routes, "resolve_active_agentdesk_agent_id", lambda: "agent-1")
    monkeypatch.setattr(
        mcp_routes,
        "delete_mcp_client_for_agent",
        lambda name, *, agent_id: {"deleted": True, "name": name, "agent_id": agent_id},
    )

    result = mcp_routes.delete_active_mcp_client("fetch")

    assert result.agent_id == "agent-1"
    assert result.payload == {"deleted": True, "name": "fetch", "agent_id": "agent-1"}
