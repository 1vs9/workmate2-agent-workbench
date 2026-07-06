# -*- coding: utf-8 -*-
"""Tests for packaged AgentDesk builtin plaza / employee / team seeding."""

from __future__ import annotations

import os
from types import SimpleNamespace

from qwenpaw.agentdesk.builtin_agents import (
    catalog_version,
    dismiss_builtin_agent,
    ensure_builtin_agents,
    ensure_builtin_plaza_catalog,
    load_builtin_catalog,
    maybe_seed_builtin_agents,
    should_seed_builtin_agents,
)
from qwenpaw.agentdesk.store import AgentDeskStore


def _profiles(*agent_ids: str) -> SimpleNamespace:
    return SimpleNamespace(
        agents=SimpleNamespace(
            active_agent="default",
            agent_order=list(agent_ids),
            profiles={
                agent_id: SimpleNamespace(
                    id=agent_id,
                    workspace_dir=f"/tmp/ws/{agent_id}",
                    enabled=True,
                )
                for agent_id in agent_ids
            },
            language="zh",
        ),
    )


def test_load_builtin_catalog_has_expected_roles():
    catalog = load_builtin_catalog()
    plaza_names = {item["name"] for item in catalog["plaza"]}
    team_names = {item["name"] for item in catalog["teams"]}
    assert "SIM卡开通业务员" in plaza_names
    assert "PPT大师" in plaza_names
    assert "开户协同小队" in plaza_names
    assert "深度调研团队" in team_names
    assert "规划者" in plaza_names
    assert len(catalog["plaza"]) == 27
    assert len(catalog["teams"]) == 2
    assert catalog["version"] == 2


def test_ensure_builtin_plaza_catalog_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "qwenpaw.agentdesk.builtin_agents.store",
        AgentDeskStore(tmp_path / "store.json"),
    )
    first = ensure_builtin_plaza_catalog()
    second = ensure_builtin_plaza_catalog()
    from qwenpaw.agentdesk import builtin_agents as builtin_module

    plaza = builtin_module.store.list_items("plaza")

    assert first > 0
    assert second == 0
    assert len(plaza) == first
    assert any(item["name"] == "文档大师" for item in plaza)


def test_ensure_builtin_agents_provisions_employee_agent(
    tmp_path,
    monkeypatch,
):
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr("qwenpaw.agentdesk.builtin_agents.store", store)
    monkeypatch.setattr("qwenpaw.agentdesk.employee_agents.store", store)
    monkeypatch.setattr("qwenpaw.agentdesk.employee_agents.WORKING_DIR", str(tmp_path))
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_config",
        lambda: _profiles("default"),
    )

    saved_agents: dict[str, object] = {}

    def fake_save_config(config):
        pass

    def fake_save_agent_config(agent_id, agent_config):
        saved_agents[agent_id] = agent_config

    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.provision_agent_profile",
        lambda **kwargs: (
            kwargs["workspace_dir"].mkdir(parents=True, exist_ok=True)
            or (
            kwargs["post_workspace_init"](
                kwargs["workspace_dir"],
                kwargs["requested_id"],
            )
            if kwargs.get("post_workspace_init")
            else None
            )
        )
        or SimpleNamespace(
            id=kwargs["requested_id"],
            workspace_dir=str(kwargs["workspace_dir"]),
            enabled=True,
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_leader_agents._initialize_agent_workspace",
        lambda workspace_dir, skill_names=None, language=None: None,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_leader_agents.load_config",
        lambda: _profiles("default"),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_leader_agents.save_config",
        fake_save_config,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.team_leader_agents.save_agent_config",
        fake_save_agent_config,
    )

    summary = ensure_builtin_agents(defer_agent_provision=False)

    assert summary["plaza_added"] > 0
    assert summary["employees_provisioned"] > 0
    employee = store.get_by_key("employees", "name", "文档大师")
    assert employee is not None
    assert employee.get("agent_id")
    assert employee["agent_id"].startswith("emp_")
    profile_path = tmp_path / "workspaces" / employee["agent_id"] / "PROFILE.md"
    assert profile_path.is_file()
    team = store.get_by_key("teams", "id", "builtin-account-opening-team")
    assert team is not None
    assert team.get("leader_agent_id")
    assert "SIM卡开通业务员" in team.get("members", [])


def test_store_is_uninitialized_on_empty_file(tmp_path):
    store = AgentDeskStore(tmp_path / "store.json")
    assert store.is_uninitialized() is True


def test_should_seed_on_empty_store(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr("qwenpaw.agentdesk.builtin_agents.store", store)
    monkeypatch.delenv("AGENTDESK_RESEED_BUILTINS", raising=False)
    assert should_seed_builtin_agents() is True


def test_should_not_seed_when_store_has_plaza(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr("qwenpaw.agentdesk.builtin_agents.store", store)
    monkeypatch.delenv("AGENTDESK_RESEED_BUILTINS", raising=False)
    store.upsert_by_key(
        "plaza",
        "name",
        "自定义岗位",
        {"name": "自定义岗位", "desc": "用户自建"},
    )
    store.patch_meta({"builtin_seed_version": catalog_version()})
    assert should_seed_builtin_agents() is False


def test_maybe_seed_skips_initialized_store(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr("qwenpaw.agentdesk.builtin_agents.store", store)
    monkeypatch.delenv("AGENTDESK_RESEED_BUILTINS", raising=False)
    store.upsert_by_key(
        "employees",
        "name",
        "已有员工",
        {"name": "已有员工", "desc": "test"},
    )
    store.patch_meta({"builtin_seed_version": catalog_version()})
    assert maybe_seed_builtin_agents() is None


def test_force_reseed_env(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr("qwenpaw.agentdesk.builtin_agents.store", store)
    store.upsert_by_key(
        "plaza",
        "name",
        "已有岗位",
        {"name": "已有岗位", "desc": "test"},
    )
    store.patch_meta({"builtin_seed_version": catalog_version()})
    monkeypatch.setenv("AGENTDESK_RESEED_BUILTINS", "1")
    assert should_seed_builtin_agents() is True


def test_dismissed_builtin_not_reseeded(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr("qwenpaw.agentdesk.builtin_agents.store", store)
    dismiss_builtin_agent("文档大师")
    ensure_builtin_plaza_catalog()
    plaza = store.list_items("plaza")
    assert not any(item["name"] == "文档大师" for item in plaza)
    assert "doc-master" in store.read_meta().get("dismissed_builtin_ids", [])
    assert len(plaza) == len(load_builtin_catalog()["plaza"]) - 1


def test_catalog_upgrade_triggers_seed(tmp_path, monkeypatch):
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr("qwenpaw.agentdesk.builtin_agents.store", store)
    monkeypatch.delenv("AGENTDESK_RESEED_BUILTINS", raising=False)
    store.upsert_by_key(
        "plaza",
        "name",
        "自定义岗位",
        {"name": "自定义岗位", "desc": "用户自建"},
    )
    store.patch_meta({"builtin_seed_version": 0})
    assert should_seed_builtin_agents() is True
