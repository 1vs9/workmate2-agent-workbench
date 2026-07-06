# -*- coding: utf-8 -*-
"""Agent reload scheduling for AgentDesk mutation results."""

from __future__ import annotations

from typing import Any

from ..app.utils import schedule_agent_reload


def mutation_reload_agent_id(result: Any) -> str | None:
    """Return the agent id a mutation result asks the runtime to reload."""
    explicit = str(getattr(result, "reload_agent_id", "") or "").strip()
    if explicit:
        return explicit
    agent_id = str(getattr(result, "agent_id", "") or "").strip()
    return agent_id or None


def schedule_mutation_reload(request: Any, result: Any) -> str | None:
    """Schedule a runtime reload for mutation results that target an agent."""
    agent_id = mutation_reload_agent_id(result)
    if not agent_id:
        return None
    schedule_agent_reload(request, agent_id)
    return agent_id
