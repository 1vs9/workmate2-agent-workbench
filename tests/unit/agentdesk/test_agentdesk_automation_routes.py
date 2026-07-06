# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

from qwenpaw.agentdesk import automation_routes
from qwenpaw.agentdesk.store import AgentDeskStore


@pytest.mark.asyncio
async def test_create_automation_job_persists_task_and_cron_id(
    monkeypatch,
    tmp_path,
) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    calls: dict[str, object] = {}
    monkeypatch.setattr(automation_routes, "store", store)
    monkeypatch.setattr(
        automation_routes,
        "resolve_agentdesk_agent_id",
        lambda employee_name: "agent-1",
    )

    async def _sync(request, job, *, agent_id: str):
        calls["sync"] = (request, job["id"], agent_id)
        return "cron-1"

    monkeypatch.setattr(automation_routes, "sync_cron_upsert", _sync)

    result = await automation_routes.create_automation_job_payload(
        {
            "id": "job-1",
            "task_id": "task-1",
            "name": "Daily brief",
            "workspace": "research",
            "employee_name": "Analyst",
            "skill_names": ["news", ""],
        },
        request=object(),
    )

    assert result["id"] == "job-1"
    assert result["cron_job_id"] == "cron-1"
    assert calls["sync"][1:] == ("job-1", "agent-1")
    task = store.get_by_key("tasks", "id", "task-1")
    assert task is not None
    assert task["automation_job_id"] == "job-1"
    assert task["workspace_label"] == "research"
    assert task["skill_names"] == ["news"]


@pytest.mark.asyncio
async def test_update_automation_job_preserves_cron_and_created_at(
    monkeypatch,
    tmp_path,
) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(automation_routes, "store", store)
    monkeypatch.setattr(
        automation_routes,
        "resolve_agentdesk_agent_id",
        lambda employee_name: "agent-1",
    )
    existing = store.upsert_by_key(
        "automation_jobs",
        "id",
        "job-1",
        {
            "id": "job-1",
            "task_id": "task-1",
            "name": "Old",
            "cron_job_id": "cron-existing",
            "created_at": 123.0,
        },
    )

    async def _sync(request, job, *, agent_id: str):
        assert job["cron_job_id"] == "cron-existing"
        return None

    monkeypatch.setattr(automation_routes, "sync_cron_upsert", _sync)

    result = await automation_routes.update_automation_job_payload(
        "job-1",
        {"name": "New", "employee_name": "Analyst"},
        request=object(),
    )

    assert result["name"] == "New"
    assert result["cron_job_id"] == "cron-existing"
    assert result["created_at"] == existing["created_at"]


@pytest.mark.asyncio
async def test_run_automation_job_records_history(monkeypatch, tmp_path) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(automation_routes, "store", store)
    store.upsert_by_key(
        "automation_jobs",
        "id",
        "job-1",
        {
            "id": "job-1",
            "task_id": "task-1",
            "name": "Daily brief",
            "workspace": "research",
            "cron_job_id": "cron-1",
        },
    )

    async def _run(request, cron_job_id):
        assert cron_job_id == "cron-1"
        return True

    monkeypatch.setattr(automation_routes, "sync_cron_run", _run)

    result = await automation_routes.run_automation_job_payload("job-1", object())

    assert result == {"id": "job-1", "status": "running", "cron_started": True}
    history = store.list_items("automation_history")
    assert len(history) == 1
    assert history[0]["job_id"] == "job-1"
    assert history[0]["status"] == "running"


@pytest.mark.asyncio
async def test_update_automation_job_missing_raises_domain_error(
    monkeypatch,
    tmp_path,
) -> None:
    store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(automation_routes, "store", store)

    with pytest.raises(automation_routes.AutomationJobNotFoundError):
        await automation_routes.update_automation_job_payload("missing", {}, object())
