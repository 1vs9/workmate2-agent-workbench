# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.agentdesk import employee_plaza_records


def test_employee_plaza_sync_patch_keeps_only_mirrored_fields() -> None:
    patch = employee_plaza_records.employee_plaza_sync_patch(
        {
            "name": "Writer",
            "desc": "Writes",
            "skills": ["search"],
            "tools": ["browser"],
            "mcp": ["fs"],
            "avatar": "avatar.svg",
            "tags": ["QwenPaw"],
            "joined": True,
            "agent_id": "agent-1",
        },
    )

    assert patch == {
        "desc": "Writes",
        "skills": ["search"],
        "tools": ["browser"],
        "mcp": ["fs"],
        "avatar": "avatar.svg",
        "tags": ["QwenPaw"],
    }


def test_employee_record_from_plaza_item_projects_joined_employee_fields() -> None:
    employee = employee_plaza_records.employee_record_from_plaza_item(
        "Writer",
        {
            "name": "Writer",
            "desc": "Writes",
            "tools": ["browser"],
            "skills": ["search"],
            "mcp": ["fs"],
            "avatar": "avatar.svg",
            "tags": ["QwenPaw"],
        },
    )

    assert employee == {
        "name": "Writer",
        "desc": "Writes",
        "tools": ["browser"],
        "skills": ["search"],
        "mcp": ["fs"],
        "avatar": "avatar.svg",
    }


def test_requested_skill_names_strips_blanks() -> None:
    assert employee_plaza_records.requested_skill_names(
        {"skills": [" search ", "", "write", "  "]},
    ) == ["search", "write"]


def test_mounted_requested_skill_names_prefers_workspace_state() -> None:
    mounted = employee_plaza_records.mounted_requested_skill_names(
        "agent-1",
        ["search", "write"],
        workspace_skill_state=lambda agent_id: {"search": {"enabled": True}},
        agent_skill_names=lambda agent_id: ["write"],
    )

    assert mounted == ["search"]


def test_mounted_requested_skill_names_falls_back_to_agent_profile() -> None:
    mounted = employee_plaza_records.mounted_requested_skill_names(
        "agent-1",
        ["search", "write"],
        workspace_skill_state=lambda agent_id: {},
        agent_skill_names=lambda agent_id: ["write"],
    )

    assert mounted == ["write"]


def test_joined_employee_payload_marks_unmounted_requested_skills_failed() -> None:
    payload = employee_plaza_records.joined_employee_payload(
        {"name": "Writer", "skills": ["search", "write"]},
        requested_skills=["search", "write"],
        mounted_skills=["search"],
    )

    assert payload == {
        "name": "Writer",
        "skills": ["search", "write"],
        "joined": True,
        "requested_skills": ["search", "write"],
        "mounted_skills": ["search"],
        "failed_skills": ["write"],
    }
