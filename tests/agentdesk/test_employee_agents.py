# -*- coding: utf-8 -*-
"""Tests for AgentDesk employee agent provisioning."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from qwenpaw.app.routers import agents as agents_router
from qwenpaw.agentdesk.agents import resolve_agent_id
from qwenpaw.agentdesk import employee_agents
from qwenpaw.agentdesk.employee_agents import ensure_employee_agent_profile


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


def test_ensure_employee_agent_profile_creates_agent_for_chinese_name(
    monkeypatch,
    tmp_path,
):
    employee_name = "舆情分析师"
    store_data: dict[str, list[dict]] = {
        "employees": [
            {
                "name": employee_name,
                "desc": "负责舆情监测、分析与报告。",
                "skills": [],
            },
        ],
    }

    monkeypatch.setattr("qwenpaw.agentdesk.employee_agents.WORKING_DIR", str(tmp_path))
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_config",
        lambda: _profiles("default"),
    )

    captured: dict[str, object] = {}

    def fake_provision_agent_profile(**kwargs):
        captured.update(kwargs)
        workspace_dir = Path(kwargs["workspace_dir"])
        workspace_dir.mkdir(parents=True, exist_ok=True)
        post_hook = kwargs.get("post_workspace_init")
        if post_hook is not None:
            post_hook(workspace_dir, kwargs["requested_id"])
        return SimpleNamespace(
            id=kwargs["requested_id"],
            workspace_dir=str(workspace_dir),
            enabled=True,
        )

    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.provision_agent_profile",
        fake_provision_agent_profile,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.get_by_key",
        lambda collection, key, value: next(
            (item for item in store_data.get(collection, []) if item.get(key) == value),
            None,
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.upsert_by_key",
        lambda collection, key, value, payload: store_data.setdefault(collection, []).append(
            payload,
        ),
    )

    agent_id = ensure_employee_agent_profile(employee_name)

    assert agent_id is not None
    assert agent_id.startswith("emp_")
    assert captured["name"] == employee_name
    assert captured["requested_id"] == agent_id
    profile_path = tmp_path / "workspaces" / agent_id / "PROFILE.md"
    assert profile_path.exists()
    profile_text = profile_path.read_text(encoding="utf-8")
    assert employee_name in profile_text
    assert "default" in profile_text.lower()
    assert "不要" in profile_text


def test_resolve_agent_id_provisions_store_employee(monkeypatch, tmp_path):
    employee_name = "舆情分析师"

    monkeypatch.setattr(
        "qwenpaw.agentdesk.agents.load_config",
        lambda: _profiles("default"),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.ensure_employee_agent_profile",
        lambda name: "emp_deadbeef01" if name == employee_name else None,
    )

    assert resolve_agent_id(employee_name) == "emp_deadbeef01"
    assert resolve_agent_id("AgentDesk企伴") == "default"
    assert resolve_agent_id(None) == "default"


def test_ensure_employee_agent_profile_skips_bootstrap(monkeypatch, tmp_path):
    employee_name = "代码质量守护者"
    store_data: dict[str, list[dict]] = {
        "employees": [
            {
                "name": employee_name,
                "desc": "负责代码审查与质量保障。",
                "skills": [],
            },
        ],
    }

    monkeypatch.setattr("qwenpaw.agentdesk.employee_agents.WORKING_DIR", str(tmp_path))
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_config",
        lambda: _profiles("default"),
    )
    def fake_provision_agent_profile(**kwargs):
        workspace_dir = Path(kwargs["workspace_dir"])
        workspace_dir.mkdir(parents=True, exist_ok=True)
        post_hook = kwargs.get("post_workspace_init")
        if post_hook is not None:
            post_hook(workspace_dir, kwargs["requested_id"])
        return SimpleNamespace(
            id=kwargs["requested_id"],
            workspace_dir=str(workspace_dir),
            enabled=True,
        )

    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.provision_agent_profile",
        fake_provision_agent_profile,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.get_by_key",
        lambda collection, key, value: next(
            (item for item in store_data.get(collection, []) if item.get(key) == value),
            None,
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.upsert_by_key",
        lambda collection, key, value, payload: store_data.setdefault(collection, []).append(
            payload,
        ),
    )

    agent_id = ensure_employee_agent_profile(employee_name)
    workspace = tmp_path / "workspaces" / agent_id

    assert agent_id is not None
    assert not (workspace / "BOOTSTRAP.md").exists()
    assert (workspace / ".bootstrap_completed").is_file()
    assert (workspace / "EMPLOYEE.json").is_file()
    assert employee_name in (workspace / "EMPLOYEE.json").read_text(encoding="utf-8")


def test_employee_and_native_creation_share_provision_service():
    assert employee_agents.provision_agent_profile is agents_router.provision_agent_profile


def test_sync_signature_not_cached_when_skills_missing(monkeypatch, tmp_path):
    employee_name = "新闻分析师"
    agent_id = "emp_news01"
    workspace = tmp_path / "workspaces" / agent_id
    workspace.mkdir(parents=True, exist_ok=True)

    store_data: dict[str, list[dict]] = {
        "employees": [
            {
                "name": employee_name,
                "desc": "负责新闻分析。",
                "skills": ["missing-skill"],
                "agent_id": agent_id,
            },
        ],
    }

    monkeypatch.setattr("qwenpaw.agentdesk.employee_agents.WORKING_DIR", str(tmp_path))
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_config",
        lambda: SimpleNamespace(
            agents=SimpleNamespace(
                active_agent="default",
                agent_order=["default", agent_id],
                profiles={
                    "default": SimpleNamespace(
                        id="default",
                        workspace_dir=str(tmp_path / "workspaces" / "default"),
                        enabled=True,
                    ),
                    agent_id: SimpleNamespace(
                        id=agent_id,
                        workspace_dir=str(workspace),
                        enabled=True,
                    ),
                },
                language="zh",
            ),
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_agent_config",
        lambda _agent_id: SimpleNamespace(
            name=employee_name,
            description="负责新闻分析。",
            skill_names=["missing-skill"],
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.save_agent_config",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.get_by_key",
        lambda collection, key, value: next(
            (item for item in store_data.get(collection, []) if item.get(key) == value),
            None,
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.upsert_by_key",
        lambda collection, key, value, payload: None,
    )
    employee_agents._synced_employee_signatures.clear()

    ensure_employee_agent_profile(employee_name)

    assert agent_id not in employee_agents._synced_employee_signatures


def test_sync_existing_employee_clears_bootstrap(monkeypatch, tmp_path):
    employee_name = "代码质量守护者"
    agent_id = "emp_quality01"
    workspace = tmp_path / "workspaces" / agent_id
    workspace.mkdir(parents=True)
    (workspace / "BOOTSTRAP.md").write_text("# bootstrap", encoding="utf-8")

    store_data: dict[str, list[dict]] = {
        "employees": [
            {
                "name": employee_name,
                "desc": "负责代码审查。",
                "skills": [],
                "agent_id": agent_id,
            },
        ],
    }

    monkeypatch.setattr("qwenpaw.agentdesk.employee_agents.WORKING_DIR", str(tmp_path))
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_config",
        lambda: SimpleNamespace(
            agents=SimpleNamespace(
                active_agent="default",
                agent_order=["default", agent_id],
                profiles={
                    "default": SimpleNamespace(
                        id="default",
                        workspace_dir=str(tmp_path / "workspaces" / "default"),
                        enabled=True,
                    ),
                    agent_id: SimpleNamespace(
                        id=agent_id,
                        workspace_dir=str(workspace),
                        enabled=True,
                    ),
                },
                language="zh",
            ),
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_agent_config",
        lambda _agent_id: SimpleNamespace(
            name=employee_name,
            description="",
            skill_names=[],
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.save_agent_config",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.get_by_key",
        lambda collection, key, value: next(
            (item for item in store_data.get(collection, []) if item.get(key) == value),
            None,
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.upsert_by_key",
        lambda collection, key, value, payload: None,
    )

    resolved = ensure_employee_agent_profile(employee_name)

    assert resolved == agent_id
    assert not (workspace / "BOOTSTRAP.md").exists()
    assert (workspace / ".bootstrap_completed").is_file()
    assert (workspace / "EMPLOYEE.json").is_file()


def test_register_provisioned_agent_in_plaza_creates_store_entries(
    monkeypatch,
    tmp_path,
):
    agent_id = "emp_planner"
    display_name = "规划者"
    workspace = tmp_path / "workspaces" / agent_id
    workspace.mkdir(parents=True, exist_ok=True)
    store_data: dict[str, list[dict]] = {"employees": [], "plaza": []}

    monkeypatch.setattr("qwenpaw.agentdesk.employee_agents.WORKING_DIR", str(tmp_path))
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_config",
        lambda: _profiles(agent_id),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_agent_config",
        lambda _agent_id: SimpleNamespace(
            name=display_name,
            description="负责拆解目标与制定执行计划。",
            skill_names=["make_plan"],
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents._sync_employee_agent",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.get_by_key",
        lambda collection, key, value: next(
            (item for item in store_data.get(collection, []) if item.get(key) == value),
            None,
        ),
    )

    def fake_upsert(collection, key, value, payload):
        items = store_data.setdefault(collection, [])
        for idx, item in enumerate(items):
            if item.get(key) == value:
                items[idx] = {**item, **payload, key: value}
                return items[idx]
        created = {**payload, key: value}
        items.append(created)
        return created

    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.upsert_by_key",
        fake_upsert,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.list_items",
        lambda collection: list(store_data.get(collection, [])),
    )

    from qwenpaw.agentdesk.employee_agents import register_provisioned_agent_in_plaza

    assert register_provisioned_agent_in_plaza(agent_id) is True
    assert register_provisioned_agent_in_plaza(agent_id) is False

    plaza = next(item for item in store_data["plaza"] if item["name"] == display_name)
    employee = next(item for item in store_data["employees"] if item["name"] == display_name)
    assert plaza["joined"] is True
    assert employee["agent_id"] == agent_id
    assert "make_plan" in plaza["skills"]
    assert "拆解目标" in plaza["desc"]


def test_register_provisioned_agent_backfills_empty_store_desc(
    monkeypatch,
    tmp_path,
):
    agent_id = "emp_writer"
    display_name = "撰稿人"
    workspace = tmp_path / "workspaces" / agent_id
    workspace.mkdir(parents=True, exist_ok=True)
    store_data: dict[str, list[dict]] = {
        "employees": [
            {
                "name": display_name,
                "agent_id": agent_id,
                "desc": "",
                "skills": ["file_reader"],
            },
        ],
        "plaza": [
            {
                "name": display_name,
                "desc": "",
                "skills": ["file_reader"],
                "joined": True,
            },
        ],
    }

    monkeypatch.setattr("qwenpaw.agentdesk.employee_agents.WORKING_DIR", str(tmp_path))
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_config",
        lambda: _profiles(agent_id),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_agent_config",
        lambda _agent_id: SimpleNamespace(
            name=display_name,
            description="负责撰写与润色报告。",
            skill_names=["file_reader"],
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents._sync_employee_agent",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.get_by_key",
        lambda collection, key, value: next(
            (item for item in store_data.get(collection, []) if item.get(key) == value),
            None,
        ),
    )

    def fake_upsert(collection, key, value, payload):
        items = store_data.setdefault(collection, [])
        for idx, item in enumerate(items):
            if item.get(key) == value:
                items[idx] = {**item, **payload, key: value}
                return items[idx]
        created = {**payload, key: value}
        items.append(created)
        return created

    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.upsert_by_key",
        fake_upsert,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.list_items",
        lambda collection: list(store_data.get(collection, [])),
    )

    from qwenpaw.agentdesk.employee_agents import register_provisioned_agent_in_plaza

    assert register_provisioned_agent_in_plaza(agent_id) is True
    plaza = next(item for item in store_data["plaza"] if item["name"] == display_name)
    employee = next(item for item in store_data["employees"] if item["name"] == display_name)
    assert plaza["desc"] == "负责撰写与润色报告。"
    assert employee["desc"] == "负责撰写与润色报告。"


def test_delete_employee_agent_removes_store_and_profile(monkeypatch, tmp_path):
    agent_id = "emp_gone01"
    workspace = tmp_path / "workspaces" / agent_id
    workspace.mkdir(parents=True, exist_ok=True)

    store_data: dict[str, list[dict]] = {
        "plaza": [{"name": "文案助手", "desc": "writes", "joined": True}],
        "employees": [
            {
                "name": "文案助手",
                "agent_id": agent_id,
                "desc": "writes",
                "skills": [],
            },
        ],
    }
    saved: dict[str, object] = {}

    def fake_get_by_key(collection: str, key: str, value: str):
        for item in store_data.get(collection, []):
            if str(item.get(key) or "") == value:
                return dict(item)
        return None

    def fake_delete_by_key(collection: str, key: str, value: str) -> bool:
        items = store_data.get(collection, [])
        for index, item in enumerate(items):
            if str(item.get(key) or "") == value:
                items.pop(index)
                return True
        return False

    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_config",
        lambda: _profiles("default", agent_id),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.store.get_by_key",
        fake_get_by_key,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.store.delete_by_key",
        fake_delete_by_key,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.save_config",
        lambda config: saved.update({"config": config}),
    )

    from qwenpaw.agentdesk.employee_agents import delete_employee_agent

    assert delete_employee_agent("文案助手") is True
    assert not store_data["plaza"]
    assert not store_data["employees"]
    assert agent_id not in saved["config"].agents.profiles  # type: ignore[union-attr]


def test_sync_orphan_employee_agents_to_plaza_skips_default(monkeypatch, tmp_path):
    store_data: dict[str, list[dict]] = {"employees": [], "plaza": []}
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_config",
        lambda: _profiles("default", "emp_writer"),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.register_provisioned_agent_in_plaza",
        lambda agent_id: agent_id == "emp_writer",
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.list_items",
        lambda collection: list(store_data.get(collection, [])),
    )

    from qwenpaw.agentdesk.employee_agents import sync_orphan_employee_agents_to_plaza

    assert sync_orphan_employee_agents_to_plaza() == 1


def test_build_agent_display_name_index_reads_configs_once(monkeypatch):
    profiles = {
        "emp_a": SimpleNamespace(),
        "emp_b": SimpleNamespace(),
    }
    calls: list[str] = []

    def fake_load(agent_id):
        calls.append(agent_id)
        return SimpleNamespace(name=f"Name-{agent_id}")

    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_agent_config",
        fake_load,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.is_plaza_hidden_assignee",
        lambda _agent_id: False,
    )
    employee_agents.invalidate_agent_display_name_index()

    index = employee_agents.build_agent_display_name_index(profiles)
    assert index["Name-emp_a"] == "emp_a"
    assert index["Name-emp_b"] == "emp_b"
    assert len(calls) == 2

    employee_agents.build_agent_display_name_index(profiles)
    assert len(calls) == 2


def test_lookup_agent_id_skips_provisioning(monkeypatch):
    from qwenpaw.agentdesk.agents import lookup_agent_id

    monkeypatch.setattr(
        "qwenpaw.agentdesk.agents.load_config",
        lambda: _profiles("default", "emp_writer"),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.build_agent_display_name_index",
        lambda _profiles: {"文案助手": "emp_writer"},
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.store.store.get_by_key",
        lambda collection, key, value: (
            {"name": "文案助手", "agent_id": "emp_writer"}
            if collection == "employees" and value == "文案助手"
            else None
        ),
    )

    def fail_ensure(*_args, **_kwargs):
        raise AssertionError("ensure_employee_agent_profile must not run on lookup")

    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.ensure_employee_agent_profile",
        fail_ensure,
    )

    assert lookup_agent_id("文案助手") == "emp_writer"

