# -*- coding: utf-8 -*-
"""Tests for AgentDesk configuration API endpoints."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import qwenpaw.constant as qwenpaw_constant
import qwenpaw.agentdesk.config_api as config_api
import qwenpaw.agentdesk.config_routes as config_routes
from qwenpaw.agentdesk.router import api_router, router


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(qwenpaw_constant, "WORKING_DIR", tmp_path)
    monkeypatch.setattr(config_api, "WORKING_DIR", tmp_path, raising=False)
    app = FastAPI()
    app.include_router(router)
    app.include_router(api_router)
    return TestClient(app)


@pytest.fixture
def fake_provider_manager(monkeypatch):
    provider = SimpleNamespace(
        id="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key="sk-secret",
        auth_token="",
        require_api_key=True,
        models=[SimpleNamespace(id="gpt-4o-mini", name="GPT-4o mini")],
        extra_models=[],
    )
    active = {"slot": None}

    async def list_provider_info():
        info = SimpleNamespace(
            id=provider.id,
            name=provider.name,
            base_url=provider.base_url,
            api_key="sk-******",
            api_key_prefix="sk-",
            require_api_key=True,
            freeze_url=False,
            is_local=False,
            is_custom=False,
            models=provider.models,
            extra_models=provider.extra_models,
        )
        return [info]

    async def get_provider_info(provider_id: str):
        if provider_id != provider.id:
            return None
        info = await list_provider_info()
        return info[0]

    def get_provider(provider_id: str):
        return provider if provider_id == provider.id else None

    def get_active_model():
        return active["slot"]

    def update_provider(provider_id: str, config: dict) -> bool:
        if provider_id != provider.id:
            return False
        if config.get("api_key") is not None:
            provider.api_key = config["api_key"]
        if config.get("base_url") is not None:
            provider.base_url = config["base_url"]
        return True

    async def activate_model(provider_id: str, model_id: str) -> None:
        active["slot"] = SimpleNamespace(provider_id=provider_id, model=model_id)

    manager = SimpleNamespace(
        list_provider_info=list_provider_info,
        get_provider_info=get_provider_info,
        get_provider=get_provider,
        get_active_model=get_active_model,
        update_provider=update_provider,
        activate_model=activate_model,
        builtin_providers={"openai": provider},
        custom_providers={},
        plugin_providers={},
    )
    monkeypatch.setattr(
        config_api.ProviderManager,
        "get_instance",
        lambda: manager,
    )
    monkeypatch.setattr(
        config_routes,
        "build_agentdesk_config",
        config_api.build_agentdesk_config,
    )
    monkeypatch.setattr(
        config_routes,
        "update_agentdesk_provider",
        config_api.update_agentdesk_provider,
    )
    monkeypatch.setattr(
        config_routes,
        "update_agentdesk_data_dirs",
        config_api.update_agentdesk_data_dirs,
    )
    monkeypatch.setattr(
        config_routes,
        "set_agentdesk_active_model",
        config_api.set_agentdesk_active_model,
    )
    monkeypatch.setattr(
        config_api,
        "get_health_model_info",
        lambda agent_id=None: {
            "model_ready": active["slot"] is not None,
            "active_model": (
                f"{active['slot'].provider_id}/{active['slot'].model}"
                if active["slot"] is not None
                else None
            ),
        },
    )
    return manager, provider, active


def test_get_config_returns_working_dir_and_providers(tmp_path, monkeypatch, fake_provider_manager):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/api/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["working_dir"] == str(tmp_path)
    assert "secret_dir" in payload
    assert "suggested_working_dir" in payload
    assert payload["providers"][0]["id"] == "openai"
    assert payload["providers"][0]["api_key_configured"] is True
    assert payload["model_ready"] is False


def test_update_data_dirs_endpoint(tmp_path, monkeypatch, fake_provider_manager):
    bootstrap = tmp_path / "bootstrap"
    paths_file = bootstrap / "paths.json"
    import qwenpaw.agentdesk.paths_config as paths_config

    monkeypatch.setattr(paths_config, "BOOTSTRAP_DIR", bootstrap)
    monkeypatch.setattr(paths_config, "PATHS_FILE", paths_file)

    client = _client(tmp_path, monkeypatch)
    target = tmp_path / "data"
    secret = tmp_path / "data.secret"
    response = client.put(
        "/api/config/data-dirs",
        json={"working_dir": str(target), "secret_dir": str(secret)},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["requires_restart"] is True
    assert payload["saved_working_dir"] == str(target.resolve())
    assert payload["saved_secret_dir"] == str(secret.resolve())
    assert paths_file.is_file()


def test_update_provider_config_persists_api_key(tmp_path, monkeypatch, fake_provider_manager):
    _, provider, _ = fake_provider_manager
    client = _client(tmp_path, monkeypatch)
    response = client.put(
        "/api/config/providers/openai",
        json={"api_key": "sk-new-key", "base_url": "https://example.test/v1"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["base_url"] == "https://example.test/v1"
    assert payload["api_key_configured"] is True
    assert provider.api_key == "sk-new-key"
    assert provider.base_url == "https://example.test/v1"


def test_set_active_model_endpoint(tmp_path, monkeypatch, fake_provider_manager):
    _, _, active = fake_provider_manager
    client = _client(tmp_path, monkeypatch)
    response = client.put(
        "/api/config/active-model",
        json={"provider_id": "openai", "model": "gpt-4o-mini"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["model_ready"] is True
    assert payload["active_model"] == {
        "provider_id": "openai",
        "model": "gpt-4o-mini",
    }
    assert active["slot"].model == "gpt-4o-mini"
