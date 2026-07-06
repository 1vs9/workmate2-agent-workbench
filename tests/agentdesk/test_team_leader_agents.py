# -*- coding: utf-8 -*-
"""Tests for hidden team leader agent provisioning."""

from pathlib import Path
from types import SimpleNamespace

import pytest

import qwenpaw.constant as qwenpaw_constant
from qwenpaw.agentdesk.default_agent import is_plaza_hidden_assignee
from qwenpaw.agentdesk.store import AgentDeskStore
from qwenpaw.agentdesk.team_leader_agents import (
    is_team_leader_agent_id,
    is_team_leader_hidden,
    provision_team_leader_agent,
    team_leader_display_name,
    delete_team_leader_agent,
)


@pytest.fixture
def agentdesk_env(tmp_path, monkeypatch):
    store_path = tmp_path / "store.json"
    monkeypatch.setattr(qwenpaw_constant, "WORKING_DIR", str(tmp_path))
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_leader_agents.WORKING_DIR",
        str(tmp_path),
    )
    store = AgentDeskStore(store_path)
    monkeypatch.setattr("qwenpaw.agentdesk.store.store", store)

    workspaces = tmp_path / "workspaces"
    default_ws = workspaces / "default"
    default_ws.mkdir(parents=True)

    saved_configs: dict[str, object] = {}

    class FakeAgentConfig:
        def __init__(self, agent_id: str, name: str = "", description: str = ""):
            self.id = agent_id
            self.name = name
            self.description = description
            self.workspace_dir = str(workspaces / agent_id)
            self.skill_names = []

    profiles: dict[str, SimpleNamespace] = {
        "default": SimpleNamespace(
            id="default",
            workspace_dir=str(default_ws),
            enabled=True,
        ),
    }
    agent_order = ["default"]

    def load_config():
        return SimpleNamespace(
            agents=SimpleNamespace(
                active_agent="default",
                profiles=profiles,
                agent_order=agent_order,
                language="zh",
            ),
        )

    def save_config(config):
        nonlocal agent_order
        agent_order = list(config.agents.agent_order)

    def load_agent_config(agent_id: str):
        if agent_id not in saved_configs:
            saved_configs[agent_id] = FakeAgentConfig(agent_id)
        return saved_configs[agent_id]

    def save_agent_config(agent_id: str, cfg):
        saved_configs[agent_id] = cfg

    monkeypatch.setattr("qwenpaw.agentdesk.team_leader_agents.load_config", load_config)
    monkeypatch.setattr("qwenpaw.agentdesk.team_leader_agents.save_config", save_config)
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_leader_agents.load_agent_config",
        load_agent_config,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_leader_agents.save_agent_config",
        save_agent_config,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_leader_agents._initialize_agent_workspace",
        lambda workspace_dir, **kwargs: workspace_dir.mkdir(parents=True, exist_ok=True),
    )

    return SimpleNamespace(
        tmp_path=tmp_path,
        profiles=profiles,
        saved_configs=saved_configs,
    )


def test_team_leader_agent_id_prefix():
    assert is_team_leader_agent_id("lead_abc123")
    assert not is_team_leader_agent_id("emp_abc123")


def test_team_leader_hidden_by_name_suffix():
    assert is_team_leader_hidden("增长团队·leader")
    assert is_team_leader_hidden("增长团队·编排者")
    assert not is_team_leader_hidden("Analyst")


def test_plaza_hidden_includes_team_leader():
    assert is_plaza_hidden_assignee("lead_team001")
    assert is_plaza_hidden_assignee("增长团队·leader")
    assert is_plaza_hidden_assignee("增长团队·编排者")


def test_provision_team_leader_writes_soul_and_profile(agentdesk_env):
    info = provision_team_leader_agent(
        team_id="team001",
        team_name="增长团队",
        team_prompt="协调投放与内容成员。",
        workers=["投放专家", "内容编辑"],
    )

    assert info["agent_id"].startswith("lead_")
    assert info["leader_name"] == team_leader_display_name("增长团队")
    assert info["agent_id"] in agentdesk_env.profiles

    workspace = agentdesk_env.tmp_path / "workspaces" / info["agent_id"]
    soul = (workspace / "SOUL.md").read_text(encoding="utf-8")
    profile = (workspace / "PROFILE.md").read_text(encoding="utf-8")
    meta = (workspace / "TEAM_LEADER.json").read_text(encoding="utf-8")

    assert "只做调度与规划" in soul
    assert "团队提示词（上下文）" in soul
    assert "协调投放与内容成员" in soul
    assert "BOOTSTRAP.md" in soul
    assert "本角色无此流程" in soul
    assert "投放专家" in profile
    assert '"is_team_leader":true' in meta
    assert '"team_id":"team001"' in meta


def test_provision_team_leader_installs_native_collaboration_skills(
    agentdesk_env,
    monkeypatch,
):
    captured: dict[str, object] = {}

    def fake_initialize(workspace_dir, **kwargs):
        captured.update(kwargs)
        workspace_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_leader_agents._initialize_agent_workspace",
        fake_initialize,
    )
    provision_team_leader_agent(
        team_id="team-skills",
        team_name="技能团队",
        team_prompt="",
        workers=["成员A"],
    )
    assert captured.get("skill_names") == ["multi_agent_collaboration", "make_plan"]


def _stub_initialize_agent_workspace_deps(monkeypatch):
    import qwenpaw.config as config_module
    from qwenpaw.app.routers import agents as agents_router

    monkeypatch.setattr(
        config_module,
        "load_config",
        lambda: SimpleNamespace(
            agents=SimpleNamespace(language="zh"),
        ),
    )
    monkeypatch.setattr(
        agents_router,
        "_apply_workspace_md_templates",
        lambda workspace_dir, language, md_template_id=None: None,
    )
    monkeypatch.setattr(
        agents_router,
        "_install_initial_skills",
        lambda workspace_dir, skill_names: None,
    )


def test_provision_team_leader_creates_runtime_workspace(
    agentdesk_env,
    monkeypatch,
):
    """Leader provisioning must create sessions/memory even without pre-existing dir."""
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_leader_agents._initialize_agent_workspace",
        __import__(
            "qwenpaw.app.routers.agents",
            fromlist=["_initialize_agent_workspace"],
        )._initialize_agent_workspace,
    )
    _stub_initialize_agent_workspace_deps(monkeypatch)

    info = provision_team_leader_agent(
        team_id="team003",
        team_name="交易分析团队",
        team_prompt="协调交易分析成员。",
        workers=["Analyst"],
    )

    workspace = agentdesk_env.tmp_path / "workspaces" / info["agent_id"]
    assert workspace.is_dir()
    assert (workspace / "sessions").is_dir()
    assert (workspace / "memory").is_dir()
    assert (workspace / "jobs.json").is_file()
    assert (workspace / "chats.json").is_file()


def test_sync_existing_leader_ensures_runtime_workspace(
    agentdesk_env,
    monkeypatch,
):
    """Re-syncing an existing leader profile must backfill missing runtime dirs."""
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_leader_agents._initialize_agent_workspace",
        __import__(
            "qwenpaw.app.routers.agents",
            fromlist=["_initialize_agent_workspace"],
        )._initialize_agent_workspace,
    )
    _stub_initialize_agent_workspace_deps(monkeypatch)

    agent_id = "lead_team004"
    agentdesk_env.profiles[agent_id] = SimpleNamespace(
        id=agent_id,
        workspace_dir=str(agentdesk_env.tmp_path / "workspaces" / agent_id),
        enabled=True,
    )

    provision_team_leader_agent(
        team_id="team004",
        team_name="研发组",
        team_prompt="",
        workers=[],
        agent_id=agent_id,
    )

    workspace = agentdesk_env.tmp_path / "workspaces" / agent_id
    assert (workspace / "sessions").is_dir()
    assert (workspace / "SOUL.md").is_file()


def test_provision_team_leader_skips_bootstrap(agentdesk_env):
    info = provision_team_leader_agent(
        team_id="team005",
        team_name="运营组",
        team_prompt="优先响应高优任务。",
        workers=["运营专员"],
    )

    workspace = agentdesk_env.tmp_path / "workspaces" / info["agent_id"]
    assert not (workspace / "BOOTSTRAP.md").exists()
    assert (workspace / ".bootstrap_completed").is_file()
    assert (workspace / "TEAM_LEADER.json").is_file()


def test_provision_team_leader_empty_prompt_keeps_orchestrator_template(agentdesk_env):
    info = provision_team_leader_agent(
        team_id="team006",
        team_name="空提示词组",
        team_prompt="",
        workers=[],
    )

    workspace = agentdesk_env.tmp_path / "workspaces" / info["agent_id"]
    soul = (workspace / "SOUL.md").read_text(encoding="utf-8")
    assert "只做调度与规划" in soul
    assert "团队提示词" not in soul


def test_sync_existing_leader_clears_bootstrap(agentdesk_env):
    agent_id = "lead_team007"
    workspace = agentdesk_env.tmp_path / "workspaces" / agent_id
    workspace.mkdir(parents=True)
    (workspace / "BOOTSTRAP.md").write_text("# bootstrap", encoding="utf-8")
    agentdesk_env.profiles[agent_id] = SimpleNamespace(
        id=agent_id,
        workspace_dir=str(workspace),
        enabled=True,
    )

    provision_team_leader_agent(
        team_id="team007",
        team_name="遗留组",
        team_prompt="同步后注入上下文。",
        workers=["成员A"],
        agent_id=agent_id,
    )

    assert not (workspace / "BOOTSTRAP.md").exists()
    assert (workspace / ".bootstrap_completed").is_file()
    soul = (workspace / "SOUL.md").read_text(encoding="utf-8")
    assert "同步后注入上下文" in soul
    assert "只做调度与规划" in soul


def test_provision_team_leader_enables_sync_delegation_tools(agentdesk_env):
    """Leader toolset must use synchronous ``chat_with_agent`` for passthrough."""
    info = provision_team_leader_agent(
        team_id="team-tools",
        team_name="工具团队",
        team_prompt="",
        workers=["Alice"],
    )

    cfg = agentdesk_env.saved_configs[info["agent_id"]]
    builtin = cfg.tools.builtin_tools
    assert builtin["chat_with_agent"].enabled is True
    assert builtin["submit_to_agent"].enabled is False
    assert builtin["check_agent_task"].enabled is False
    assert builtin["list_agents"].enabled is True
    # Coordinator-only whitelist: every non-delegation builtin must be disabled
    # so the leader's per-turn tool schema (and thus prompt size / TTFT) stays
    # minimal and the leader cannot execute worker tasks itself.
    for name in ("execute_shell_command", "read_file", "write_file", "edit_file",
                 "grep_search", "glob_search", "browser_use"):
        assert builtin[name].enabled is False, name


def test_sync_existing_leader_enables_sync_delegation_tools(agentdesk_env):
    """Re-syncing a leader provisioned before the fix must enable sync
    ``chat_with_agent`` and disable async background delegation."""
    from qwenpaw.config.config import AgentProfileConfig, ToolsConfig

    agent_id = "lead_toolsync"
    workspace = agentdesk_env.tmp_path / "workspaces" / agent_id
    agentdesk_env.profiles[agent_id] = SimpleNamespace(
        id=agent_id,
        workspace_dir=str(workspace),
        enabled=True,
    )
    # Pre-fix state: synchronous delegation enabled, async tools disabled.
    existing = AgentProfileConfig(
        id=agent_id,
        name="旧名",
        description="旧描述",
        tools=ToolsConfig(),
    )
    existing.tools.builtin_tools["chat_with_agent"].enabled = True
    existing.tools.builtin_tools["submit_to_agent"].enabled = False
    existing.tools.builtin_tools["check_agent_task"].enabled = False
    agentdesk_env.saved_configs[agent_id] = existing

    provision_team_leader_agent(
        team_id="toolsync",
        team_name="同步工具组",
        team_prompt="",
        workers=[],
        agent_id=agent_id,
    )

    cfg = agentdesk_env.saved_configs[agent_id]
    assert cfg.tools.builtin_tools["chat_with_agent"].enabled is True
    assert cfg.tools.builtin_tools["submit_to_agent"].enabled is False
    assert cfg.tools.builtin_tools["check_agent_task"].enabled is False


def test_delete_team_leader_removes_profile(agentdesk_env):
    info = provision_team_leader_agent(
        team_id="team002",
        team_name="研发组",
        team_prompt="",
        workers=[],
    )
    delete_team_leader_agent(
        {"id": "team002", "leader_agent_id": info["agent_id"]},
    )
    assert info["agent_id"] not in agentdesk_env.profiles