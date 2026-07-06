# -*- coding: utf-8 -*-
"""Route behavior tests for the AgentDesk BFF API."""

from pathlib import Path
from types import SimpleNamespace
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import qwenpaw.constant as qwenpaw_constant
from qwenpaw.config.config import MCPConfig, ToolsConfig
from qwenpaw.agents.skill_system.store import (
    default_pool_manifest,
    read_skill_manifest,
    read_skill_pool_manifest,
)
from qwenpaw.agentdesk.router import api_router, router
from qwenpaw.agentdesk.store import AgentDeskStore


def _skill_md(name: str, description: str = "Demo skill") -> bytes:
    return (
        f"---\nname: {name}\ndescription: {description}\n---\n\n"
        "Use this skill when testing WorkBuddy skill integration.\n"
    ).encode()


def _fake_config(tmp_path):
    default_workspace = tmp_path / "workspaces" / "default"
    analyst_workspace = tmp_path / "workspaces" / "Analyst"
    qa_workspace = tmp_path / "workspaces" / "QwenPaw_QA_Agent_0.2"
    default_workspace.mkdir(parents=True, exist_ok=True)
    analyst_workspace.mkdir(parents=True, exist_ok=True)
    qa_workspace.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        agents=SimpleNamespace(
            active_agent="default",
            language="zh",
            agent_order=["default", "Analyst", "QwenPaw_QA_Agent_0.2"],
            profiles={
                "default": SimpleNamespace(
                    workspace_dir=str(default_workspace),
                    enabled=True,
                ),
                "Analyst": SimpleNamespace(
                    workspace_dir=str(analyst_workspace),
                    enabled=True,
                ),
                "QwenPaw_QA_Agent_0.2": SimpleNamespace(
                    workspace_dir=str(qa_workspace),
                    enabled=True,
                ),
            },
        ),
        tools=ToolsConfig(),
        mcp=MCPConfig(),
    )


def _client(tmp_path, monkeypatch) -> TestClient:
    pool_dir = tmp_path / "skill_pool"
    pool_dir.mkdir(parents=True, exist_ok=True)
    (pool_dir / "skill.json").write_text(
        json.dumps(default_pool_manifest()),
        encoding="utf-8",
    )
    import qwenpaw.agentdesk.agents as agentdesk_agents
    import qwenpaw.agentdesk.agent_profiles as agent_profiles
    import qwenpaw.agentdesk.agent_workspace as agent_workspace
    import qwenpaw.agentdesk.automation as automation
    import qwenpaw.agentdesk.automation_routes as automation_routes
    import qwenpaw.agentdesk.team_leader_agents as team_leader_agents
    import qwenpaw.agentdesk.employee_agents as employee_agents
    import qwenpaw.agentdesk.employee_routes as employee_routes
    import qwenpaw.agentdesk.builtin_agents as builtin_agents
    import qwenpaw.agentdesk.config_routes as config_routes
    import qwenpaw.agentdesk.document_records as document_records
    import qwenpaw.agentdesk.document_routes as document_routes
    import qwenpaw.agentdesk.mcp_config as mcp_config
    import qwenpaw.agentdesk.plaza_routes as plaza_routes
    import qwenpaw.agentdesk.plaza_projection as plaza_projection
    import qwenpaw.agentdesk.record_avatars as record_avatars
    import qwenpaw.agentdesk.session_routing as session_routing
    import qwenpaw.agentdesk.skill_catalog as skill_catalog
    import qwenpaw.agentdesk.skill_management_routes as skill_management_routes
    import qwenpaw.agentdesk.skill_records as skill_records
    import qwenpaw.agentdesk.skill_resolution as skill_resolution
    import qwenpaw.agentdesk.skill_upload_routes as skill_upload_routes
    import qwenpaw.agentdesk.task_cleanup as task_cleanup
    import qwenpaw.agentdesk.task_planning as task_planning
    import qwenpaw.agentdesk.task_records as task_records
    import qwenpaw.agentdesk.task_routes as task_routes
    import qwenpaw.agentdesk.task_transcript_cache as task_transcript_cache
    import qwenpaw.agentdesk.task_workspace_files as task_workspace_files
    import qwenpaw.agentdesk.task_workspace_sync as task_workspace_sync
    import qwenpaw.agentdesk.team_records as team_records
    import qwenpaw.agentdesk.team_routes as team_routes
    import qwenpaw.agentdesk.trace_events as trace_events
    import qwenpaw.config.utils as config_utils

    agentdesk_store = AgentDeskStore(tmp_path / "store.json")
    for module in (
        automation,
        automation_routes,
        builtin_agents,
        config_routes,
        document_records,
        document_routes,
        employee_agents,
        employee_routes,
        plaza_projection,
        plaza_routes,
        record_avatars,
        session_routing,
        skill_catalog,
        skill_management_routes,
        skill_records,
        skill_resolution,
        skill_upload_routes,
        task_cleanup,
        task_planning,
        task_records,
        task_routes,
        task_transcript_cache,
        task_workspace_files,
        task_workspace_sync,
        team_records,
        team_routes,
        trace_events,
    ):
        if hasattr(module, "store"):
            monkeypatch.setattr(module, "store", agentdesk_store)
        if hasattr(module, "agentdesk_store"):
            monkeypatch.setattr(module, "agentdesk_store", agentdesk_store)
    monkeypatch.setattr(qwenpaw_constant, "WORKING_DIR", tmp_path)
    monkeypatch.setattr(task_cleanup, "WORKING_DIR", tmp_path)
    config = _fake_config(tmp_path)

    def load_config():
        return config

    def save_config(updated_config) -> None:
        nonlocal config
        config = updated_config

    for module in (
        agent_workspace,
        config_routes,
        config_utils,
        employee_agents,
        plaza_projection,
        plaza_routes,
        task_cleanup,
        team_leader_agents,
        agentdesk_agents,
    ):
        if hasattr(module, "load_config"):
            monkeypatch.setattr(module, "load_config", load_config)
        if hasattr(module, "save_config"):
            monkeypatch.setattr(module, "save_config", save_config)
    monkeypatch.setattr(team_leader_agents, "WORKING_DIR", str(tmp_path))
    monkeypatch.setattr(
        team_leader_agents,
        "_initialize_agent_workspace",
        lambda workspace_dir, **kwargs: workspace_dir.mkdir(parents=True, exist_ok=True),
    )

    agent_configs: dict[str, SimpleNamespace] = {}

    def fake_load_agent_config(agent_id: str) -> SimpleNamespace:
        if agent_id not in agent_configs:
            agent_configs[agent_id] = SimpleNamespace(
                name=(
                    "QA Agent"
                    if agent_id == "QwenPaw_QA_Agent_0.2"
                    else agent_id
                ),
                description=f"{agent_id} agent",
                skill_names=[],
                mcp=MCPConfig(),
            )
        return agent_configs[agent_id]

    def fake_save_agent_config(agent_id: str, agent_config: SimpleNamespace) -> None:
        agent_configs[agent_id] = agent_config

    if hasattr(config_routes, "load_agent_config"):
        monkeypatch.setattr(config_routes, "load_agent_config", fake_load_agent_config)
    if hasattr(config_routes, "save_agent_config"):
        monkeypatch.setattr(config_routes, "save_agent_config", fake_save_agent_config)
    monkeypatch.setattr(agent_profiles, "load_agent_config", fake_load_agent_config)
    monkeypatch.setattr(mcp_config, "load_agent_config", fake_load_agent_config)
    monkeypatch.setattr(mcp_config, "save_agent_config", fake_save_agent_config)
    monkeypatch.setattr(team_leader_agents, "load_agent_config", fake_load_agent_config)
    monkeypatch.setattr(team_leader_agents, "save_agent_config", fake_save_agent_config)
    monkeypatch.setattr(employee_agents, "WORKING_DIR", str(tmp_path))
    monkeypatch.setattr(employee_agents, "load_agent_config", fake_load_agent_config)
    monkeypatch.setattr(employee_agents, "save_agent_config", fake_save_agent_config)
    monkeypatch.setattr(
        employee_agents,
        "provision_agent_profile",
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
            or SimpleNamespace(
                id=kwargs["requested_id"],
                workspace_dir=str(kwargs["workspace_dir"]),
                enabled=True,
            )
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.mutation_reload.schedule_agent_reload",
        lambda *args, **kwargs: None,
    )
    plaza_routes.invalidate_plaza_orphan_sync()
    app = FastAPI()
    app.include_router(router)
    app.include_router(api_router)
    client = TestClient(app)
    client.agentdesk_store = agentdesk_store  # type: ignore[attr-defined]
    client.agentdesk_config = config  # type: ignore[attr-defined]
    return client


def _register_task_workspace(
    client: TestClient,
    *,
    task_id: str,
    title: str,
    workspace: Path,
    agent_id: str | None = None,
) -> str:
    owner_id = agent_id or f"{task_id}-agent"
    config = client.agentdesk_config  # type: ignore[attr-defined]
    config.agents.profiles[owner_id] = SimpleNamespace(
        workspace_dir=str(workspace),
        enabled=True,
    )
    client.agentdesk_store.upsert_by_key(  # type: ignore[attr-defined]
        "tasks",
        "id",
        task_id,
        {
            "id": task_id,
            "title": title,
            "agent_id": owner_id,
            "workspace_dir": str(workspace),
        },
    )
    return owner_id


def test_plaza_join_creates_employee(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    plaza_response = client.post(
        "/api/plaza",
        json={"name": "Analyst", "desc": "Reads docs", "skills": ["search"]},
    )
    join_response = client.post("/api/plaza/Analyst/join")
    employees_response = client.get("/api/employees")
    plaza_list_response = client.get("/api/plaza")

    assert plaza_response.status_code == 200
    assert join_response.status_code == 200
    join_payload = join_response.json()
    assert join_payload["joined"] is True
    assert "requested_skills" in join_payload
    assert "mounted_skills" in join_payload
    assert "failed_skills" in join_payload
    employees = employees_response.json()
    assert any(
        employee["name"] == "Analyst" and employee["skills"] == ["search"]
        for employee in employees
    )
    assert all(employee["name"] != "default" for employee in employees)
    assert all(employee["name"] != "QA Agent" for employee in employees)
    assert all(employee["id"] != "QwenPaw_QA_Agent_0.2" for employee in employees)
    plaza_names = {item["name"] for item in plaza_list_response.json()}
    assert "default" not in plaza_names
    assert "QA Agent" not in plaza_names


def test_list_plaza_syncs_orphan_employee_agents(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    agent_id = "emp_planner"
    display_name = "规划者"
    workspace = tmp_path / "workspaces" / agent_id
    workspace.mkdir(parents=True, exist_ok=True)

    config = client.agentdesk_config  # type: ignore[attr-defined]
    config.agents.profiles[agent_id] = SimpleNamespace(
        workspace_dir=str(workspace),
        enabled=True,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.agent_profiles.load_agent_config",
        lambda requested_id: SimpleNamespace(
            name=display_name,
            description="负责拆解目标与制定执行计划。",
            skill_names=["make_plan"],
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_agent_config",
        lambda requested_id: SimpleNamespace(
            name=display_name,
            description="负责拆解目标与制定执行计划。",
            skill_names=["make_plan"],
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents._sync_employee_agent",
        lambda *_args, **_kwargs: None,
    )

    client.get("/api/plaza")

    plaza_names: set[str] = set()
    employee = None
    for _ in range(100):
        plaza_list = client.get("/api/plaza").json()
        plaza_names = {item["name"] for item in plaza_list}
        employee = client.agentdesk_store.get_by_key(  # type: ignore[attr-defined]
            "employees",
            "name",
            display_name,
        )
        if display_name in plaza_names and employee is not None:
            break
        time.sleep(0.02)

    assert display_name in plaza_names
    assert employee["agent_id"] == agent_id


def test_list_plaza_backfills_desc_from_agent_profile(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    agent_id = "emp_searcher"
    display_name = "新闻查询专家"
    workspace = tmp_path / "workspaces" / agent_id
    workspace.mkdir(parents=True, exist_ok=True)

    config = client.agentdesk_config  # type: ignore[attr-defined]
    config.agents.profiles[agent_id] = SimpleNamespace(
        workspace_dir=str(workspace),
        enabled=True,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.agent_profiles.load_agent_config",
        lambda requested_id: SimpleNamespace(
            name=display_name,
            description="负责新闻检索、摘要与来源核验。",
            skill_names=["file_reader"],
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.load_agent_config",
        lambda requested_id: SimpleNamespace(
            name=display_name,
            description="负责新闻检索、摘要与来源核验。",
            skill_names=["file_reader"],
        ),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents._sync_employee_agent",
        lambda *_args, **_kwargs: None,
    )

    client.agentdesk_store.upsert_by_key(  # type: ignore[attr-defined]
        "plaza",
        "name",
        display_name,
        {"name": display_name, "desc": "", "skills": ["file_reader"], "joined": True},
    )
    client.agentdesk_store.upsert_by_key(  # type: ignore[attr-defined]
        "employees",
        "name",
        display_name,
        {
            "name": display_name,
            "agent_id": agent_id,
            "desc": "",
            "skills": ["file_reader"],
        },
    )

    card = next(
        item for item in client.get("/api/plaza").json() if item["name"] == display_name
    )
    assert "新闻检索" in card["desc"]


def test_plaza_join_returns_mounted_skills_for_available_pool_skills(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post(
        "/api/skills",
        json={
            "name": "join-mounted-skill",
            "description": "Mounted via join",
            "body": "Use this skill when join should mount it automatically.",
        },
    )
    client.post(
        "/api/plaza",
        json={
            "name": "JoinAnalyst",
            "desc": "Auto mount via join",
            "skills": ["join-mounted-skill"],
        },
    )

    join_response = client.post("/api/plaza/JoinAnalyst/join")

    assert join_response.status_code == 200
    payload = join_response.json()
    assert payload["joined"] is True
    assert payload["requested_skills"] == ["join-mounted-skill"]
    assert set(payload["mounted_skills"] + payload["failed_skills"]) == {
        "join-mounted-skill",
    }


def test_update_employee_mounts_requested_skills(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post(
        "/api/skills",
        json={
            "name": "edit-mounted-skill",
            "description": "Mounted via employee update",
            "body": "Use this skill when editing an employee should mount it.",
        },
    )
    client.post(
        "/api/plaza",
        json={
            "name": "Analyst",
            "desc": "Reads docs",
            "skills": [],
        },
    )
    client.post("/api/plaza/Analyst/join")

    update_response = client.put(
        "/api/employees/Analyst",
        json={
            "desc": "Updated news analyst",
            "skills": ["edit-mounted-skill"],
        },
    )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["desc"] == "Updated news analyst"
    assert payload["requested_skills"] == ["edit-mounted-skill"]
    assert payload["mounted_skills"] == ["edit-mounted-skill"]
    assert payload["failed_skills"] == []
    workspace_dir = Path(_fake_config(tmp_path).agents.profiles["Analyst"].workspace_dir)
    manifest = read_skill_manifest(workspace_dir)
    assert manifest["skills"]["edit-mounted-skill"]["enabled"] is True


def test_update_employee_mounts_workspace_only_skill_from_active_agent(
    tmp_path,
    monkeypatch,
):
    """Skills shown as 已安装 on the active agent but absent from the pool manifest
    should sync into the pool before mounting onto an employee agent."""
    client = _client(tmp_path, monkeypatch)
    config = _fake_config(tmp_path)
    active_workspace = Path(config.agents.profiles["default"].workspace_dir)
    skill_name = "实时查询足球赛程和比分"
    skill_dir = active_workspace / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_bytes(
        _skill_md(skill_name, "Use this skill when the user asks about football."),
    )
    workspace_manifest = read_skill_manifest(active_workspace)
    workspace_manifest.setdefault("skills", {})[skill_name] = {
        "enabled": True,
        "source": "agent",
    }
    (active_workspace / "skill.json").write_text(
        json.dumps(workspace_manifest),
        encoding="utf-8",
    )
    assert skill_name not in (read_skill_pool_manifest().get("skills") or {})

    client.post(
        "/api/plaza",
        json={
            "name": "Analyst",
            "desc": "Sports desk",
            "skills": [],
        },
    )
    client.post("/api/plaza/Analyst/join")

    update_response = client.put(
        "/api/employees/Analyst",
        json={
            "desc": "Sports analyst",
            "skills": [skill_name],
        },
    )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["mounted_skills"] == [skill_name]
    assert payload["failed_skills"] == []
    pool_manifest = read_skill_pool_manifest()
    assert skill_name in pool_manifest.get("skills", {})
    employee_workspace = Path(config.agents.profiles["Analyst"].workspace_dir)
    employee_manifest = read_skill_manifest(employee_workspace)
    assert employee_manifest["skills"][skill_name]["enabled"] is True


def test_conversational_create_exposes_prompt_in_desc_field(tmp_path, monkeypatch):
    """Conversational creation often sends the prompt under ``description`` /
    ``persona`` (native + LLM-chosen field names) instead of the canonical
    ``desc``. The plaza card (what the 编辑员工 modal binds to), the employees
    list and the provisioned agent profile must still expose it via ``desc``.
    """
    client = _client(tmp_path, monkeypatch)

    role_summary = "数据检索机器"
    role_persona = (
        "设定：纯粹的数据检索机器。工具：仅拥有网页搜索和抓取权限。"
        "职责：针对子问题进行地毯式搜索，只提取客观数据与原文链接。"
    )

    # The employee-creator flow lets the model pick the JSON field names; this
    # mirrors the real payload captured in the field (description + persona,
    # no ``desc``).
    create = client.post(
        "/api/plaza",
        json={
            "name": "研究员",
            "description": role_summary,
            "persona": role_persona,
            "skills": [],
        },
    )
    assert create.status_code == 200
    assert role_summary in create.json()["desc"]

    join = client.post("/api/plaza/研究员/join")
    assert join.status_code == 200
    assert role_summary in join.json()["desc"]
    agent_id = join.json().get("agent_id")
    assert agent_id

    # GET /api/plaza is the source the edit modal binds its prompt textarea to.
    plaza = client.get("/api/plaza").json()
    card = next(item for item in plaza if item["name"] == "研究员")
    assert card["desc"].strip()
    assert role_summary in card["desc"]
    assert role_persona in card["desc"]

    # Employees list round-trips the same canonical field.
    employees = client.get("/api/employees").json()
    employee = next(item for item in employees if item["name"] == "研究员")
    assert employee["desc"].strip()
    assert role_summary in employee["desc"]

    # The provisioned agent profile carries the real role, not the generic
    # "AgentDesk 数字员工" fallback used when desc is empty.
    profile = (tmp_path / "workspaces" / agent_id / "PROFILE.md").read_text(
        encoding="utf-8",
    )
    assert role_summary in profile


def test_team_crud_round_trip(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    created = client.post(
        "/api/teams",
        json={
            "id": "team-research",
            "name": "Research",
            "desc": "拆解研究任务并派工。",
            "members": ["Writer", "Analyst"],
        },
    ).json()
    assert created["leader"].endswith("·leader")
    assert created["leader_agent_id"].startswith("lead_")
    assert created["members"] == ["Writer", "Analyst"]
    updated = client.put(
        f"/api/teams/{created['id']}",
        json={"members": ["Writer", "QA"]},
    ).json()
    listed = client.get("/api/teams").json()
    deleted = client.delete(f"/api/teams/{created['id']}").json()

    assert updated["members"] == ["Writer", "QA"]
    assert updated["leader"] == created["leader"]
    assert listed == [updated]
    assert deleted["deleted"] is True
    assert client.get("/api/teams").json() == []


def test_team_create_hides_leader_from_employees(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    created = client.post(
        "/api/teams",
        json={
            "name": "Ops",
            "desc": "协调运维成员。",
            "members": ["Analyst"],
        },
    ).json()
    employees = client.get("/api/employees").json()
    employee_names = {item["name"] for item in employees}
    employee_ids = {item.get("id") or item.get("agent_id") for item in employees}

    assert created["leader"] not in employee_names
    assert created["leader_agent_id"] not in employee_ids


def test_team_normalize_leader_workers_separation(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    created = client.post(
        "/api/teams",
        json={
            "id": "team-dev",
            "name": "Dev Team",
            "desc": "研发协作编排。",
            "members": ["Backend", "Frontend"],
        },
    ).json()
    assert created["leader"].endswith("·leader")
    assert created["members"] == ["Backend", "Frontend"]

    legacy = client.post(
        "/api/teams",
        json={"name": "Legacy", "members": ["Lead", "Worker"]},
    ).json()
    assert legacy["leader"].endswith("·leader")
    assert legacy["members"] == ["Lead", "Worker"]


def test_skills_tools_mcp_have_agentdesk_shapes(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    skills = client.get("/api/skills")
    tools = client.get("/api/tools")
    mcp = client.get("/api/mcp")

    assert skills.status_code == 200
    assert tools.status_code == 200
    assert mcp.status_code == 200
    assert isinstance(skills.json(), list)
    assert all("name" in item for item in skills.json())
    assert all("key" in item and "label" in item for item in tools.json())
    assert all("name" in item and "transport" in item for item in mcp.json())


def test_mcp_compat_write_endpoints_are_available(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    created = client.post(
        "/api/mcp",
        json={
            "name": "demo-mcp",
            "transport": "stdio",
            "command": "echo",
        },
    )
    deleted = client.delete("/api/mcp/demo-mcp")

    assert created.status_code == 200
    assert created.json()["name"] == "demo-mcp"
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


def test_skill_create_and_upload_round_trip_in_list(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    created = client.post(
        "/api/skills",
        json={
            "name": "demo-skill",
            "description": "Demo skill",
            "body": "Use this skill when testing skill creation.",
        },
    )
    uploaded = client.post(
        "/api/skills/upload",
        files=[("files", ("SKILL.md", _skill_md("folder")))],
        data={"relative_paths": '["folder/SKILL.md"]'},
    )
    listed = client.get("/api/skills").json()

    assert created.status_code == 200
    assert uploaded.status_code == 200
    assert uploaded.json()["uploaded"] == 1
    names = {item["name"] for item in listed}
    assert {"demo-skill", "folder"} <= names
    demo = next(item for item in listed if item["name"] == "demo-skill")
    assert demo["description"] == "Demo skill"
    assert "Use this skill" in demo["body"]
    stored = client.agentdesk_store.list_items("skills")  # type: ignore[attr-defined]
    assert any(item["name"] == "demo-skill" for item in stored)


def test_skill_files_tree_and_content(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    uploaded = client.post(
        "/api/skills/upload",
        files=[
            ("files", ("SKILL.md", _skill_md("detail-skill"))),
            ("files", ("guide.md", b"# Guide\n\nExtra reference.\n")),
        ],
        data={
            "relative_paths": '["detail-skill/SKILL.md", "detail-skill/references/guide.md"]',
            "auto_install_safe": "true",
        },
    )
    assert uploaded.status_code == 200

    tree = client.get("/api/skills/detail-skill/files")
    assert tree.status_code == 200
    payload = tree.json()
    assert payload["skill_name"] == "detail-skill"
    assert payload["location"] == "workspace"
    top_names = {entry["name"] for entry in payload["entries"]}
    assert {"SKILL.md", "references"} <= top_names
    refs = next(entry for entry in payload["entries"] if entry["name"] == "references")
    assert refs["type"] == "directory"
    assert any(child["name"] == "guide.md" for child in refs["children"])

    skill_md = client.get("/api/skills/detail-skill/files/SKILL.md")
    assert skill_md.status_code == 200
    md_payload = skill_md.json()
    assert md_payload["is_markdown"] is True
    assert "detail-skill" in md_payload["content"]

    guide = client.get("/api/skills/detail-skill/files/references/guide.md")
    assert guide.status_code == 200
    assert "Guide" in guide.json()["content"]

    rejected = client.get("/api/skills/detail-skill/files/../SKILL.md")
    assert rejected.status_code in {400, 404}

    missing = client.get("/api/skills/missing-skill/files")
    assert missing.status_code == 404


def test_skill_files_resolve_on_employee_workspace(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    config = _fake_config(tmp_path)
    employee_workspace = Path(config.agents.profiles["Analyst"].workspace_dir)
    skill_name = "资讯分析"
    skill_dir = employee_workspace / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_bytes(_skill_md(skill_name, "资讯分析技能"))

    tree = client.get(f"/api/skills/{skill_name}/files")
    assert tree.status_code == 200
    assert tree.json()["location"] == "workspace"
    assert any(entry["name"] == "SKILL.md" for entry in tree.json()["entries"])


def test_task_workspace_file_preview_maps_legacy_skill_path(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace"
    skill_dir = workspace / "skills" / "资讯分析"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# 资讯分析\n", encoding="utf-8")
    agent_id = "workspace-preview-agent"
    config = client.agentdesk_config  # type: ignore[attr-defined]
    config.agents.profiles[agent_id] = SimpleNamespace(
        workspace_dir=str(workspace),
        enabled=True,
    )

    client.agentdesk_store.upsert_by_key(  # type: ignore[attr-defined]
        "tasks",
        "id",
        "task-1",
        {
            "id": "task-1",
            "title": "Demo",
            "agent_id": agent_id,
            "workspace_dir": str(workspace),
        },
    )
    preview = client.get(
        "/api/tasks/task-1/workspace/file",
        params={"path": "backend/data/skills/资讯分析/SKILL.md"},
    )

    assert preview.status_code == 200
    assert "资讯分析" in preview.json()["content"]


def test_skill_zip_upload_imports_into_pool(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("zip-skill/SKILL.md", _skill_md("zip-skill"))

    response = client.post(
        "/api/skills/upload",
        files=[("file", ("skills.zip", buf.getvalue(), "application/zip"))],
    )
    listed = client.get("/api/skills").json()

    assert response.status_code == 200
    assert response.json()["uploaded"] == 1
    assert any(item["name"] == "zip-skill" for item in listed)


def test_skill_upload_auto_install_marks_installed(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/skills/upload",
        files=[("files", ("SKILL.md", _skill_md("auto-mount")))],
        data={
            "relative_paths": '["auto-mount/SKILL.md"]',
            "auto_install_safe": "true",
        },
    )
    listed = client.get("/api/skills").json()

    assert response.status_code == 200
    assert response.json()["uploaded"] == 1
    assert response.json()["mounted"] is True
    skill = next(item for item in listed if item["name"] == "auto-mount")
    assert skill["installed"] is True
    assert skill["enabled"] is True


def test_skill_upload_without_auto_install_stays_pool_only(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/skills/upload",
        files=[("files", ("SKILL.md", _skill_md("pool-only")))],
        data={
            "relative_paths": '["pool-only/SKILL.md"]',
            "auto_install_safe": "false",
        },
    )
    listed = client.get("/api/skills").json()

    assert response.status_code == 200
    assert response.json()["uploaded"] == 1
    assert response.json()["mounted"] is False
    skill = next(item for item in listed if item["name"] == "pool-only")
    assert skill["installed"] is False
    assert skill["enabled"] is False


def test_skill_mount_installs_and_enables_pool_skill_for_employee(
    tmp_path,
    monkeypatch,
):
    client = _client(tmp_path, monkeypatch)
    client.post(
        "/api/skills",
        json={
            "name": "mounted-skill",
            "description": "Mount me",
            "body": "Use this skill when mounting to an employee.",
        },
    )

    response = client.post(
        "/api/skills/mounted-skill/mount",
        json={"employee_name": "Analyst", "scope": "agent"},
    )
    workspace_dir = Path(_fake_config(tmp_path).agents.profiles["Analyst"].workspace_dir)
    manifest = read_skill_manifest(workspace_dir)

    assert response.status_code == 200
    assert response.json()["mounted"] is True
    assert response.json()["agent_id"] == "Analyst"
    assert (workspace_dir / "skills" / "mounted-skill" / "SKILL.md").is_file()
    assert manifest["skills"]["mounted-skill"]["enabled"] is True


def test_skill_mount_returns_404_for_unknown_pool_skill(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/skills/missing-skill/mount",
        json={"employee_name": "Analyst"},
    )

    assert response.status_code == 404


def test_skill_mount_is_idempotent_for_workspace_only_skill(tmp_path, monkeypatch):
    from qwenpaw.agents.skill_system import SkillService
    from qwenpaw.agents.skill_system.store import render_skill_md

    client = _client(tmp_path, monkeypatch)
    analyst_workspace = Path(_fake_config(tmp_path).agents.profiles["Analyst"].workspace_dir)
    SkillService(analyst_workspace).create_skill(
        name="ws-only-mounted",
        content=render_skill_md(
            proposed_name="ws-only-mounted",
            description="Workspace-only mounted skill",
            body="Use this skill when testing idempotent mount behavior.",
        ),
        enable=True,
    )

    response = client.post(
        "/api/skills/ws-only-mounted/mount",
        json={"employee_name": "Analyst"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mounted"] is True
    assert payload["already_mounted"] is True
    assert payload["skill_name"] == "ws-only-mounted"
    assert payload["agent_id"] == "Analyst"


def test_list_skills_includes_workspace_only_mounted_skills(tmp_path, monkeypatch):
    from qwenpaw.agents.skill_system import SkillService
    from qwenpaw.agents.skill_system.store import render_skill_md

    client = _client(tmp_path, monkeypatch)
    workspace_dir = Path(_fake_config(tmp_path).agents.profiles["default"].workspace_dir)
    SkillService(workspace_dir).create_skill(
        name="ws-only-skill",
        content=render_skill_md(
            proposed_name="ws-only-skill",
            description="Workspace-only skill for list API",
            body="Use this skill when testing workspace-only skill listing.",
        ),
        enable=True,
    )

    listed = client.get("/api/skills").json()
    match = next((item for item in listed if item["name"] == "ws-only-skill"), None)

    assert match is not None
    assert match["installed"] is True
    assert match["enabled"] is True
    assert match["source"] == "workspace"


def test_skill_mount_imports_packaged_employee_creator(tmp_path, monkeypatch):
    from qwenpaw.agents.skill_system.registry import get_packaged_builtin_versions

    if "employee-creator" not in get_packaged_builtin_versions():
        pytest.skip("employee-creator builtin not packaged in this environment")

    client = _client(tmp_path, monkeypatch)
    response = client.post(
        "/api/skills/employee-creator/mount",
        json={"employee_name": "Analyst", "scope": "agent"},
    )

    assert response.status_code == 200
    assert response.json()["mounted"] is True
    workspace_dir = Path(_fake_config(tmp_path).agents.profiles["Analyst"].workspace_dir)
    manifest = read_skill_manifest(workspace_dir)
    assert manifest["skills"]["employee-creator"]["enabled"] is True


def test_skill_upload_rejects_absolute_relative_path(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/skills/upload",
        files=[("files", ("SKILL.md", b"---\nname: bad\n---\n"))],
        data={"relative_paths": '["/tmp/escape/SKILL.md"]'},
    )

    assert response.status_code == 400


def test_skill_upload_rejects_parent_relative_path(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/skills/upload",
        files=[("files", ("SKILL.md", b"---\nname: bad\n---\n"))],
        data={"relative_paths": '["../escape/SKILL.md"]'},
    )

    assert response.status_code == 400


def test_skill_upload_recovers_existing_pool_skill_on_conflict(
    tmp_path,
    monkeypatch,
):
    client = _client(tmp_path, monkeypatch)

    first = client.post(
        "/api/skills/upload",
        files=[("files", ("SKILL.md", _skill_md("pool-recover")))],
        data={
            "relative_paths": '["pool-recover/SKILL.md"]',
            "auto_install_safe": "false",
        },
    )
    assert first.status_code == 200
    assert first.json()["uploaded"] == 1
    assert first.json()["mounted"] is False

    second = client.post(
        "/api/skills/upload",
        files=[("files", ("SKILL.md", _skill_md("pool-recover")))],
        data={
            "relative_paths": '["pool-recover/SKILL.md"]',
            "auto_install_safe": "true",
        },
    )
    listed = client.get("/api/skills").json()

    assert second.status_code == 200
    payload = second.json()
    assert payload["uploaded"] == 0
    assert payload["recovered"] == ["pool-recover"]
    assert payload["mounted"] is True
    skill = next(item for item in listed if item["name"] == "pool-recover")
    assert skill["installed"] is True
    assert skill["enabled"] is True


def test_skill_upload_conflict_without_auto_install_returns_409(
    tmp_path,
    monkeypatch,
):
    client = _client(tmp_path, monkeypatch)

    client.post(
        "/api/skills/upload",
        files=[("files", ("SKILL.md", _skill_md("pool-conflict")))],
        data={
            "relative_paths": '["pool-conflict/SKILL.md"]',
            "auto_install_safe": "false",
        },
    )

    response = client.post(
        "/api/skills/upload",
        files=[("files", ("SKILL.md", _skill_md("pool-conflict")))],
        data={
            "relative_paths": '["pool-conflict/SKILL.md"]',
            "auto_install_safe": "false",
        },
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["conflicts"][0]["skill_name"] == "pool-conflict"
    assert detail["conflicts"][0]["suggested_name"]


def test_mcp_create_round_trips_in_list(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    client.post(
        "/api/mcp",
        json={
            "name": "demo-mcp",
            "transport": "stdio",
            "command": "echo",
        },
    )

    listed = client.get("/api/mcp").json()

    assert any(item["name"] == "demo-mcp" for item in listed)


def test_mcp_presets_list_includes_builtin_catalog(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/mcp/presets")

    assert response.status_code == 200
    presets = response.json()
    preset_ids = {item["id"] for item in presets}
    assert preset_ids >= {
        "tavily_search",
        "fetch",
        "memory",
        "sequential-thinking",
        "filesystem",
    }
    assert all("installed" in item for item in presets)


def test_mcp_preset_install_persists_to_agent_config(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    saved: list[tuple[str, SimpleNamespace]] = []

    def capture_save(agent_id: str, agent_config: SimpleNamespace) -> None:
        saved.append((agent_id, agent_config))

    monkeypatch.setattr(
        "qwenpaw.agentdesk.mcp_config.save_agent_config",
        capture_save,
    )

    install = client.post("/api/mcp/presets/fetch/install")
    listed = client.get("/api/mcp").json()
    presets = client.get("/api/mcp/presets").json()

    assert install.status_code == 200
    assert install.json()["key"] == "fetch"
    assert install.json()["command"] == "npx"
    assert any(item["key"] == "fetch" for item in listed)
    assert next(item for item in presets if item["id"] == "fetch")["installed"] is True
    assert saved
    assert saved[-1][0] == "default"
    assert "fetch" in saved[-1][1].mcp.clients


def test_mcp_preset_install_unknown_returns_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post("/api/mcp/presets/not-a-preset/install")

    assert response.status_code == 404


def test_list_tasks_returns_newest_first(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    first = client.post("/api/tasks", json={"id": "task-old", "title": "Old"}).json()
    second = client.post("/api/tasks", json={"id": "task-new", "title": "New"}).json()

    listed = client.get("/api/tasks").json()

    assert [task["id"] for task in listed[:2]] == ["task-new", "task-old"]
    assert second["createdAt"] >= first["createdAt"]


def test_update_task_pinned_persists(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    client.post("/api/tasks", json={"id": "task-pin", "title": "Pin me"})

    pin_response = client.patch("/api/tasks/task-pin", json={"pinned": True})
    assert pin_response.status_code == 200
    assert pin_response.json()["pinned"] is True

    listed = client.get("/api/tasks").json()
    pinned_task = next(task for task in listed if task["id"] == "task-pin")
    assert pinned_task["pinned"] is True

    unpin_response = client.patch("/api/tasks/task-pin", json={"pinned": False})
    assert unpin_response.status_code == 200
    assert unpin_response.json()["pinned"] is False

    got = client.get("/api/tasks/task-pin").json()
    assert got.get("pinned") is False


def test_update_task_not_found(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.patch("/api/tasks/missing-task", json={"pinned": True})

    assert response.status_code == 404


def test_delete_task_cleans_store_session_and_workspace(tmp_path, monkeypatch):
    from qwenpaw.app.runner.session import sanitize_filename

    client = _client(tmp_path, monkeypatch)
    task_id = "task-delete-me"
    workspace = tmp_path / "agentdesk" / "task-workspaces" / task_id
    workspace.mkdir(parents=True)
    (workspace / "artifact.txt").write_text("data", encoding="utf-8")

    sessions_dir = workspace / "sessions" / "console"
    sessions_dir.mkdir(parents=True)
    session_name = f"{sanitize_filename('agentdesk')}_{sanitize_filename(task_id)}.json"
    session_path = sessions_dir / session_name
    session_path.write_text("{}", encoding="utf-8")

    _register_task_workspace(
        client,
        task_id=task_id,
        title="Delete me",
        workspace=workspace,
    )

    delete_response = client.delete(f"/api/tasks/{task_id}")
    assert delete_response.status_code == 200
    payload = delete_response.json()
    assert payload["deleted"] is True
    assert payload["id"] == task_id
    assert payload["aborted"] is False
    assert str(session_path) in payload["files_removed"]
    assert str(workspace.resolve()) in payload["files_removed"]

    listed = client.get("/api/tasks").json()
    assert all(task["id"] != task_id for task in listed)
    assert not session_path.exists()
    assert not workspace.exists()


def test_task_workspace_file_tree_and_file_preview(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("# Demo\nHello", encoding="utf-8")

    _register_task_workspace(
        client,
        task_id="task-1",
        title="Demo",
        workspace=workspace,
    )
    tree = client.get("/api/tasks/task-1/workspace/tree")
    preview = client.get(
        "/api/tasks/task-1/workspace/file",
        params={"path": "README.md"},
    )

    assert tree.json()["files"] == [{"path": "README.md"}]
    assert preview.json()["content"] == "# Demo\nHello"
    assert preview.json()["binary"] is False


def test_task_workspace_reveal_accepts_plain_relative_path(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("# Demo\nHello", encoding="utf-8")

    _register_task_workspace(
        client,
        task_id="task-1",
        title="Demo",
        workspace=workspace,
    )

    revealed: list[str] = []

    def fake_reveal(path):
        revealed.append(str(path))

    monkeypatch.setattr(
        "qwenpaw.agentdesk.task_workspace_routes.reveal_path_in_os",
        fake_reveal,
    )

    response = client.post(
        "/api/tasks/task-1/workspace/reveal",
        json={"path": "README.md"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert revealed == [str((workspace / "README.md").resolve())]


def test_task_workspace_reveal_accepts_msys_absolute_path(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "note.md"
    target.write_text("hello", encoding="utf-8")

    _register_task_workspace(
        client,
        task_id="task-1",
        title="Demo",
        workspace=workspace,
    )

    revealed: list[str] = []

    def fake_reveal(path):
        revealed.append(str(path))

    monkeypatch.setattr(
        "qwenpaw.agentdesk.task_workspace_routes.reveal_path_in_os",
        fake_reveal,
    )

    drive = str(workspace.drive).replace(":", "").lower()
    msys_path = f"/{drive}{workspace.as_posix()[2:]}/note.md"
    response = client.post(
        "/api/tasks/task-1/workspace/reveal",
        json={"path": msys_path},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert revealed == [str(target.resolve())]


def test_context_budget_estimate_returns_segments(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/tasks/task-1/context/budget",
        json={"message": "hello world", "skill_names": ["search"]},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["used_tokens"] > 0
    assert payload["context_limit"] > 0
    assert {segment["key"] for segment in payload["segments"]} >= {
        "message",
        "skills",
        "base",
    }


def test_knowledge_and_cases_crud_round_trip(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    knowledge = client.post(
        "/api/knowledge",
        json={"id": "k1", "title": "Handbook", "content": "Read me"},
    ).json()
    case = client.post(
        "/api/cases",
        json={"id": "c1", "title": "Launch", "content": "Ship it"},
    ).json()
    updated = client.put("/api/knowledge/k1", json={"content": "Updated"}).json()

    assert knowledge["title"] == "Handbook"
    assert case["title"] == "Launch"
    assert updated["content"] == "Updated"
    assert client.get("/api/knowledge").json() == [updated]
    assert client.delete("/api/cases/c1").json()["deleted"] is True
    assert client.get("/api/cases").json() == []


def test_automation_job_lifecycle_and_history(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    job = client.post(
        "/api/automation/jobs",
        json={
            "id": "job-1",
            "name": "Daily check",
            "workspace": "default",
            "prompt": "Check status",
            "schedule": {"cron": "0 9 * * *", "mode": "periodic"},
        },
    ).json()
    paused = client.post("/api/automation/jobs/job-1/pause").json()
    resumed = client.post("/api/automation/jobs/job-1/resume").json()
    run = client.post("/api/automation/jobs/job-1/run").json()
    history = client.get("/api/automation/history").json()

    assert job["enabled"] is True
    assert job["task_id"]
    assert job["frequency"] == "每天 09:00"
    assert paused["enabled"] is False
    assert resumed["enabled"] is True
    assert run["status"] in {"queued", "running"}
    assert history[0]["job_id"] == "job-1"
    assert client.delete("/api/automation/jobs/job-1").json()["deleted"] is True


def test_list_employees_deduplicates_linked_store_rows(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    agent_id = "emp_sentiment01"
    workspace = tmp_path / "workspaces" / agent_id
    workspace.mkdir(parents=True, exist_ok=True)

    config = client.agentdesk_config  # type: ignore[attr-defined]
    config.agents.profiles[agent_id] = SimpleNamespace(
        workspace_dir=str(workspace),
        enabled=True,
    )
    client.agentdesk_store.upsert_by_key(  # type: ignore[attr-defined]
        "employees",
        "name",
        "舆情分析师",
        {
            "name": "舆情分析师",
            "agent_id": agent_id,
            "desc": "store copy",
            "skills": [],
            "tools": [],
            "mcp": [],
        },
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.agent_profiles.load_agent_config",
        lambda requested_id: SimpleNamespace(
            name="舆情分析师" if requested_id == agent_id else requested_id,
            description="profile copy",
            skill_names=[],
        ),
    )

    employees = client.get("/api/employees").json()
    sentiment_rows = [item for item in employees if item["name"] == "舆情分析师"]

    assert len(sentiment_rows) == 1
    assert sentiment_rows[0]["agent_id"] == agent_id


def test_delete_employee_removes_from_list(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    agent_id = "emp_delete_me01"
    workspace = tmp_path / "workspaces" / agent_id
    workspace.mkdir(parents=True, exist_ok=True)

    config = client.agentdesk_config  # type: ignore[attr-defined]
    config.agents.profiles[agent_id] = SimpleNamespace(
        workspace_dir=str(workspace),
        enabled=True,
    )
    client.agentdesk_store.upsert_by_key(  # type: ignore[attr-defined]
        "employees",
        "name",
        "Readme编写大师",
        {
            "name": "Readme编写大师",
            "agent_id": agent_id,
            "desc": "writes readme",
            "skills": [],
            "tools": [],
            "mcp": [],
        },
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.agent_profiles.load_agent_config",
        lambda requested_id: SimpleNamespace(
            name="Readme编写大师" if requested_id == agent_id else requested_id,
            description="profile copy",
            skill_names=[],
        ),
    )

    before = client.get("/api/employees").json()
    assert any(item["name"] == "Readme编写大师" for item in before)

    deleted = client.delete("/api/employees/Readme编写大师").json()
    assert deleted["deleted"] is True

    after = client.get("/api/employees").json()
    assert not any(item["name"] == "Readme编写大师" for item in after)
    assert agent_id not in client.agentdesk_config.agents.profiles  # type: ignore[attr-defined]


def test_delete_plaza_removes_card_after_reload(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    agent_id = "emp_plaza_del01"
    workspace = tmp_path / "workspaces" / agent_id
    workspace.mkdir(parents=True, exist_ok=True)

    config = client.agentdesk_config  # type: ignore[attr-defined]
    config.agents.profiles[agent_id] = SimpleNamespace(
        workspace_dir=str(workspace),
        enabled=True,
    )
    client.agentdesk_store.upsert_by_key(  # type: ignore[attr-defined]
        "plaza",
        "name",
        "测试岗位",
        {
            "name": "测试岗位",
            "desc": "for delete test",
            "tags": ["AgentDesk"],
            "skills": [],
            "joined": True,
        },
    )
    client.agentdesk_store.upsert_by_key(  # type: ignore[attr-defined]
        "employees",
        "name",
        "测试岗位",
        {
            "name": "测试岗位",
            "agent_id": agent_id,
            "desc": "for delete test",
            "skills": [],
            "tools": [],
            "mcp": [],
        },
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.agent_profiles.load_agent_config",
        lambda requested_id: SimpleNamespace(
            name="测试岗位" if requested_id == agent_id else requested_id,
            description="profile copy",
            skill_names=[],
        ),
    )

    before = client.get("/api/plaza").json()
    assert any(item["name"] == "测试岗位" for item in before)

    deleted = client.delete("/api/plaza/测试岗位").json()
    assert deleted["deleted"] is True

    after = client.get("/api/plaza").json()
    assert not any(item["name"] == "测试岗位" for item in after)
    assert agent_id not in client.agentdesk_config.agents.profiles  # type: ignore[attr-defined]


def test_task_workspace_searches_team_member_workspaces(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    leader_ws = tmp_path / "leader"
    worker_ws = tmp_path / "worker"
    leader_ws.mkdir()
    worker_ws.mkdir()
    report = worker_ws / "AI_Trend_Report_2026H1.md"
    report.write_text("# Trends", encoding="utf-8")

    client.agentdesk_store.upsert_by_key(  # type: ignore[attr-defined]
        "teams",
        "id",
        "team-research",
        {
            "id": "team-research",
            "name": "深度调研团队",
            "members": ["研究员"],
            "leader_agent_id": "lead_research01",
        },
    )
    client.agentdesk_store.upsert_by_key(  # type: ignore[attr-defined]
        "employees",
        "name",
        "研究员",
        {
            "name": "研究员",
            "agent_id": "emp_searcher01",
            "desc": "research",
            "skills": [],
            "tools": [],
            "mcp": [],
        },
    )

    config = client.agentdesk_config  # type: ignore[attr-defined]
    config.agents.profiles["lead_research01"] = SimpleNamespace(
        workspace_dir=str(leader_ws),
        enabled=True,
    )
    config.agents.profiles["emp_searcher01"] = SimpleNamespace(
        workspace_dir=str(worker_ws),
        enabled=True,
    )

    client.post(
        "/api/tasks",
        json={
            "id": "task-team-1",
            "title": "调研",
            "workspace_dir": str(leader_ws),
        },
    )
    task = (
        client.agentdesk_store.get_by_key("tasks", "id", "task-team-1") or {}  # type: ignore[attr-defined]
    )
    client.agentdesk_store.upsert_by_key(  # type: ignore[attr-defined]
        "tasks",
        "id",
        "task-team-1",
        {**task, "team_id": "team-research"},
    )

    tree = client.get("/api/tasks/task-team-1/workspace/tree").json()
    assert any(item["path"].endswith("AI_Trend_Report_2026H1.md") for item in tree["files"])

    preview = client.get(
        "/api/tasks/task-team-1/workspace/file",
        params={"path": "AI_Trend_Report_2026H1.md"},
    )
    assert preview.json()["content"] == "# Trends"


def test_list_plaza_and_employees_do_not_provision_agents(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.agentdesk_store.upsert_by_key(  # type: ignore[attr-defined]
        "plaza",
        "name",
        "快速测试员",
        {
            "name": "快速测试员",
            "desc": "只做列表读取，不应触发 agent 同步。",
            "tags": ["AgentDesk"],
            "skills": ["search"],
        },
    )

    def fail_ensure(*_args, **_kwargs):
        raise AssertionError("ensure_employee_agent_profile must not run on list reads")

    monkeypatch.setattr(
        "qwenpaw.agentdesk.employee_agents.ensure_employee_agent_profile",
        fail_ensure,
    )

    plaza = client.get("/api/plaza").json()
    employees = client.get("/api/employees").json()

    assert any(item["name"] == "快速测试员" for item in plaza)
    assert isinstance(employees, list)
