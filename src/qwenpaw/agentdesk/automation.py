# -*- coding: utf-8 -*-
"""AgentDesk scheduled automation jobs — persistence and QwenPaw cron bridge."""

from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime
from typing import Any

from .session_bridge import AGENTDESK_SESSION_CHANNEL, AGENTDESK_SESSION_USER_ID

logger = logging.getLogger(__name__)

_AGENTDESK_USER_ID = AGENTDESK_SESSION_USER_ID
_AGENTDESK_CHANNEL = AGENTDESK_SESSION_CHANNEL


def _now() -> float:
    return time.time()


def _body_dict(body: dict[str, Any] | None) -> dict[str, Any]:
    return dict(body or {})


def _format_timestamp(ts: Any) -> str:
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    if isinstance(ts, str) and ts.strip():
        return ts.strip()
    return ""


def _status_label(status: str | None) -> str:
    labels = {
        "queued": "已排队",
        "running": "运行中",
        "success": "成功",
        "error": "失败",
        "paused": "已暂停",
        "idle": "待运行",
        "skipped": "已跳过",
        "cancelled": "已取消",
    }
    key = str(status or "").strip().lower()
    return labels.get(key, status or "")


def schedule_frequency_label(schedule: dict[str, Any] | None) -> str:
    """Human-readable schedule summary for the automation list UI."""
    if not isinstance(schedule, dict):
        return "未设置"
    mode = str(schedule.get("mode") or "").strip().lower()
    if mode == "once":
        run_at = schedule.get("run_at")
        if run_at:
            try:
                dt = datetime.fromisoformat(str(run_at).replace("Z", "+00:00"))
                return f"单次 {dt.strftime('%m-%d %H:%M')}"
            except ValueError:
                pass
        return "单次"
    if mode == "interval":
        unit = str(schedule.get("interval_unit") or "hours")
        amount = schedule.get("interval_amount") or 1
        if unit == "minutes":
            return f"每 {amount} 分钟"
        return f"每 {amount} 小时"
    cron = str(schedule.get("cron") or "").strip()
    if not cron:
        return "未设置"
    parts = cron.split()
    if len(parts) >= 2:
        minute, hour = parts[0], parts[1]
        if len(parts) >= 5 and parts[2] != "*" and parts[3] != "*":
            return f"单次 {parts[2]}-{parts[3]} {hour}:{minute.zfill(2)}"
        if len(parts) >= 5 and parts[4] in {"1-5", "mon-fri"}:
            return f"工作日 {hour}:{minute.zfill(2)}"
        if len(parts) >= 5 and parts[4] == "1":
            return f"每周一 {hour}:{minute.zfill(2)}"
        if hour.startswith("*/"):
            return f"每 {hour[2:]} 小时"
        if minute.startswith("*/"):
            return f"每 {minute[2:]} 分钟"
        if hour == "*" and minute.startswith("*/"):
            return f"每 {minute[2:]} 分钟"
        if re.fullmatch(r"\d+", hour) and re.fullmatch(r"\d+", minute):
            return f"每天 {hour.zfill(2)}:{minute.zfill(2)}"
    return cron


def schedule_eta_label(schedule: dict[str, Any] | None) -> str:
    if not isinstance(schedule, dict):
        return ""
    mode = str(schedule.get("mode") or "").strip().lower()
    if mode == "once":
        run_at = schedule.get("run_at")
        if run_at:
            try:
                dt = datetime.fromisoformat(str(run_at).replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                return str(run_at)
    cron = str(schedule.get("cron") or "").strip()
    parts = cron.split()
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"下次约 {parts[1].zfill(2)}:{parts[0].zfill(2)}"
    return ""


def normalize_schedule(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    schedule = dict(raw)
    schedule.setdefault("timezone", "Asia/Shanghai")
    mode = str(schedule.get("mode") or "").strip().lower()
    schedule_type = str(schedule.get("type") or "cron").strip().lower()
    if mode == "once" or schedule_type == "once":
        run_at = schedule.get("run_at")
        if run_at:
            schedule["type"] = "once"
            schedule["mode"] = "once"
            schedule.pop("cron", None)
            return schedule
    schedule.setdefault("type", "cron")
    if mode:
        schedule["mode"] = mode
    return schedule


def normalize_date_range(raw: Any) -> dict[str, str | None]:
    if not isinstance(raw, dict):
        return {"start": None, "end": None}
    start = raw.get("start")
    end = raw.get("end")
    return {
        "start": str(start).strip() if start else None,
        "end": str(end).strip() if end else None,
    }


def build_automation_job(job_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = _body_dict(body)
    schedule = normalize_schedule(payload.get("schedule"))
    date_range = normalize_date_range(payload.get("date_range"))
    skill_names_raw = payload.get("skill_names") or []
    skill_names = (
        [str(name).strip() for name in skill_names_raw if str(name).strip()]
        if isinstance(skill_names_raw, list)
        else []
    )
    task_id = str(payload.get("task_id") or uuid.uuid4().hex)
    name = str(payload.get("name") or "Automation").strip() or "Automation"
    model_name = payload.get("model_name")
    if model_name is not None:
        model_name = str(model_name).strip() or None
    return {
        "id": job_id,
        "task_id": task_id,
        "name": name,
        "workspace": str(payload.get("workspace") or "default").strip() or "default",
        "prompt": str(payload.get("prompt") or ""),
        "employee_name": payload.get("employee_name"),
        "model_name": model_name,
        "skill_names": skill_names,
        "chat_mode": str(payload.get("chat_mode") or "chat"),
        "schedule": schedule,
        "date_range": date_range,
        "enabled": payload.get("enabled", True),
        "status": payload.get("status", "idle"),
        "cron_job_id": payload.get("cron_job_id"),
        "created_at": payload.get("created_at", _now()),
        "updated_at": _now(),
    }


def enrich_automation_job(job: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(job)
    schedule = job.get("schedule") if isinstance(job.get("schedule"), dict) else {}
    enriched["frequency"] = schedule_frequency_label(schedule)
    enriched["eta"] = schedule_eta_label(schedule)
    return enriched


def enrich_automation_history(item: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(item)
    enriched["time"] = _format_timestamp(item.get("time"))
    enriched["status"] = _status_label(item.get("status"))
    return enriched


def build_history_record(job: dict[str, Any], *, status: str = "queued") -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "job_id": job.get("id", ""),
        "task_id": job.get("task_id", ""),
        "name": job.get("name", ""),
        "workspace": job.get("workspace", "default"),
        "status": status,
        "time": _now(),
    }


def _parse_run_at(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def build_cron_job_spec(job: dict[str, Any], *, agent_id: str) -> Any:
    from ..app.crons.models import (
        CronJobRequest,
        CronJobSpec,
        DispatchSpec,
        DispatchTarget,
        ScheduleSpec,
    )

    schedule_raw = job.get("schedule") if isinstance(job.get("schedule"), dict) else {}
    timezone = str(schedule_raw.get("timezone") or "Asia/Shanghai")
    mode = str(schedule_raw.get("mode") or "").strip().lower()
    schedule_type = str(schedule_raw.get("type") or "cron").strip().lower()
    task_id = str(job.get("task_id") or uuid.uuid4().hex)

    if schedule_type == "once" or mode == "once":
        run_at = _parse_run_at(schedule_raw.get("run_at"))
        if run_at is None:
            raise ValueError("once schedule requires run_at")
        schedule = ScheduleSpec(type="once", run_at=run_at, timezone=timezone)
    else:
        cron = str(schedule_raw.get("cron") or "0 9 * * *").strip()
        schedule = ScheduleSpec(type="cron", cron=cron, timezone=timezone)

    return CronJobSpec(
        id=job.get("cron_job_id") or None,
        name=str(job.get("name") or "Automation"),
        enabled=bool(job.get("enabled", True)),
        schedule=schedule,
        task_type="agent",
        request=CronJobRequest(
            input=str(job.get("prompt") or ""),
            user_id=_AGENTDESK_USER_ID,
            session_id=task_id,
        ),
        dispatch=DispatchSpec(
            channel=_AGENTDESK_CHANNEL,
            target=DispatchTarget(user_id=_AGENTDESK_USER_ID, session_id=task_id),
            meta={"agent_id": agent_id},
        ),
        meta={
            "agentdesk_job_id": job.get("id"),
            "workspace": job.get("workspace"),
            "agent_id": agent_id,
            "model_name": job.get("model_name"),
            "skill_names": job.get("skill_names") or [],
            "chat_mode": job.get("chat_mode"),
            "date_range": job.get("date_range") or {},
        },
    )


async def get_cron_manager(request: Any) -> Any | None:
    try:
        from ..app.agent_context import get_agent_for_request

        workspace = await get_agent_for_request(request)
        return workspace.cron_manager
    except Exception:  # noqa: BLE001 - optional bridge when agent context unavailable
        return None


async def sync_cron_upsert(request: Any, job: dict[str, Any], *, agent_id: str) -> str | None:
    mgr = await get_cron_manager(request)
    if mgr is None:
        return job.get("cron_job_id")
    try:
        spec = build_cron_job_spec(job, agent_id=agent_id)
    except ValueError as exc:
        logger.warning("skip cron sync for agentdesk job %s: %s", job.get("id"), exc)
        return job.get("cron_job_id")
    try:
        if job.get("cron_job_id"):
            spec = spec.model_copy(update={"id": job["cron_job_id"]})
            await mgr.create_or_replace_job(spec)
            return str(spec.id)
        created = spec.model_copy(update={"id": uuid.uuid4().hex})
        await mgr.create_or_replace_job(created)
        return str(created.id)
    except Exception:  # noqa: BLE001
        logger.exception("failed to sync agentdesk automation job %s to cron", job.get("id"))
        return job.get("cron_job_id")


async def sync_cron_delete(request: Any, cron_job_id: str | None) -> None:
    if not cron_job_id:
        return
    mgr = await get_cron_manager(request)
    if mgr is None:
        return
    try:
        await mgr.delete_job(cron_job_id)
    except Exception:  # noqa: BLE001
        logger.exception("failed to delete cron job %s", cron_job_id)


async def sync_cron_pause(request: Any, cron_job_id: str | None) -> None:
    if not cron_job_id:
        return
    mgr = await get_cron_manager(request)
    if mgr is None:
        return
    try:
        await mgr.pause_job(cron_job_id)
    except Exception:  # noqa: BLE001
        logger.exception("failed to pause cron job %s", cron_job_id)


async def sync_cron_resume(request: Any, cron_job_id: str | None) -> None:
    if not cron_job_id:
        return
    mgr = await get_cron_manager(request)
    if mgr is None:
        return
    try:
        await mgr.resume_job(cron_job_id)
    except Exception:  # noqa: BLE001
        logger.exception("failed to resume cron job %s", cron_job_id)


async def sync_cron_run(request: Any, cron_job_id: str | None) -> bool:
    if not cron_job_id:
        return False
    mgr = await get_cron_manager(request)
    if mgr is None:
        return False
    try:
        await mgr.run_job(cron_job_id)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("failed to run cron job %s", cron_job_id)
        return False
