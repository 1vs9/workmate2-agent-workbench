# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from qwenpaw.agentdesk import mutation_reload


def test_mutation_reload_agent_id_prefers_explicit_reload_agent() -> None:
    result = SimpleNamespace(agent_id="agent-1", reload_agent_id="agent-2")

    assert mutation_reload.mutation_reload_agent_id(result) == "agent-2"


def test_schedule_mutation_reload_uses_result_agent(monkeypatch) -> None:
    calls: list[tuple[object, str]] = []
    request = object()

    monkeypatch.setattr(
        mutation_reload,
        "schedule_agent_reload",
        lambda req, agent_id: calls.append((req, agent_id)),
    )

    scheduled = mutation_reload.schedule_mutation_reload(
        request,
        SimpleNamespace(agent_id="agent-1"),
    )

    assert scheduled == "agent-1"
    assert calls == [(request, "agent-1")]


def test_schedule_mutation_reload_skips_empty_agent(monkeypatch) -> None:
    calls: list[tuple[object, str]] = []

    monkeypatch.setattr(
        mutation_reload,
        "schedule_agent_reload",
        lambda req, agent_id: calls.append((req, agent_id)),
    )

    scheduled = mutation_reload.schedule_mutation_reload(
        object(),
        SimpleNamespace(payload={}),
    )

    assert scheduled is None
    assert calls == []
