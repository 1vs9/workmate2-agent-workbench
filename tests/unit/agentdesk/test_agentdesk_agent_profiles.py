# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from qwenpaw.agentdesk import agent_profiles


def test_agent_desc_and_skills_strips_values(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_profiles,
        "load_agent_config",
        lambda agent_id: SimpleNamespace(
            description="  hello  ",
            skill_names=[" search ", "", "write"],
        ),
    )

    assert agent_profiles.agent_desc_and_skills("agent-1") == (
        "hello",
        ["search", "write"],
    )


def test_agent_desc_and_skills_falls_back_on_config_error(monkeypatch) -> None:
    def _load(agent_id: str) -> SimpleNamespace:
        raise RuntimeError("broken")

    monkeypatch.setattr(agent_profiles, "load_agent_config", _load)

    assert agent_profiles.agent_desc_and_skills("agent-1") == ("", [])
    assert agent_profiles.agent_description("agent-1") == ""
    assert agent_profiles.agent_skill_names("agent-1") == []


def test_agent_display_name_prefers_store_override(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_profiles,
        "load_agent_config",
        lambda agent_id: SimpleNamespace(name="Config Name"),
    )

    assert agent_profiles.agent_display_name(
        "agent-1",
        {"item-1": {"agent_id": "agent-1", "name": "Store Name"}},
    ) == "Store Name"


def test_agent_display_name_ignores_emp_prefixed_labels(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_profiles,
        "load_agent_config",
        lambda agent_id: SimpleNamespace(name="emp_hidden"),
    )

    assert agent_profiles.agent_display_name(
        "agent-1",
        {"item-1": {"agent_id": "agent-1", "name": "emp_store"}},
    ) == "agent-1"


def test_agent_display_name_uses_config_name(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_profiles,
        "load_agent_config",
        lambda agent_id: SimpleNamespace(name="Config Name"),
    )

    assert agent_profiles.agent_display_name("agent-1", {}) == "Config Name"
