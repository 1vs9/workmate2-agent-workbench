# -*- coding: utf-8 -*-
"""Resolve and bootstrap QwenPaw model configuration for AgentDesk chat."""

from __future__ import annotations

import logging
from typing import Any

from ..config.config import ModelSlotConfig, load_agent_config
from ..providers.provider_manager import ProviderManager

logger = logging.getLogger(__name__)

_NO_MODEL_MESSAGE = (
    "未配置可用模型。请在 QwenPaw 设置中配置 API Key 并选择模型，"
    "或安装本地模型后重试。"
)


def _slot_is_set(slot: Any | None) -> bool:
    return bool(
        slot is not None
        and getattr(slot, "provider_id", None)
        and getattr(slot, "model", None),
    )


def model_slot_for_build_agent(agent_id: str) -> ModelSlotConfig | None:
    """Return the model slot :func:`build_agent` accepts, if any."""
    agent_config = load_agent_config(agent_id)
    active = agent_config.active_model
    if not _slot_is_set(active):
        active = ProviderManager.get_instance().get_active_model()
    if not _slot_is_set(active):
        return None
    return active


def resolve_effective_model_slot(agent_id: str) -> ModelSlotConfig | None:
    """Resolve the model slot AgentDesk chat would use for *agent_id*."""
    ready = model_slot_for_build_agent(agent_id)
    if ready is not None:
        return ready

    agent_config = load_agent_config(agent_id)
    active_slot = ProviderManager.get_instance().get_active_model()

    routing = agent_config.llm_routing
    if getattr(routing, "enabled", False):
        if routing.mode == "cloud_first":
            if routing.cloud is not None and _slot_is_set(routing.cloud):
                return routing.cloud
            if active_slot is not None and _slot_is_set(active_slot):
                return active_slot
            return None
        if routing.local is not None and _slot_is_set(routing.local):
            return routing.local
        return None

    if active_slot is not None and _slot_is_set(active_slot):
        return active_slot
    return None


def _provider_has_usable_models(provider: Any) -> bool:
    models = list(getattr(provider, "models", []) or []) + list(
        getattr(provider, "extra_models", []) or [],
    )
    if not models:
        return False
    if provider.id == "qwenpaw-local":
        return bool(str(getattr(provider, "base_url", "") or "").strip())
    if getattr(provider, "require_api_key", True):
        return bool(
            str(getattr(provider, "api_key", "") or "").strip()
            or str(getattr(provider, "auth_token", "") or "").strip(),
        )
    return True


def find_first_usable_model() -> tuple[str, str] | None:
    """Return the first provider/model pair that looks ready to call."""
    manager = ProviderManager.get_instance()
    provider_ids: list[str] = []
    provider_ids.extend(manager.builtin_providers.keys())
    provider_ids.extend(manager.custom_providers.keys())
    provider_ids.extend(manager.plugin_providers.keys())

    for provider_id in provider_ids:
        provider = manager.get_provider(provider_id)
        if provider is None or not _provider_has_usable_models(provider):
            continue
        for model in list(provider.models or []) + list(provider.extra_models or []):
            model_id = getattr(model, "id", None)
            if model_id and provider.has_model(model_id):
                return provider_id, model_id
    return None


async def _activate_model_slot(
    slot: ModelSlotConfig,
    *,
    agent_id: str,
) -> tuple[ModelSlotConfig | None, str | None]:
    manager = ProviderManager.get_instance()
    try:
        await manager.activate_model(slot.provider_id, slot.model)
        logger.info(
            "AgentDesk activated model %s/%s for agent '%s'",
            slot.provider_id,
            slot.model,
            agent_id,
        )
    except Exception as exc:  # noqa: BLE001 - surface provider errors to UI
        return None, f"无法激活模型 {slot.provider_id}/{slot.model}: {exc}"

    ready = model_slot_for_build_agent(agent_id)
    if ready is not None:
        return ready, None
    return None, (
        f"已尝试激活 {slot.provider_id}/{slot.model}，但模型仍未就绪。"
        "请在 QwenPaw 设置中确认 API Key 与模型选择。"
    )


async def ensure_chat_model(agent_id: str) -> tuple[ModelSlotConfig | None, str | None]:
    """Ensure chat can run for *agent_id*; auto-activate first usable model if needed."""
    ready = model_slot_for_build_agent(agent_id)
    if ready is not None:
        return ready, None

    target = resolve_effective_model_slot(agent_id)
    if target is None:
        first = find_first_usable_model()
        if first is None:
            return None, _NO_MODEL_MESSAGE
        provider_id, model_id = first
        target = ModelSlotConfig(provider_id=provider_id, model=model_id)

    return await _activate_model_slot(target, agent_id=agent_id)


def get_health_model_info(agent_id: str | None = None) -> dict[str, Any]:
    """Expose model readiness in AgentDesk /health payload."""
    from .agents import resolve_agent_id

    resolved_agent = resolve_agent_id(agent_id)
    slot = model_slot_for_build_agent(resolved_agent)
    if slot is None:
        return {
            "model_ready": False,
            "active_model": None,
            "active_agent": resolved_agent,
        }
    return {
        "model_ready": True,
        "active_model": f"{slot.provider_id}/{slot.model}",
        "active_agent": resolved_agent,
    }
