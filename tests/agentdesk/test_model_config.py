# -*- coding: utf-8 -*-
"""Tests for AgentDesk model resolution and bootstrap."""

from types import SimpleNamespace

import pytest

import qwenpaw.agentdesk.model_config as model_config


def _agent_config(**overrides):
    base = SimpleNamespace(
        active_model=None,
        llm_routing=SimpleNamespace(
            enabled=False,
            mode="cloud_first",
            cloud=None,
            local=None,
        ),
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_resolve_effective_model_slot_prefers_agent_active_model(monkeypatch):
    slot = SimpleNamespace(provider_id="openai", model="gpt-4o")
    monkeypatch.setattr(
        model_config,
        "load_agent_config",
        lambda agent_id: _agent_config(active_model=slot),
    )
    monkeypatch.setattr(
        model_config.ProviderManager,
        "get_instance",
        lambda: SimpleNamespace(get_active_model=lambda: None),
    )

    assert model_config.resolve_effective_model_slot("default") is slot


def test_resolve_effective_model_slot_falls_back_to_global_active(monkeypatch):
    global_slot = SimpleNamespace(provider_id="dashscope", model="qwen-max")
    monkeypatch.setattr(
        model_config,
        "load_agent_config",
        lambda agent_id: _agent_config(),
    )
    monkeypatch.setattr(
        model_config.ProviderManager,
        "get_instance",
        lambda: SimpleNamespace(get_active_model=lambda: global_slot),
    )

    resolved = model_config.resolve_effective_model_slot("default")
    assert resolved is global_slot


@pytest.mark.asyncio
async def test_ensure_chat_model_auto_activates_first_usable(monkeypatch):
    activated: list[tuple[str, str]] = []
    active_state: dict[str, SimpleNamespace | None] = {"slot": None}

    async def fake_activate(provider_id: str, model_id: str) -> None:
        activated.append((provider_id, model_id))
        active_state["slot"] = SimpleNamespace(
            provider_id=provider_id,
            model=model_id,
        )

    provider = SimpleNamespace(
        id="openai",
        models=[SimpleNamespace(id="gpt-4o-mini")],
        extra_models=[],
        api_key="test-key",
        auth_token="",
        require_api_key=True,
        has_model=lambda model_id: model_id == "gpt-4o-mini",
    )
    manager = SimpleNamespace(
        get_active_model=lambda: active_state["slot"],
        builtin_providers={"openai": provider},
        custom_providers={},
        plugin_providers={},
        get_provider=lambda provider_id: provider if provider_id == "openai" else None,
        activate_model=fake_activate,
    )

    monkeypatch.setattr(
        model_config,
        "load_agent_config",
        lambda agent_id: _agent_config(),
    )
    monkeypatch.setattr(model_config.ProviderManager, "get_instance", lambda: manager)

    slot, error = await model_config.ensure_chat_model("default")

    assert error is None
    assert activated == [("openai", "gpt-4o-mini")]
    assert slot.provider_id == "openai"
    assert slot.model == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_ensure_chat_model_activates_routing_slot_for_build_agent(monkeypatch):
    """Routing-only slots must be activated before build_agent runs."""
    activated: list[tuple[str, str]] = []
    routing_slot = SimpleNamespace(provider_id="dashscope", model="qwen-max")
    activated_slot = SimpleNamespace(provider_id="dashscope", model="qwen-max")

    async def fake_activate(provider_id: str, model_id: str) -> None:
        activated.append((provider_id, model_id))

    manager = SimpleNamespace(
        get_active_model=lambda: activated_slot if activated else None,
        activate_model=fake_activate,
        builtin_providers={},
        custom_providers={},
        plugin_providers={},
        get_provider=lambda provider_id: None,
    )

    monkeypatch.setattr(
        model_config,
        "load_agent_config",
        lambda agent_id: _agent_config(
            llm_routing=SimpleNamespace(
                enabled=True,
                mode="cloud_first",
                cloud=routing_slot,
                local=None,
            ),
        ),
    )
    monkeypatch.setattr(model_config.ProviderManager, "get_instance", lambda: manager)

    slot, error = await model_config.ensure_chat_model("default")

    assert error is None
    assert activated == [("dashscope", "qwen-max")]
    assert slot.provider_id == "dashscope"
    assert slot.model == "qwen-max"


@pytest.mark.asyncio
async def test_model_slot_for_build_agent_ignores_routing_only_slot(monkeypatch):
    routing_slot = SimpleNamespace(provider_id="dashscope", model="qwen-max")
    monkeypatch.setattr(
        model_config,
        "load_agent_config",
        lambda agent_id: _agent_config(
            llm_routing=SimpleNamespace(
                enabled=True,
                mode="cloud_first",
                cloud=routing_slot,
                local=None,
            ),
        ),
    )
    monkeypatch.setattr(
        model_config.ProviderManager,
        "get_instance",
        lambda: SimpleNamespace(get_active_model=lambda: None),
    )

    assert model_config.model_slot_for_build_agent("default") is None
    assert model_config.resolve_effective_model_slot("default") is routing_slot


@pytest.mark.asyncio
async def test_ensure_chat_model_returns_actionable_error_when_unconfigured(
    monkeypatch,
):
    manager = SimpleNamespace(
        get_active_model=lambda: None,
        builtin_providers={},
        custom_providers={},
        plugin_providers={},
        get_provider=lambda provider_id: None,
    )
    monkeypatch.setattr(
        model_config,
        "load_agent_config",
        lambda agent_id: _agent_config(),
    )
    monkeypatch.setattr(model_config.ProviderManager, "get_instance", lambda: manager)

    slot, error = await model_config.ensure_chat_model("default")

    assert slot is None
    assert error is not None
    assert "未配置可用模型" in error
