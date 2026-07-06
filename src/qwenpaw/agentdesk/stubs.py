# -*- coding: utf-8 -*-
"""Stub AgentDesk API responses until real QwenPaw mapping is implemented."""

from __future__ import annotations

from typing import Any


def empty_list() -> list[Any]:
    return []


def health_payload() -> dict[str, Any]:
    from .model_config import get_health_model_info

    payload = {
        "status": "ok",
        "model_context_size": 128000,
        "agent_max_iters": 0,
        "agent_max_iters_effective": 50,
        "agent_max_iters_unlimited": True,
        "agent_iters_unlimited_cap": 200,
        "backend": "qwenpaw-agentdesk",
    }
    payload.update(get_health_model_info())
    return payload
