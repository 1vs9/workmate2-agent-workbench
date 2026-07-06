# -*- coding: utf-8 -*-
"""Tests for AgentDesk chat payload skill mounting."""

import qwenpaw.agentdesk.chat_skill_mount as chat_skill_mount
from qwenpaw.agentdesk.models import ChatRequest
from qwenpaw.agentdesk.store import AgentDeskStore


def test_dedupe_skill_names_strips_blanks_and_preserves_order():
    assert chat_skill_mount.dedupe_skill_names(
        [" search ", "", "docx", "search", "  ", "slides"],
    ) == ["search", "docx", "slides"]


def test_ensure_payload_skills_mounted_sync_persists_task_skills(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        chat_skill_mount,
        "agentdesk_store",
        AgentDeskStore(tmp_path / "store.json"),
    )
    monkeypatch.setattr(
        chat_skill_mount,
        "ensure_packaged_builtin_in_pool",
        lambda skill_name, *, user_text=None: None,
    )

    def fake_mount(*, skill_name, agent_id, overwrite=False, user_text=None):
        calls.append((skill_name, agent_id, overwrite, user_text))
        return {"skill_name": skill_name}

    monkeypatch.setattr(chat_skill_mount, "ensure_skill_mounted", fake_mount)
    payload = ChatRequest(
        task_id="task-1",
        message="make a report",
        employee_name="Analyst",
        skill_names=["search", "search", "docx"],
    )

    mounted = chat_skill_mount.ensure_payload_skills_mounted_sync(
        payload,
        agent_id="Analyst",
    )

    task = chat_skill_mount.agentdesk_store.get_by_key("tasks", "id", "task-1")
    assert mounted == ["search", "docx"]
    assert calls == [
        ("search", "Analyst", False, "make a report"),
        ("docx", "Analyst", False, "make a report"),
    ]
    assert task["skill_names"] == ["search", "docx"]
