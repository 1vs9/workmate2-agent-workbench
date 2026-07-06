# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from qwenpaw.agentdesk import router, skill_routes


def test_mount_skill_with_task_id_attaches_resolved_skill(monkeypatch) -> None:
    calls: dict[str, object] = {}

    monkeypatch.setattr(skill_routes, "resolve_agentdesk_agent_id", lambda name: "agent-1")
    monkeypatch.setattr(
        skill_routes,
        "resolve_workspace_skill_name",
        lambda agent_id, skill_name: None,
    )
    monkeypatch.setattr(
        skill_routes,
        "resolve_mount_skill_name",
        lambda skill_name: "resolved-skill",
    )
    monkeypatch.setattr(
        skill_routes,
        "ensure_skill_mounted",
        lambda **kwargs: {
            "mounted": True,
            "skill_name": kwargs["skill_name"],
            "agent_id": kwargs["agent_id"],
        },
    )
    monkeypatch.setattr(
        skill_routes,
        "attach_skill_to_task_record",
        lambda task_id, skill_name: calls.setdefault(
            "attached",
            (task_id, skill_name),
        ),
    )

    result = skill_routes.mount_skill_for_request(
        "Display Skill",
        {"employee_name": "Analyst", "task_id": "task-1"},
    )

    assert result.agent_id == "agent-1"
    assert result.payload == {
        "mounted": True,
        "skill_name": "resolved-skill",
        "agent_id": "agent-1",
        "requested_skill": "Display Skill",
    }
    assert calls["attached"] == ("task-1", "resolved-skill")


def test_mount_skill_returns_existing_workspace_mount(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(skill_routes, "resolve_agentdesk_agent_id", lambda name: "agent-1")
    monkeypatch.setattr(
        skill_routes,
        "resolve_workspace_skill_name",
        lambda agent_id, skill_name: "existing-skill",
    )
    monkeypatch.setattr(
        skill_routes,
        "agent_workspace_dir",
        lambda agent_id: tmp_path / agent_id,
    )

    result = skill_routes.mount_skill_for_request(
        "Display Skill",
        {"employee_name": "Analyst"},
    )

    assert result.agent_id == "agent-1"
    assert result.payload == {
        "mounted": True,
        "already_mounted": True,
        "skill_name": "existing-skill",
        "requested_skill": "Display Skill",
        "agent_id": "agent-1",
        "workspace_dir": str(tmp_path / "agent-1"),
    }


@pytest.mark.asyncio
async def test_mount_skill_endpoint_schedules_reload(monkeypatch) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setattr(
        router,
        "_mount_skill_for_request",
        lambda skill_name, body: skill_routes.SkillMutationResult(
            agent_id="agent-1",
            payload={"mounted": True, "skill_name": skill_name},
        ),
    )
    monkeypatch.setattr(
        router,
        "_schedule_mutation_reload",
        lambda request, result: calls.setdefault("reloaded", result.agent_id),
    )

    result = await router.mount_skill("Display Skill", {"task_id": "task-1"}, object())

    assert result == {"mounted": True, "skill_name": "Display Skill"}
    assert calls["reloaded"] == "agent-1"
