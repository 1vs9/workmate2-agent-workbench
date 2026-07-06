# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from qwenpaw.agentdesk import skill_catalog
from qwenpaw.agentdesk.skill_catalog import (
    pool_skill_names,
    serialize_pool_skills,
    skill_content_from_payload,
    workspace_only_skill_items,
    workspace_skill_state,
    agentdesk_skill_item,
)


class _FakeSkillService:
    def __init__(self, names: list[str]) -> None:
        self.names = names

    def list_all_skills(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(name=name) for name in self.names]


def test_skill_content_from_payload_preserves_frontmatter() -> None:
    content = "---\nname: Existing\n---\nBody"

    assert skill_content_from_payload({"content": content}) == content


def test_skill_content_from_payload_renders_defaults() -> None:
    content = skill_content_from_payload({"name": "Search", "body": ""})

    assert "Search" in content
    assert "WorkBuddy skill" in content
    assert "Use this skill when the user requests this capability." in content


def test_agentdesk_skill_item_maps_builtin_source_to_agentdesk() -> None:
    item = agentdesk_skill_item(
        SimpleNamespace(
            name="Search",
            description="Find things",
            content="Body",
            source="builtin",
            version_text="v1",
            icon=None,
            emoji="S",
        ),
    )

    assert item == {
        "name": "Search",
        "description": "Find things",
        "body": "Body",
        "content": "Body",
        "source": "agentdesk",
        "version_text": "v1",
        "icon": "",
        "emoji": "S",
    }


def test_pool_skill_names_reads_service_names() -> None:
    assert pool_skill_names(_FakeSkillService(["a", "b"])) == {"a", "b"}


def test_workspace_skill_state_reads_manifest(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(skill_catalog, "agent_workspace_dir", lambda agent_id: tmp_path)
    monkeypatch.setattr(
        skill_catalog,
        "read_skill_manifest",
        lambda workspace_dir: {"skills": {"Search": {"enabled": True}}},
    )

    assert workspace_skill_state("agent-1") == {"Search": {"enabled": True}}


def test_workspace_skill_state_falls_back_on_error(monkeypatch) -> None:
    def _workspace(agent_id: str):
        raise RuntimeError("missing")

    monkeypatch.setattr(skill_catalog, "agent_workspace_dir", _workspace)

    assert workspace_skill_state("agent-1") == {}


def test_workspace_only_skill_items_serializes_missing_workspace_skills(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(skill_catalog, "agent_workspace_dir", lambda agent_id: tmp_path)
    monkeypatch.setattr(skill_catalog, "get_workspace_skills_dir", lambda path: path)
    monkeypatch.setattr(
        skill_catalog,
        "read_skill_from_dir",
        lambda path, source: SimpleNamespace(
            name=path.name,
            description="Workspace skill",
            content="Body",
            source=source,
        ),
    )

    items = workspace_only_skill_items(
        "agent-1",
        existing_names={"Existing"},
        workspace_state={
            "Existing": {"enabled": True},
            "WorkspaceOnly": {"enabled": True},
        },
    )

    assert list(items) == ["WorkspaceOnly"]
    assert items["WorkspaceOnly"]["source"] == "workspace"
    assert items["WorkspaceOnly"]["installed"] is True
    assert items["WorkspaceOnly"]["enabled"] is True


def test_serialize_pool_skills_merges_pool_workspace_and_store(monkeypatch) -> None:
    monkeypatch.setattr(
        skill_catalog,
        "load_config",
        lambda: SimpleNamespace(agents=SimpleNamespace(active_agent="agent-1")),
    )
    monkeypatch.setattr(
        skill_catalog,
        "workspace_skill_state",
        lambda agent_id: {
            "Pool": {"enabled": True},
            "WorkspaceOnly": {"enabled": False},
        },
    )
    monkeypatch.setattr(
        skill_catalog,
        "workspace_only_skill_items",
        lambda agent_id, existing_names, workspace_state: {
            "WorkspaceOnly": {
                "name": "WorkspaceOnly",
                "description": "Workspace",
                "body": "Workspace body",
                "content": "Workspace body",
                "source": "workspace",
                "installed": True,
                "enabled": False,
            },
        },
    )
    monkeypatch.setattr(
        skill_catalog,
        "SkillPoolService",
        lambda: _FakePoolService(
            [
                SimpleNamespace(
                    name="Pool",
                    description="Pool skill",
                    content="Pool body",
                    source="builtin",
                    version_text="",
                    icon="",
                    emoji="",
                ),
            ],
        ),
    )
    monkeypatch.setattr(
        skill_catalog,
        "store",
        SimpleNamespace(
            list_items=lambda collection: [
                {
                    "name": "StoreOnly",
                    "description": "Store skill",
                    "body": "Store body",
                },
            ],
        ),
    )

    items = serialize_pool_skills()

    assert [item["name"] for item in items] == ["Pool", "StoreOnly", "WorkspaceOnly"]
    by_name = {item["name"]: item for item in items}
    assert by_name["Pool"]["source"] == "agentdesk"
    assert by_name["Pool"]["installed"] is True
    assert by_name["Pool"]["enabled"] is True
    assert by_name["StoreOnly"]["installed"] is False
    assert by_name["WorkspaceOnly"]["source"] == "workspace"


class _FakePoolService:
    def __init__(self, skills: list[SimpleNamespace]) -> None:
        self.skills = skills

    def list_all_skills(self) -> list[SimpleNamespace]:
        return self.skills
