# -*- coding: utf-8 -*-
"""AgentDesk config endpoint orchestration helpers."""

from __future__ import annotations

from typing import Any

from .config_api import (
    build_agentdesk_config,
    set_agentdesk_active_model,
    update_agentdesk_data_dirs,
    update_agentdesk_provider,
)


async def get_agentdesk_config_payload() -> dict[str, Any]:
    return await build_agentdesk_config()


async def update_agentdesk_provider_payload(
    provider_id: str,
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    return await update_agentdesk_provider(provider_id, dict(body or {}))


async def update_agentdesk_data_dirs_payload(
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(body or {})
    working_dir = str(payload.get("working_dir") or "").strip()
    secret_dir = str(payload.get("secret_dir") or "").strip()
    if not working_dir:
        raise ValueError("working_dir is required")
    return await update_agentdesk_data_dirs(working_dir, secret_dir)


async def set_agentdesk_active_model_payload(
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = dict(body or {})
    provider_id = str(payload.get("provider_id") or "").strip()
    model_id = str(payload.get("model") or "").strip()
    if not provider_id or not model_id:
        raise ValueError("provider_id and model are required")
    return await set_agentdesk_active_model(provider_id, model_id)
