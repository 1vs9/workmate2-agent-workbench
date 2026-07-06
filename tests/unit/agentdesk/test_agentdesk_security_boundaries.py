# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from qwenpaw.agentdesk import (
    config_api,
    task_workspace_files,
)
from qwenpaw.agentdesk.router import (
    api_router,
)
from qwenpaw.agentdesk.store import AgentDeskStore
from qwenpaw.agentdesk.task_cleanup import remove_task_workspace_dirs
from qwenpaw.agentdesk.task_projection import task_for_client


class _FakeProviderManager:
    def __init__(self) -> None:
        self.info = SimpleNamespace(
            id="openai",
            name="OpenAI",
            base_url="https://api.example.test",
            api_key="sk-secret-value",
            api_key_prefix="sk-sec",
            require_api_key=True,
            freeze_url=False,
            is_local=False,
            is_custom=False,
            models=[SimpleNamespace(id="gpt-test", name="GPT Test")],
            extra_models=[],
        )

    async def list_provider_info(self):
        return [self.info]

    async def get_provider_info(self, provider_id: str):
        return self.info if provider_id == self.info.id else None

    def get_provider(self, provider_id: str):
        if provider_id != self.info.id:
            return None
        return SimpleNamespace(
            api_key="sk-secret-value",
            auth_token="",
            require_api_key=True,
        )

    def get_active_model(self):
        return None

    def update_provider(self, provider_id: str, updates: dict) -> bool:
        if provider_id != self.info.id:
            return False
        for key, value in updates.items():
            setattr(self.info, key, value)
        return True


@pytest.mark.asyncio
async def test_agentdesk_config_redacts_provider_api_key(monkeypatch) -> None:
    manager = _FakeProviderManager()
    monkeypatch.setattr(
        config_api.ProviderManager,
        "get_instance",
        lambda: manager,
    )
    monkeypatch.setattr(
        config_api,
        "get_health_model_info",
        lambda: {"model_ready": False, "active_model": None},
    )

    payload = await config_api.build_agentdesk_config()

    provider = payload["providers"][0]
    assert "api_key" not in provider
    assert provider["api_key_prefix"] == "sk-sec"
    assert provider["api_key_configured"] is True


@pytest.mark.asyncio
async def test_agentdesk_update_provider_redacts_provider_api_key(monkeypatch) -> None:
    manager = _FakeProviderManager()
    monkeypatch.setattr(
        config_api.ProviderManager,
        "get_instance",
        lambda: manager,
    )

    provider = await config_api.update_agentdesk_provider(
        "openai",
        {"api_key": "sk-new-secret"},
    )

    assert "api_key" not in provider
    assert provider["api_key_configured"] is True


def test_create_task_rejects_client_controlled_workspace_dir(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(task_workspace_files, "store", store)
    app = FastAPI()
    app.include_router(api_router)

    response = TestClient(app).post(
        "/api/tasks",
        json={"id": "task-1", "title": "Task", "workspace_dir": str(tmp_path)},
    )

    assert response.status_code == 400
    assert store.get_by_key("tasks", "id", "task-1") is None


def test_task_for_client_projects_messages_through_shared_projection() -> None:
    task = {
        "id": "task-1",
        "messages": [
            {
                "role": "user",
                "content": (
                    "Use skill context. the user's task: visible request"
                    "\n\nTool context follows"
                ),
            },
            {"role": "assistant", "content": "answer"},
            "invalid",
        ],
    }

    out = task_for_client(task)

    assert out["messages"] == [
        {"role": "user", "content": "visible request"},
        {"role": "assistant", "content": "answer"},
    ]


def test_workspace_file_rejects_absolute_path(tmp_path, monkeypatch) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    store.upsert_by_key(
        "tasks",
        "id",
        "task-1",
        {"id": "task-1", "agent_id": "default"},
    )
    monkeypatch.setattr(task_workspace_files, "store", store)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        task_workspace_files.resolve_task_workspace_file("task-1", str(outside))

    assert exc.value.status_code == 400


@pytest.mark.parametrize("unsafe_path", ["C:secret.txt", "/secret.txt"])
def test_workspace_file_rejects_drive_or_rooted_path(
    tmp_path,
    monkeypatch,
    unsafe_path: str,
) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    store.upsert_by_key(
        "tasks",
        "id",
        "task-1",
        {"id": "task-1", "agent_id": "default"},
    )
    monkeypatch.setattr(task_workspace_files, "store", store)

    with pytest.raises(HTTPException) as exc:
        task_workspace_files.resolve_task_workspace_file("task-1", unsafe_path)

    assert exc.value.status_code == 400


def test_workspace_roots_ignore_untrusted_task_workspace_dir(tmp_path, monkeypatch) -> None:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    untrusted = tmp_path / "untrusted"
    untrusted.mkdir()
    store = AgentDeskStore(tmp_path / "store.json")
    store.upsert_by_key(
        "tasks",
        "id",
        "task-1",
        {
            "id": "task-1",
            "agent_id": "default",
            "workspace_dir": str(untrusted),
        },
    )
    monkeypatch.setattr(task_workspace_files, "store", store)
    monkeypatch.setattr(
        task_workspace_files,
        "_agent_workspace_dir",
        lambda _agent_id: trusted,
    )

    roots = task_workspace_files.task_workspace_roots("task-1")

    assert roots == [trusted.resolve()]


def test_workspace_file_rejects_symlink_escape(tmp_path, monkeypatch) -> None:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = trusted / "outside-link.txt"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable on this platform: {exc}")

    store = AgentDeskStore(tmp_path / "store.json")
    store.upsert_by_key(
        "tasks",
        "id",
        "task-1",
        {"id": "task-1", "agent_id": "default"},
    )
    monkeypatch.setattr(task_workspace_files, "store", store)
    monkeypatch.setattr(
        task_workspace_files,
        "_agent_workspace_dir",
        lambda _agent_id: trusted,
    )

    with pytest.raises(HTTPException) as exc:
        task_workspace_files.resolve_task_workspace_file("task-1", "outside-link.txt")

    assert exc.value.status_code == 404


def test_workspace_tree_hides_symlink_escape(tmp_path, monkeypatch) -> None:
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    (trusted / "inside.txt").write_text("inside", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = trusted / "outside-link.txt"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink unavailable on this platform: {exc}")

    store = AgentDeskStore(tmp_path / "store.json")
    store.upsert_by_key(
        "tasks",
        "id",
        "task-1",
        {"id": "task-1", "agent_id": "default"},
    )
    monkeypatch.setattr(task_workspace_files, "store", store)
    monkeypatch.setattr(
        task_workspace_files,
        "_agent_workspace_dir",
        lambda _agent_id: trusted,
    )
    app = FastAPI()
    app.include_router(api_router)

    response = TestClient(app).get("/api/tasks/task-1/workspace/tree")

    assert response.status_code == 200
    assert response.json()["files"] == [{"path": "inside.txt"}]


def test_delete_task_does_not_remove_untrusted_workspace_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("qwenpaw.agentdesk.task_cleanup.WORKING_DIR", tmp_path)
    external = tmp_path / "external-task-1"
    external.mkdir()
    (external / "keep.txt").write_text("keep", encoding="utf-8")

    removed = remove_task_workspace_dirs(
        "task-1",
        {"id": "task-1", "workspace_dir": str(external)},
    )

    assert removed == []
    assert external.is_dir()
    assert (external / "keep.txt").is_file()


def test_delete_task_removes_only_owned_task_workspace(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("qwenpaw.agentdesk.task_cleanup.WORKING_DIR", tmp_path)
    owned = tmp_path / "agentdesk" / "task-workspaces" / "task-1"
    owned.mkdir(parents=True)
    (owned / "artifact.txt").write_text("artifact", encoding="utf-8")

    removed = remove_task_workspace_dirs("task-1", {"id": "task-1"})

    assert removed == [str(owned.resolve())]
    assert not owned.exists()
