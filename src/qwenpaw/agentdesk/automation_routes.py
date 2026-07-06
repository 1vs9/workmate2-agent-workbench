# -*- coding: utf-8 -*-
"""AgentDesk automation endpoint orchestration helpers."""

from __future__ import annotations

import uuid
from typing import Any

from .agent_workspace import resolve_agentdesk_agent_id
from .automation import (
    build_automation_job,
    build_history_record,
    enrich_automation_history,
    enrich_automation_job,
    sync_cron_delete,
    sync_cron_pause,
    sync_cron_resume,
    sync_cron_run,
    sync_cron_upsert,
)
from .store import store


class AutomationJobNotFoundError(LookupError):
    """Raised when a AgentDesk automation job does not exist."""


def persist_automation_task(job: dict[str, Any]) -> None:
    task_id = str(job.get("task_id") or "").strip()
    if not task_id:
        return
    task = store.ensure_task(task_id, title=str(job.get("name") or "Automation"))
    task["automation_job_id"] = job.get("id")
    task["workspace_label"] = job.get("workspace")
    if job.get("skill_names"):
        task["skill_names"] = list(job.get("skill_names") or [])
    store.upsert_by_key("tasks", "id", task_id, task)


def list_automation_job_payloads() -> list[dict[str, Any]]:
    return [enrich_automation_job(job) for job in store.list_items("automation_jobs")]


async def create_automation_job_payload(
    body: dict[str, Any] | None,
    request: Any,
) -> dict[str, Any]:
    payload = dict(body or {})
    job_id = str(payload.get("id") or uuid.uuid4().hex)
    job = build_automation_job(job_id, payload)
    persist_automation_task(job)
    agent_id = resolve_agentdesk_agent_id(
        str(payload.get("employee_name") or "") or None,
    )
    cron_job_id = await sync_cron_upsert(request, job, agent_id=agent_id)
    if cron_job_id:
        job["cron_job_id"] = cron_job_id
    stored = store.upsert_by_key("automation_jobs", "id", job_id, job)
    return enrich_automation_job(stored)


async def update_automation_job_payload(
    job_id: str,
    body: dict[str, Any] | None,
    request: Any,
) -> dict[str, Any]:
    existing = store.get_by_key("automation_jobs", "id", job_id)
    if existing is None:
        raise AutomationJobNotFoundError(job_id)
    payload = {**existing, **dict(body or {}), "id": job_id}
    job = build_automation_job(job_id, payload)
    job["cron_job_id"] = existing.get("cron_job_id") or job.get("cron_job_id")
    job["created_at"] = existing.get("created_at", job.get("created_at"))
    persist_automation_task(job)
    agent_id = resolve_agentdesk_agent_id(
        str(job.get("employee_name") or "") or None,
    )
    cron_job_id = await sync_cron_upsert(request, job, agent_id=agent_id)
    if cron_job_id:
        job["cron_job_id"] = cron_job_id
    stored = store.upsert_by_key("automation_jobs", "id", job_id, job)
    return enrich_automation_job(stored)


async def run_automation_job_payload(job_id: str, request: Any) -> dict[str, Any]:
    job = store.get_by_key("automation_jobs", "id", job_id)
    if job is None:
        raise AutomationJobNotFoundError(job_id)
    started = await sync_cron_run(request, job.get("cron_job_id"))
    history = build_history_record(job, status="running" if started else "queued")
    store.upsert_by_key("automation_history", "id", history["id"], history)
    return {"id": job_id, "status": history["status"], "cron_started": started}


async def pause_automation_job_payload(job_id: str, request: Any) -> dict[str, Any]:
    job = store.get_by_key("automation_jobs", "id", job_id)
    if job is None:
        raise AutomationJobNotFoundError(job_id)
    job["enabled"] = False
    job["status"] = "paused"
    await sync_cron_pause(request, job.get("cron_job_id"))
    stored = store.upsert_by_key("automation_jobs", "id", job_id, job)
    return enrich_automation_job(stored)


async def resume_automation_job_payload(job_id: str, request: Any) -> dict[str, Any]:
    job = store.get_by_key("automation_jobs", "id", job_id)
    if job is None:
        raise AutomationJobNotFoundError(job_id)
    job["enabled"] = True
    job["status"] = "idle"
    await sync_cron_resume(request, job.get("cron_job_id"))
    stored = store.upsert_by_key("automation_jobs", "id", job_id, job)
    return enrich_automation_job(stored)


async def delete_automation_job_payload(job_id: str, request: Any) -> dict[str, Any]:
    job = store.get_by_key("automation_jobs", "id", job_id)
    if job is None:
        raise AutomationJobNotFoundError(job_id)
    await sync_cron_delete(request, job.get("cron_job_id"))
    deleted = store.delete_by_key("automation_jobs", "id", job_id)
    return {"deleted": deleted, "id": job_id}


def list_automation_history_payloads() -> list[dict[str, Any]]:
    items = store.list_items("automation_history")
    return [enrich_automation_history(item) for item in items]
