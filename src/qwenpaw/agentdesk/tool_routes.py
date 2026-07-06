# -*- coding: utf-8 -*-
"""AgentDesk tool endpoint orchestration helpers."""

from __future__ import annotations

from typing import Any

from ..config.config import ToolsConfig
from ..config.utils import load_config


def _effective_tools_config(raw_tools: Any) -> ToolsConfig:
    if not isinstance(raw_tools, ToolsConfig):
        return ToolsConfig()
    if not raw_tools.builtin_tools:
        return ToolsConfig.model_validate(raw_tools.model_dump())
    return raw_tools


def list_tool_payloads() -> list[dict[str, Any]]:
    """List built-in execution tools for AgentDesk employee capability UI."""
    tools_cfg = _effective_tools_config(getattr(load_config(), "tools", None))
    return [
        {
            "key": key,
            "name": tool.name,
            "label": tool.name,
            "description": tool.description,
            "enabled": tool.enabled,
            "read_only": False,
            "async_execution": tool.async_execution,
        }
        for key, tool in tools_cfg.builtin_tools.items()
    ]
