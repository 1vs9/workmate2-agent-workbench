# -*- coding: utf-8 -*-
"""Tests for AgentDesk default agent mapping and persona."""

from types import SimpleNamespace

from qwenpaw.constant import BUILTIN_QA_AGENT_ID, BUILTIN_QA_AGENT_NAME
from qwenpaw.agentdesk.agents import display_sender, resolve_agent_id
from qwenpaw.agentdesk.default_agent import (
    DEFAULT_AGENT_ID,
    DEFAULT_DISPLAY_NAME,
    AGENTDESK_DEFAULT_DESCRIPTION,
    AGENTDESK_DEFAULT_SYSTEM_PROMPT,
    apply_agentdesk_default_persona,
    ensure_agentdesk_default_agent_identity,
    is_builtin_qa_assignee,
    is_default_agentdesk_assignee,
    is_plaza_hidden_assignee,
)


def _profiles(*agent_ids: str) -> SimpleNamespace:
    return SimpleNamespace(
        agents=SimpleNamespace(
            active_agent=DEFAULT_AGENT_ID,
            profiles={
                agent_id: SimpleNamespace(id=agent_id) for agent_id in agent_ids
            },
        ),
    )


def test_resolve_agent_id_maps_agentdesk_brand_to_default(monkeypatch):
    monkeypatch.setattr(
        "qwenpaw.agentdesk.agents.load_config",
        lambda: _profiles(DEFAULT_AGENT_ID, "Analyst"),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.ensure_employee_agent_profile",
        lambda name: None,
    )

    assert resolve_agent_id(None) == DEFAULT_AGENT_ID
    assert resolve_agent_id("") == DEFAULT_AGENT_ID
    assert resolve_agent_id(DEFAULT_DISPLAY_NAME) == DEFAULT_AGENT_ID
    assert resolve_agent_id("AgentDesk") == DEFAULT_AGENT_ID
    assert resolve_agent_id("Analyst") == "Analyst"


def test_display_sender_uses_agentdesk_brand_for_default():
    assert display_sender(None, DEFAULT_AGENT_ID) == DEFAULT_DISPLAY_NAME
    assert display_sender(DEFAULT_DISPLAY_NAME, DEFAULT_AGENT_ID) == DEFAULT_DISPLAY_NAME
    assert display_sender("Analyst", "Analyst") == "Analyst"


def test_plaza_hidden_assignee_names():
    assert is_default_agentdesk_assignee(DEFAULT_DISPLAY_NAME)
    assert is_default_agentdesk_assignee("default")
    assert is_plaza_hidden_assignee("AgentDesk企伴")
    assert not is_plaza_hidden_assignee("Analyst")


def test_builtin_qa_assignee_is_hidden():
    assert is_builtin_qa_assignee(BUILTIN_QA_AGENT_ID)
    assert is_builtin_qa_assignee(BUILTIN_QA_AGENT_NAME)
    assert is_plaza_hidden_assignee(BUILTIN_QA_AGENT_ID)
    assert is_plaza_hidden_assignee(BUILTIN_QA_AGENT_NAME)
    assert not is_builtin_qa_assignee("Analyst")
    assert not is_plaza_hidden_assignee("Analyst")


def test_agentdesk_default_description():
    assert "企业智能" in AGENTDESK_DEFAULT_DESCRIPTION


def test_ensure_agentdesk_default_agent_identity_updates_config(monkeypatch, tmp_path):
    workspace = tmp_path / "workspaces" / "default"
    workspace.mkdir(parents=True)
    saved: dict[str, object] = {}

    class FakeConfig:
        name = "Default Agent"
        description = "Default QwenPaw agent"
        workspace_dir = str(workspace)

    monkeypatch.setattr(
        "qwenpaw.agentdesk.default_agent.load_agent_config",
        lambda _agent_id: FakeConfig(),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.default_agent.save_agent_config",
        lambda agent_id, cfg: saved.update({"agent_id": agent_id, "config": cfg}),
    )

    ensure_agentdesk_default_agent_identity()

    assert saved["agent_id"] == DEFAULT_AGENT_ID
    assert saved["config"].name == DEFAULT_DISPLAY_NAME
    assert saved["config"].description == AGENTDESK_DEFAULT_DESCRIPTION
    profile = (workspace / "PROFILE.md").read_text(encoding="utf-8")
    assert DEFAULT_DISPLAY_NAME in profile
    assert AGENTDESK_DEFAULT_DESCRIPTION in profile


def test_ensure_agentdesk_default_agent_enables_auto_memory(monkeypatch, tmp_path):
    """default is the only LTM agent, so its native auto-memory must be on."""
    workspace = tmp_path / "workspaces" / "default"
    workspace.mkdir(parents=True)
    saved: dict[str, object] = {}

    search_cfg = SimpleNamespace(enabled=False)
    memory_cfg = SimpleNamespace(
        auto_memory_search_config=search_cfg,
        auto_memory_interval=None,
    )
    running = SimpleNamespace(reme_light_memory_config=memory_cfg)

    class FakeConfig:
        name = DEFAULT_DISPLAY_NAME
        description = AGENTDESK_DEFAULT_DESCRIPTION
        workspace_dir = str(workspace)
        running = SimpleNamespace(reme_light_memory_config=memory_cfg)

    config = FakeConfig()
    config.running = running

    monkeypatch.setattr(
        "qwenpaw.agentdesk.default_agent.load_agent_config",
        lambda _agent_id: config,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.default_agent.save_agent_config",
        lambda agent_id, cfg: saved.update({"agent_id": agent_id, "config": cfg}),
    )

    ensure_agentdesk_default_agent_identity()

    assert search_cfg.enabled is True
    assert memory_cfg.auto_memory_interval == 5
    assert saved.get("agent_id") == DEFAULT_AGENT_ID


def test_ensure_agentdesk_default_agent_preserves_memory_customization(monkeypatch, tmp_path):
    """User-tuned memory settings (and the nightly job) must be preserved."""
    workspace = tmp_path / "workspaces" / "default"
    workspace.mkdir(parents=True)
    saved: dict[str, object] = {}

    search_cfg = SimpleNamespace(enabled=True)
    memory_cfg = SimpleNamespace(
        auto_memory_search_config=search_cfg,
        auto_memory_interval=12,
    )

    class FakeConfig:
        name = DEFAULT_DISPLAY_NAME
        description = AGENTDESK_DEFAULT_DESCRIPTION
        workspace_dir = str(workspace)
        running = SimpleNamespace(reme_light_memory_config=memory_cfg)

    monkeypatch.setattr(
        "qwenpaw.agentdesk.default_agent.load_agent_config",
        lambda _agent_id: FakeConfig(),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.default_agent.save_agent_config",
        lambda agent_id, cfg: saved.update({"agent_id": agent_id, "config": cfg}),
    )

    ensure_agentdesk_default_agent_identity()

    # Nothing changed -> the user's interval is untouched and no save happens.
    assert memory_cfg.auto_memory_interval == 12
    assert search_cfg.enabled is True
    assert "config" not in saved


def test_agentdesk_default_persona_avoids_qwenpaw_brand():
    assert "QwenPaw" not in AGENTDESK_DEFAULT_SYSTEM_PROMPT
    assert "QA Agent" not in AGENTDESK_DEFAULT_SYSTEM_PROMPT
    assert "你用的什么模型" in AGENTDESK_DEFAULT_SYSTEM_PROMPT
    assert "list_agents" in AGENTDESK_DEFAULT_SYSTEM_PROMPT


def test_apply_agentdesk_default_persona_appends_once():
    running = SimpleNamespace(auto_continue_on_text_only=False)
    agent = SimpleNamespace(
        _system_prompt="Base prompt",
        _agent_config=SimpleNamespace(running=running),
        state=SimpleNamespace(context=[]),
    )

    apply_agentdesk_default_persona(agent)

    assert running.auto_continue_on_text_only is True
    assert AGENTDESK_DEFAULT_SYSTEM_PROMPT.strip() in agent._system_prompt
    assert "中文优先" in agent._system_prompt
    first = agent._system_prompt
    apply_agentdesk_default_persona(agent)
    assert agent._system_prompt == first
