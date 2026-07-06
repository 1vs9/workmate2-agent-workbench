# -*- coding: utf-8 -*-
"""Tests for AgentDesk approval compatibility endpoint."""

from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient

import qwenpaw.agentdesk.chat as agentdesk_chat
import qwenpaw.agentdesk.chat_message_composer as chat_message_composer
import qwenpaw.agentdesk.chat_skill_mount as chat_skill_mount
from qwenpaw.agentdesk import session_routing
from qwenpaw.agentdesk.chat import router
from qwenpaw.agentdesk.models import ChatRequest
from qwenpaw.agentdesk.store import AgentDeskStore


class _Pending:
    request_id = "req-1"
    session_id = "task-1"
    root_session_id = "task-1"
    tool_name = "shell"


class _ApprovalService:
    def __init__(self) -> None:
        self.resolved: tuple[str, object] | None = None
        self.root_pending = False

    async def get_request(self, request_id: str):
        return _Pending() if request_id == "req-1" else None

    async def get_pending_by_session(self, session_id: str):
        if self.root_pending:
            return None
        return _Pending() if session_id == "task-1" else None

    async def get_pending_by_root_session(self, session_id: str):
        return [_Pending()] if self.root_pending and session_id == "task-1" else []

    async def resolve_request(self, request_id: str, decision):
        self.resolved = (request_id, decision)
        return _Pending()


def test_chat_approve_without_request_id_is_noop():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/chat/approve",
        json={"task_id": "task-1", "approved": True},
    )

    assert response.status_code == 200
    assert response.json() == {
        "task_id": "task-1",
        "approved": True,
        "status": "no_pending_approval",
    }


def test_chat_approve_uses_pending_session_request_when_request_id_missing(
    monkeypatch,
):
    service = _ApprovalService()
    monkeypatch.setattr(agentdesk_chat, "get_approval_service", lambda: service)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/chat/approve",
        json={"task_id": "task-1", "approved": True},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["request_id"] == "req-1"
    assert service.resolved is not None


def test_chat_approve_falls_back_to_root_session_pending_request(monkeypatch):
    service = _ApprovalService()
    service.root_pending = True
    monkeypatch.setattr(agentdesk_chat, "get_approval_service", lambda: service)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        "/api/chat/approve",
        json={"task_id": "task-1", "approved": False},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "denied"
    assert response.json()["request_id"] == "req-1"
    assert service.resolved is not None


async def test_chat_skill_names_are_mounted_and_persisted(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        chat_skill_mount,
        "agentdesk_store",
        AgentDeskStore(tmp_path / "store.json"),
    )

    def fake_mount(*, skill_name, agent_id, overwrite=False, user_text=None):
        calls.append((skill_name, agent_id, overwrite))
        return {"mounted": True, "skill_name": skill_name, "agent_id": agent_id}

    monkeypatch.setattr(chat_skill_mount, "ensure_skill_mounted", fake_mount)
    payload = ChatRequest(
        task_id="task-1",
        message="hello",
        employee_name="Analyst",
        skill_names=["search", "search", "docx"],
    )

    mounted = await chat_skill_mount.ensure_payload_skills_mounted(
        payload,
        agent_id="Analyst",
        request=None,
    )
    task = chat_skill_mount.agentdesk_store.get_by_key("tasks", "id", "task-1")

    assert mounted == ["search", "docx"]
    assert calls == [
        ("search", "Analyst", False),
        ("docx", "Analyst", False),
    ]
    assert task["skill_names"] == ["search", "docx"]


async def test_chat_skill_mount_surfaces_missing_skill(monkeypatch):
    def fake_mount(*, skill_name, agent_id, overwrite=False, user_text=None):
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    monkeypatch.setattr(chat_skill_mount, "ensure_skill_mounted", fake_mount)
    payload = ChatRequest(
        task_id="task-1",
        message="hello",
        employee_name="Analyst",
        skill_names=["missing"],
    )

    try:
        await chat_skill_mount.ensure_payload_skills_mounted(
            payload,
            agent_id="Analyst",
            request=None,
        )
    except HTTPException as exc:
        assert exc.status_code == 404
        assert "missing" in str(exc.detail)
    else:  # pragma: no cover
        raise AssertionError("Expected missing skill to raise HTTPException")


def test_chat_routing_records_team_and_single_modes():
    team_payload = ChatRequest(
        task_id="task-team",
        message="hello",
        mode="team",
        team_id="team-1",
        team_name="开户协同小队",
    )
    team_task = session_routing.apply_chat_routing_to_task(
        {"id": "task-team"},
        team_payload,
    )
    assert team_task.get("mode") == "team"
    assert team_task.get("team_id") == "team-1"
    assert team_task.get("team_name") == "开户协同小队"
    assert "employee_name" not in team_task

    single_payload = ChatRequest(
        task_id="task-single",
        message="hello",
        mode="single",
        employee_name="Analyst",
    )
    single_task = session_routing.apply_chat_routing_to_task(
        {"id": "task-single"},
        single_payload,
    )
    assert single_task.get("mode") == "single"
    assert single_task.get("employee_name") == "Analyst"
    assert "team_id" not in single_task
    assert "team_name" not in single_task


def test_augment_user_message_with_skills_injects_skill_body(tmp_path):
    skill_dir = tmp_path / "skills" / "xiaobei-ppt-style"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("SKILL.md").write_text(
        "---\nname: xiaobei-ppt-style\ndescription: PPT style\n---\n\nFollow red theme.\n",
        encoding="utf-8",
    )

    merged = chat_message_composer.augment_user_message_with_skills(
        tmp_path,
        "make a deck",
        ["xiaobei-ppt-style"],
    )

    assert "Follow red theme." in merged
    assert "make a deck" in merged
    assert "xiaobei-ppt-style" in merged
    assert "Use the [xiaobei-ppt-style] skill" in merged


def test_augment_user_message_with_skills_uses_chinese_wrapper(tmp_path):
    skill_dir = tmp_path / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: demo\n---\n\n按红色主题排版。\n",
        encoding="utf-8",
    )

    merged = chat_message_composer.augment_user_message_with_skills(
        tmp_path,
        "请帮我做一份汇报 PPT",
        ["demo-skill"],
    )

    assert "按红色主题排版。" in merged
    assert "使用工作区技能" in merged
    assert "请帮我做一份汇报 PPT" in merged


def test_augment_user_message_with_skills_noop_without_skills(tmp_path):
    assert (
        chat_message_composer.augment_user_message_with_skills(tmp_path, "hello", [])
        == "hello"
    )


def test_resolve_chat_user_messages_keeps_display_separate_from_agent(tmp_path):
    skill_dir = tmp_path / "skills" / "xiaobei-ppt-style"
    skill_dir.mkdir(parents=True)
    skill_dir.joinpath("SKILL.md").write_text(
        "---\nname: xiaobei-ppt-style\ndescription: PPT style\n---\n\nFollow red theme.\n",
        encoding="utf-8",
    )

    display, agent = chat_message_composer.resolve_chat_user_messages(
        tmp_path,
        "创建一个ai科普的ppt",
        ["xiaobei-ppt-style"],
    )

    assert display == "创建一个ai科普的ppt"
    assert "agentdesk-locale-hint" in agent
    assert "中文" in agent
    assert "Follow red theme." in agent
    assert display not in agent or agent.index(display) < agent.index("Follow red theme.")


def test_resolve_chat_user_messages_adds_chinese_hint_without_skills(tmp_path):
    display, agent = chat_message_composer.resolve_chat_user_messages(
        tmp_path,
        "今天天气怎么样？",
        [],
    )

    assert display == "今天天气怎么样？"
    assert "agentdesk-locale-hint" in agent
    assert "中文" in agent
    assert agent.endswith("今天天气怎么样？")


def test_display_user_message_content_strips_skill_injection():
    from qwenpaw.agentdesk.user_message_display import display_user_message_content

    augmented = (
        "Use the [xiaobei-ppt-style] skill in `/tmp/skills/xiaobei-ppt-style` to fulfill "
        "the user's task: 创建一个ai科普的ppt\n\nFollow red theme.\n"
    )
    assert display_user_message_content(augmented) == "创建一个ai科普的ppt"
    assert display_user_message_content("plain hello") == "plain hello"


def test_display_user_message_content_strips_chinese_skill_wrapper():
    from qwenpaw.agentdesk.user_message_display import display_user_message_content

    augmented = (
        "<agentdesk-locale-hint>本轮请使用中文回复。</agentdesk-locale-hint>\n\n"
        "使用工作区技能 `[demo]`（`/tmp/skills/demo`）完成用户任务：请做汇报\n\n正文"
    )
    assert display_user_message_content(augmented) == "请做汇报"
