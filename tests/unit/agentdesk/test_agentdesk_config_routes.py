# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from qwenpaw.agentdesk import config_routes


@pytest.mark.asyncio
async def test_get_agentdesk_config_payload_delegates(monkeypatch) -> None:
    async def _build():
        return {"providers": []}

    monkeypatch.setattr(config_routes, "build_agentdesk_config", _build)

    assert await config_routes.get_agentdesk_config_payload() == {"providers": []}


@pytest.mark.asyncio
async def test_update_agentdesk_provider_payload_normalizes_body(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def _update(provider_id: str, payload: dict[str, object]):
        calls.append((provider_id, payload))
        return {"id": provider_id}

    monkeypatch.setattr(config_routes, "update_agentdesk_provider", _update)

    assert await config_routes.update_agentdesk_provider_payload(
        "openai",
        {"api_key": "sk"},
    ) == {"id": "openai"}
    assert calls == [("openai", {"api_key": "sk"})]


@pytest.mark.asyncio
async def test_update_agentdesk_data_dirs_payload_requires_working_dir() -> None:
    with pytest.raises(ValueError, match="working_dir is required"):
        await config_routes.update_agentdesk_data_dirs_payload({"working_dir": " "})


@pytest.mark.asyncio
async def test_update_agentdesk_data_dirs_payload_trims_paths(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    async def _update(working_dir: str, secret_dir: str):
        calls.append((working_dir, secret_dir))
        return {"ok": True}

    monkeypatch.setattr(config_routes, "update_agentdesk_data_dirs", _update)

    assert await config_routes.update_agentdesk_data_dirs_payload(
        {"working_dir": " C:/data ", "secret_dir": " C:/secret "},
    ) == {"ok": True}
    assert calls == [("C:/data", "C:/secret")]


@pytest.mark.asyncio
async def test_set_agentdesk_active_model_payload_requires_fields() -> None:
    with pytest.raises(ValueError, match="provider_id and model are required"):
        await config_routes.set_agentdesk_active_model_payload(
            {"provider_id": "openai", "model": " "},
        )


@pytest.mark.asyncio
async def test_set_agentdesk_active_model_payload_trims_fields(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    async def _set(provider_id: str, model_id: str):
        calls.append((provider_id, model_id))
        return {"model_ready": True}

    monkeypatch.setattr(config_routes, "set_agentdesk_active_model", _set)

    assert await config_routes.set_agentdesk_active_model_payload(
        {"provider_id": " openai ", "model": " gpt-4.1 "},
    ) == {"model_ready": True}
    assert calls == [("openai", "gpt-4.1")]
