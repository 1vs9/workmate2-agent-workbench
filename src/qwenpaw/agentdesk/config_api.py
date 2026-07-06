# -*- coding: utf-8 -*-
"""AgentDesk settings snapshot and provider configuration helpers."""

from __future__ import annotations

from typing import Any

from ..providers.provider_manager import ProviderManager
from .model_config import get_health_model_info


def _working_dir() -> str:
    from ..constant import WORKING_DIR

    return str(WORKING_DIR)


def _secret_dir() -> str:
    from ..constant import SECRET_DIR

    return str(SECRET_DIR)


def _provider_models(provider_info: Any) -> list[dict[str, str]]:
    models: list[dict[str, str]] = []
    seen: set[str] = set()
    for model in list(getattr(provider_info, "models", []) or []) + list(
        getattr(provider_info, "extra_models", []) or [],
    ):
        model_id = str(getattr(model, "id", "") or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        models.append(
            {
                "id": model_id,
                "name": str(getattr(model, "name", "") or model_id),
            },
        )
    return models


def _provider_api_key_configured(manager: ProviderManager, provider_id: str) -> bool:
    provider = manager.get_provider(provider_id)
    if provider is None:
        return False
    if not getattr(provider, "require_api_key", True):
        return True
    return bool(
        str(getattr(provider, "api_key", "") or "").strip()
        or str(getattr(provider, "auth_token", "") or "").strip(),
    )


def _provider_payload(manager: ProviderManager, info: Any) -> dict[str, Any]:
    """Return a provider row safe for the browser settings UI."""

    return {
        "id": info.id,
        "name": info.name,
        "base_url": info.base_url,
        "api_key_prefix": info.api_key_prefix,
        "api_key_configured": _provider_api_key_configured(manager, info.id),
        "require_api_key": info.require_api_key,
        "freeze_url": info.freeze_url,
        "is_local": info.is_local,
        "is_custom": info.is_custom,
        "models": _provider_models(info),
    }


async def build_agentdesk_config() -> dict[str, Any]:
    """Return a AgentDesk-friendly configuration snapshot for the settings UI."""
    manager = ProviderManager.get_instance()
    provider_infos = await manager.list_provider_info()
    active = manager.get_active_model()
    health = get_health_model_info()

    providers: list[dict[str, Any]] = []
    for info in provider_infos:
        providers.append(_provider_payload(manager, info))

    active_payload = None
    if active is not None and active.provider_id and active.model:
        active_payload = {
            "provider_id": active.provider_id,
            "model": active.model,
        }

    from .paths_config import load_saved_paths, suggest_paths

    suggested_working_dir, suggested_secret_dir = suggest_paths()
    saved_paths = load_saved_paths()

    return {
        "working_dir": _working_dir(),
        "secret_dir": _secret_dir(),
        "suggested_working_dir": suggested_working_dir,
        "suggested_secret_dir": suggested_secret_dir,
        "paths_saved": saved_paths is not None,
        "saved_working_dir": saved_paths.get("working_dir") if saved_paths else None,
        "saved_secret_dir": saved_paths.get("secret_dir") if saved_paths else None,
        "model_ready": bool(health.get("model_ready")),
        "active_model": active_payload,
        "active_model_label": health.get("active_model"),
        "providers": providers,
    }


async def update_agentdesk_data_dirs(
    working_dir: str,
    secret_dir: str,
) -> dict[str, Any]:
    """Persist data directories for the next process restart."""
    from .paths_config import save_paths

    saved = save_paths(working_dir, secret_dir)
    return {
        "working_dir": _working_dir(),
        "secret_dir": _secret_dir(),
        "saved_working_dir": saved["working_dir"],
        "saved_secret_dir": saved["secret_dir"],
        "requires_restart": True,
        "message": (
            "数据目录已保存，请完全退出并重新启动 AgentDesk 后生效。"
            "（已同步 Windows 用户环境变量）"
        ),
    }


async def update_agentdesk_provider(
    provider_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Update provider credentials/settings and return refreshed provider row."""
    manager = ProviderManager.get_instance()
    updates: dict[str, Any] = {}
    if "api_key" in payload and payload["api_key"] is not None:
        updates["api_key"] = str(payload["api_key"]).strip()
    if "base_url" in payload and payload["base_url"] is not None:
        updates["base_url"] = str(payload["base_url"]).strip()

    if not updates:
        raise ValueError("No provider fields to update")

    if not manager.update_provider(provider_id, updates):
        raise LookupError(f"Provider '{provider_id}' not found")

    info = await manager.get_provider_info(provider_id)
    if info is None:
        raise LookupError(f"Provider '{provider_id}' not found after update")

    return _provider_payload(manager, info)


async def set_agentdesk_active_model(provider_id: str, model_id: str) -> dict[str, Any]:
    """Activate a global provider/model pair for AgentDesk chat."""
    manager = ProviderManager.get_instance()
    await manager.activate_model(provider_id, model_id)
    active = manager.get_active_model()
    if active is None:
        return {"active_model": None, "active_model_label": None, "model_ready": False}
    label = f"{active.provider_id}/{active.model}"
    return {
        "active_model": {
            "provider_id": active.provider_id,
            "model": active.model,
        },
        "active_model_label": label,
        "model_ready": True,
    }
