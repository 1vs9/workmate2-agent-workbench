# -*- coding: utf-8 -*-
"""Helpers for refreshing AgentDesk agent runtimes."""

from __future__ import annotations

import logging

from fastapi import Request

logger = logging.getLogger(__name__)


async def reload_agent_after_skill_mount(request: Request | None, agent_id: str) -> bool:
    """Reload a running agent so newly enabled skills register in the toolkit."""
    if request is None:
        return False
    app_state = getattr(getattr(request, "app", None), "state", None)
    manager = getattr(app_state, "multi_agent_manager", None)
    if manager is None or not hasattr(manager, "reload_agent"):
        return False
    if not manager.is_agent_loaded(agent_id):
        return False
    try:
        return bool(await manager.reload_agent(agent_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to reload agent '%s' after skill mount: %s", agent_id, exc)
        return False
