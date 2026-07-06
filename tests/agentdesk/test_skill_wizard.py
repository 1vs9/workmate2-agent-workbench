# -*- coding: utf-8 -*-
"""Tests for AgentDesk one-sentence skill wizard orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import qwenpaw.constant as qwenpaw_constant
import qwenpaw.agentdesk.chat as agentdesk_chat
import qwenpaw.agentdesk.chat_message_composer as chat_message_composer
from qwenpaw.agents.skill_system.store import default_pool_manifest, render_skill_md
from qwenpaw.app.runner.task_tracker import TaskTracker
from qwenpaw.agentdesk.chat import router as chat_router
from qwenpaw.agentdesk.router import api_router, router
from qwenpaw.agentdesk.locale import detect_user_language
from qwenpaw.agentdesk.skill_wizard import (
    build_skill_create_agent_message,
    build_skill_find_agent_message,
    extract_skill_purpose,
    is_skill_create_message,
    is_skill_find_message,
    is_substantive_skill_content,
    parse_materialize_skill_success,
    propose_skill_name,
)
from qwenpaw.agentdesk.store import AgentDeskStore


def _substantive_body(topic: str) -> str:
    return (
        f"# {topic}\n\n"
        f"Use this skill when the user asks for {topic}.\n\n"
        "## Workflow\n\n"
        f"1. Gather market context and user constraints for {topic}.\n"
        "2. Pull relevant data via search and structured APIs.\n"
        "3. Summarize risks, catalysts, and actionable takeaways.\n"
        "4. Present findings with sources and confidence notes.\n\n"
        "## Output\n\n"
        "- Executive summary with key metrics.\n"
        "- Bull/bear scenarios and watchlist items.\n"
    )


def _skill_pool_setup(tmp_path, monkeypatch):
    pool_dir = tmp_path / "skill_pool"
    pool_dir.mkdir(parents=True, exist_ok=True)
    (pool_dir / "skill.json").write_text(
        json.dumps(default_pool_manifest()),
        encoding="utf-8",
    )
    agentdesk_store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(qwenpaw_constant, "WORKING_DIR", tmp_path)
    monkeypatch.setattr(
        agentdesk_chat,
        "agentdesk_store",
        agentdesk_store,
    )
    monkeypatch.setattr("qwenpaw.agentdesk.task_routes.store", agentdesk_store)
    monkeypatch.setattr("qwenpaw.agentdesk.task_records.store", agentdesk_store)
    monkeypatch.setattr("qwenpaw.agentdesk.task_planning.store", agentdesk_store)
    import qwenpaw.agentdesk.skill_wizard as skill_wizard_module

    monkeypatch.setattr(skill_wizard_module, "agentdesk_store", agentdesk_store)
    config = SimpleNamespace(
        agents=SimpleNamespace(
            active_agent="default",
            profiles={
                "default": SimpleNamespace(
                    workspace_dir=str(tmp_path / "workspaces" / "default"),
                    enabled=True,
                ),
            },
        ),
        tools=SimpleNamespace(builtin_tools={}),
        mcp=SimpleNamespace(clients={}),
    )
    (tmp_path / "workspaces" / "default").mkdir(parents=True, exist_ok=True)
    import qwenpaw.config.utils as config_utils

    monkeypatch.setattr(config_utils, "load_config", lambda: config)
    monkeypatch.setattr("qwenpaw.agentdesk.agent_workspace.load_config", lambda: config)
    monkeypatch.setattr("qwenpaw.agentdesk.agents.load_config", lambda: config)
    monkeypatch.setattr(agentdesk_chat, "schedule_agent_reload", lambda request, agent_id: None)
    return config


def _write_workspace_skill(tmp_path: Path, skill_name: str, body: str) -> None:
    content = render_skill_md(
        proposed_name=skill_name,
        description=f"Skill for {skill_name}",
        body=body,
    )
    skill_dir = tmp_path / "workspaces" / "default" / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def _materialize_sse_events(skill_name: str) -> list[str]:
    call_evt = {
        "object": "message",
        "type": "plugin_call",
        "status": "completed",
        "content": [
            {
                "type": "data",
                "data": {
                    "name": "materialize_skill",
                    "call_id": "call-1",
                    "arguments": {
                        "name": skill_name,
                        "description": f"Use this skill when the user asks for {skill_name}.",
                        "body": "example",
                    },
                },
            },
        ],
    }
    output_evt = {
        "object": "message",
        "type": "plugin_call_output",
        "status": "completed",
        "content": [
            {
                "type": "data",
                "data": {
                    "name": "materialize_skill",
                    "call_id": "call-1",
                    "output": (
                        f"**Skill created and enabled**: `{skill_name}`\n\n"
                        "Visible via `/skills`; invoke with "
                        f"`/{skill_name}`."
                    ),
                    "state": "success",
                },
            },
        ],
    }
    return [
        f"data: {json.dumps(call_evt, ensure_ascii=False)}\n\n",
        f"data: {json.dumps(output_evt, ensure_ascii=False)}\n\n",
    ]


class _FakeChatManager:
    async def get_or_create_chat(self, session_id, sender_id, channel_id, name=None):
        return SimpleNamespace(id=session_id)


class _FakeConsoleChannel:
    def __init__(self, events: list[str]):
        self._events = events

    def resolve_session_id(self, sender_id, channel_meta=None):
        return str(channel_meta.get("session_id") or "chat-1")

    async def stream_one(self, payload):
        for event in self._events:
            yield event


class _FakeChannelManager:
    def __init__(self, events: list[str]):
        self._events = events

    async def get_channel(self, channel_id):
        return _FakeConsoleChannel(self._events)


class _FakeWorkspace:
    def __init__(self, tmp_path: Path, events: list[str]):
        self.workspace_dir = str(tmp_path / "workspaces" / "default")
        self.task_tracker = TaskTracker()
        self.channel_manager = _FakeChannelManager(events)
        self.chat_manager = _FakeChatManager()


def test_extract_skill_purpose_from_quotes():
    assert extract_skill_purpose("请帮我创建一个可以实现「整理会议纪要」的skill") == "整理会议纪要"


def test_propose_skill_name_supports_chinese_purpose():
    assert propose_skill_name("资讯分析") == "资讯分析"


def test_propose_skill_name_avoids_collision():
    assert propose_skill_name("demo", existing={"demo"}) == "demo-2"


def test_detect_user_language_prefers_chinese_for_cjk_text():
    assert detect_user_language("请帮我创建一个 skill") == "zh"
    assert detect_user_language("Create a stock analysis skill") == "en"


def test_build_skill_create_agent_message_includes_focus():
    message = build_skill_create_agent_message("请帮我创建一个可以实现「股市分析」的 skill")
    assert "股市分析" in message
    assert "materialize_skill" in message
    assert "快速创建" in message
    assert "FAQ/问答" in message
    assert "Skip `create_plan`" not in message


def test_is_skill_find_message_detects_find_draft():
    assert is_skill_find_message("请帮我查找并自动安装能「……」的skill")
    assert is_skill_find_message("请帮我查找并自动安装能「创建readme」的skill")
    assert not is_skill_find_message("请帮我创建一个可以实现「创建readme」的skill")


def test_is_skill_create_message_detects_explicit_create_only():
    assert is_skill_create_message("请帮我创建一个可以实现「股市分析」的skill")
    assert not is_skill_create_message("把上述功能总结成一段描述")
    assert not is_skill_create_message(
        "功能列表：\n1. 单任务自主规划\n2. 支持创建自定义skill\n3. 多轮对话",
    )
    assert not is_skill_create_message("请帮我查找并自动安装能「创建readme」的skill")


def test_build_skill_find_agent_message_avoids_materialize():
    message = build_skill_find_agent_message("请帮我查找并自动安装能「创建readme」的skill")
    assert "创建readme" in message
    assert "不要调用 `materialize_skill`" in message
    assert "market/search" in message


def test_resolve_chat_user_messages_routes_find_to_lookup_prompt(tmp_path):
    display, agent = chat_message_composer.resolve_chat_user_messages(
        tmp_path,
        "请帮我查找并自动安装能「创建readme」的skill",
        [],
    )
    assert display == "请帮我查找并自动安装能「创建readme」的skill"
    assert "技能查找" in agent
    assert "materialize_skill" in agent
    assert "不要调用" in agent


def test_resolve_chat_user_messages_routes_employee_creator_to_quick_create(tmp_path):
    display, agent = chat_message_composer.resolve_chat_user_messages(
        tmp_path,
        "帮我创建一个代码质量守护者，擅长代码审查。",
        ["employee-creator"],
    )
    assert display.startswith("帮我创建一个代码质量守护者")
    assert "AgentDesk 快速创建员工" in agent
    assert "BOOTSTRAP" in agent
    assert "POST /api/plaza" in agent


def test_parse_materialize_skill_success():
    detail = "**Skill created and enabled**: `stock-analysis`\n\nVisible via `/skills`"
    assert parse_materialize_skill_success(detail) == "stock-analysis"


def test_is_substantive_skill_content_rejects_stub():
    stub = render_skill_md(
        proposed_name="demo",
        description="demo",
        body=(
            "# demo\n\nUse this skill when the user asks for this capability.\n\n"
            "## Workflow\n\n"
            "1. Clarify the user's goal related to: demo.\n"
            "2. Break the work into concrete steps.\n"
        ),
    )
    assert is_substantive_skill_content(stub) is False
    assert is_substantive_skill_content(_substantive_body("股市分析")) is True


def test_skill_wizard_stream_uses_agent_orchestration(tmp_path, monkeypatch):
    _skill_pool_setup(tmp_path, monkeypatch)
    skill_name = "auto-weekly-report"
    _write_workspace_skill(tmp_path, skill_name, _substantive_body("自动写周报"))

    async def fake_get_agent_for_request(request, agent_id=None):
        return _FakeWorkspace(tmp_path, _materialize_sse_events(skill_name))

    async def fake_ensure_chat_model(agent_id):
        return SimpleNamespace(provider_id="p", model="m"), None

    monkeypatch.setattr(agentdesk_chat, "ensure_chat_model", fake_ensure_chat_model)
    monkeypatch.setattr(agentdesk_chat, "get_agent_for_request", fake_get_agent_for_request)
    async def fake_reload(request, agent_id):
        return False

    monkeypatch.setattr(agentdesk_chat, "_reload_agent_after_skill_mount", fake_reload)
    monkeypatch.setattr(
        agentdesk_chat,
        "ensure_skill_creator_mounted",
        lambda **kwargs: ["make-skill"],
    )

    app = FastAPI()
    app.include_router(router)
    app.include_router(api_router)
    app.include_router(chat_router)
    client = TestClient(app)

    task = client.post("/api/tasks", json={"title": "技能创建"}).json()
    response = client.post(
        "/api/chat/stream",
        json={
            "task_id": task["id"],
            "message": "请帮我创建一个可以实现「自动写周报」的 skill",
            "intent": "skill_create",
            "wizard_action": "start",
        },
    )

    assert response.status_code == 200
    body = response.text
    assert "materialize_skill" in body
    assert "tool_call_end" in body or '"step": "tool_call_end"' in body
    assert "skill_done" in body
    assert skill_name in body

    plan = client.get(f"/api/tasks/{task['id']}/plan").json()
    assert plan["wizard"]["status"] == "skill_done"
    assert plan["wizard"]["created_skill"]["name"] == skill_name

    skills = client.get("/api/skills").json()
    assert any(item["name"] == skill_name for item in skills)
    created_item = next(item for item in skills if item["name"] == skill_name)
    assert created_item["installed"] is True
    assert created_item["enabled"] is True


def test_skill_wizard_stream_syncs_chinese_skill_name(tmp_path, monkeypatch):
    _skill_pool_setup(tmp_path, monkeypatch)
    skill_name = "资讯分析"
    _write_workspace_skill(tmp_path, skill_name, _substantive_body("资讯分析"))

    async def fake_get_agent_for_request(request, agent_id=None):
        return _FakeWorkspace(tmp_path, _materialize_sse_events(skill_name))

    async def fake_ensure_chat_model(agent_id):
        return SimpleNamespace(provider_id="p", model="m"), None

    monkeypatch.setattr(agentdesk_chat, "ensure_chat_model", fake_ensure_chat_model)
    monkeypatch.setattr(agentdesk_chat, "get_agent_for_request", fake_get_agent_for_request)
    async def fake_reload(request, agent_id):
        return False

    monkeypatch.setattr(agentdesk_chat, "_reload_agent_after_skill_mount", fake_reload)
    monkeypatch.setattr(
        agentdesk_chat,
        "ensure_skill_creator_mounted",
        lambda **kwargs: ["make-skill"],
    )

    app = FastAPI()
    app.include_router(router)
    app.include_router(api_router)
    app.include_router(chat_router)
    client = TestClient(app)

    task = client.post("/api/tasks", json={"title": "技能创建"}).json()
    response = client.post(
        "/api/chat/stream",
        json={
            "task_id": task["id"],
            "message": "请帮我创建一个可以实现「资讯分析」的 skill",
            "intent": "skill_create",
            "wizard_action": "start",
        },
    )

    assert response.status_code == 200
    assert "skill_done" in response.text
    assert '"type": "artifact"' in response.text or '"type":"artifact"' in response.text

    task_detail = client.get(f"/api/tasks/{task['id']}").json()
    assistant_msgs = [
        msg for msg in task_detail.get("messages", []) if msg.get("role") == "assistant"
    ]
    assert assistant_msgs
    artifacts = assistant_msgs[-1].get("artifacts") or []
    assert any(
        str(item.get("path") or "").endswith(f"skills/{skill_name}/SKILL.md")
        for item in artifacts
        if isinstance(item, dict)
    )

    skills = client.get("/api/skills").json()
    assert any(item["name"] == skill_name for item in skills)

    tree = client.get(f"/api/skills/{skill_name}/files")
    assert tree.status_code == 200
    assert tree.json()["skill_name"] == skill_name


def test_skill_wizard_stream_does_not_report_done_without_materialize(
    tmp_path,
    monkeypatch,
):
    _skill_pool_setup(tmp_path, monkeypatch)

    async def fake_get_agent_for_request(request, agent_id=None):
        text_evt = {
            "object": "content",
            "type": "text",
            "text": "我会帮你创建技能。",
            "delta": True,
        }
        return _FakeWorkspace(
            tmp_path,
            [f"data: {json.dumps(text_evt, ensure_ascii=False)}\n\n"],
        )

    async def fake_ensure_chat_model(agent_id):
        return SimpleNamespace(provider_id="p", model="m"), None

    monkeypatch.setattr(agentdesk_chat, "ensure_chat_model", fake_ensure_chat_model)
    monkeypatch.setattr(agentdesk_chat, "get_agent_for_request", fake_get_agent_for_request)
    async def fake_reload(request, agent_id):
        return False

    monkeypatch.setattr(agentdesk_chat, "_reload_agent_after_skill_mount", fake_reload)
    monkeypatch.setattr(
        agentdesk_chat,
        "ensure_skill_creator_mounted",
        lambda **kwargs: ["make-skill"],
    )

    app = FastAPI()
    app.include_router(router)
    app.include_router(api_router)
    app.include_router(chat_router)
    client = TestClient(app)

    task = client.post("/api/tasks", json={"title": "技能创建"}).json()
    response = client.post(
        "/api/chat/stream",
        json={
            "task_id": task["id"],
            "message": "请帮我创建一个可以实现「股市分析」的 skill",
            "intent": "skill_create",
            "wizard_action": "start",
        },
    )

    assert response.status_code == 200
    body = response.text
    assert "skill_done" not in body
    assert "skill_failed" in body

    plan = client.get(f"/api/tasks/{task['id']}/plan").json()
    assert plan["wizard"]["status"] == "skill_failed"
