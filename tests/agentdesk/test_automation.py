# -*- coding: utf-8 -*-
"""Automation job persistence and field mapping tests."""

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

import qwenpaw.constant as qwenpaw_constant
from qwenpaw.agentdesk import automation
from qwenpaw.agentdesk.router import api_router, router
from qwenpaw.agentdesk.store import AgentDeskStore


def _fake_config(tmp_path):
    default_workspace = tmp_path / "workspaces" / "default"
    default_workspace.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        agents=SimpleNamespace(
            active_agent="default",
            profiles={
                "default": SimpleNamespace(
                    workspace_dir=str(default_workspace),
                    enabled=True,
                ),
            },
        ),
        tools=SimpleNamespace(builtin_tools={}),
        mcp=SimpleNamespace(clients={}),
    )


def _client(tmp_path, monkeypatch) -> TestClient:
    import qwenpaw.agentdesk.agent_workspace as agent_workspace
    import qwenpaw.agentdesk.automation_routes as automation_routes
    import qwenpaw.agentdesk.task_routes as task_routes

    agentdesk_store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(
        automation_routes,
        "store",
        agentdesk_store,
    )
    monkeypatch.setattr(
        task_routes,
        "store",
        agentdesk_store,
    )
    monkeypatch.setattr(qwenpaw_constant, "WORKING_DIR", tmp_path)
    config = _fake_config(tmp_path)
    monkeypatch.setattr(
        agent_workspace,
        "load_config",
        lambda: config,
    )
    app = FastAPI()
    app.include_router(router)
    app.include_router(api_router)
    return TestClient(app)


def test_schedule_frequency_labels():
    assert automation.schedule_frequency_label({"mode": "periodic", "cron": "0 9 * * *"}) == "每天 09:00"
    assert automation.schedule_frequency_label({"mode": "interval", "interval_unit": "hours", "interval_amount": 2}) == "每 2 小时"
    assert automation.schedule_frequency_label({"mode": "once", "run_at": "2026-06-15T09:30:00"}) == "单次 06-15 09:30"


def test_build_automation_job_maps_payload_fields():
    job = automation.build_automation_job(
        "job-1",
        {
            "name": "Daily digest",
            "workspace": "Claw",
            "prompt": "Summarize inbox",
            "model_name": "GLM-5.1",
            "skill_names": ["cron"],
            "chat_mode": "plan",
            "schedule": {"type": "cron", "cron": "0 9 * * *", "mode": "periodic"},
            "date_range": {"start": "2026-06-01", "end": "2026-12-31"},
        },
    )
    assert job["id"] == "job-1"
    assert job["name"] == "Daily digest"
    assert job["workspace"] == "Claw"
    assert job["prompt"] == "Summarize inbox"
    assert job["model_name"] == "GLM-5.1"
    assert job["skill_names"] == ["cron"]
    assert job["chat_mode"] == "plan"
    assert job["schedule"]["cron"] == "0 9 * * *"
    assert job["date_range"]["start"] == "2026-06-01"
    assert job["date_range"]["end"] == "2026-12-31"
    assert job["task_id"]


def test_create_automation_job_persists_and_links_task(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    created = client.post(
        "/api/automation/jobs",
        json={
            "name": "Morning report",
            "workspace": "Claw",
            "prompt": "Generate daily summary",
            "model_name": "Auto",
            "skill_names": [],
            "chat_mode": "chat",
            "schedule": {
                "type": "cron",
                "cron": "0 9 * * *",
                "timezone": "Asia/Shanghai",
                "mode": "periodic",
            },
            "date_range": {"start": "2026-06-01", "end": None},
        },
    ).json()

    assert created["name"] == "Morning report"
    assert created["frequency"] == "每天 09:00"
    assert created["task_id"]

    listed = client.get("/api/automation/jobs").json()
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]

    task = client.get(f"/api/tasks/{created['task_id']}").json()
    assert task["id"] == created["task_id"]


def test_update_automation_job(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/automation/jobs",
        json={"id": "job-1", "name": "Old", "prompt": "Do work", "schedule": {"cron": "0 9 * * *"}},
    ).json()

    updated = client.put(
        "/api/automation/jobs/job-1",
        json={
            "name": "Renamed",
            "prompt": "Do better work",
            "schedule": {"cron": "30 8 * * 1-5", "mode": "periodic"},
        },
    ).json()

    assert updated["name"] == "Renamed"
    assert updated["prompt"] == "Do better work"
    assert updated["task_id"] == created["task_id"]
    assert "工作日" in updated["frequency"]


def test_automation_history_is_formatted(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    client.post(
        "/api/automation/jobs",
        json={"id": "job-1", "name": "Run me", "prompt": "Go", "schedule": {"cron": "0 9 * * *"}},
    )
    client.post("/api/automation/jobs/job-1/run")

    history = client.get("/api/automation/history").json()
    assert len(history) == 1
    assert history[0]["job_id"] == "job-1"
    assert history[0]["time"]
    assert history[0]["status"] in {"已排队", "运行中"}
