# -*- coding: utf-8 -*-
"""AgentDesk single/team session routing invariants."""

from __future__ import annotations

from fastapi import HTTPException

from .models import ChatRequest
from .store import store as agentdesk_store

TEAM_SESSION_SWITCH_DETAIL = (
    "当前 session 已是群聊模式。若要和其他 Agent 单聊，请新开一个 session。"
)
SINGLE_SESSION_TO_TEAM_DETAIL = (
    "当前 session 已是单聊模式。若要发起群聊，请新开一个 session。"
)
TEAM_SESSION_CHANGE_DETAIL = (
    "当前 session 已绑定到这个团队。若要切换团队，请新开一个 session。"
)


def coerce_team_routing_from_store(payload: ChatRequest) -> None:
    """Bind every turn to the task's established target.

    Single-chat tasks may switch agents while keeping the same session context.
    Team-chat tasks are bound to their original team and must not become a
    single-agent chat or switch teams inside the same session.
    """
    persisted = agentdesk_store.get_by_key("tasks", "id", payload.task_id)
    if not persisted:
        return
    persisted_team_id = str(persisted.get("team_id") or "").strip()
    persisted_team_name = str(persisted.get("team_name") or "").strip()

    if persisted_team_id or persisted_team_name:
        requested_mode = str(payload.mode or "single").strip() or "single"
        requested_team_id = str(payload.team_id or "").strip()
        requested_team_name = str(payload.team_name or "").strip()
        if requested_mode != "team":
            raise HTTPException(status_code=409, detail=TEAM_SESSION_SWITCH_DETAIL)
        if (
            requested_team_id
            and persisted_team_id
            and requested_team_id != persisted_team_id
        ) or (
            requested_team_name
            and persisted_team_name
            and requested_team_name != persisted_team_name
        ):
            raise HTTPException(status_code=409, detail=TEAM_SESSION_CHANGE_DETAIL)
        payload.mode = "team"
        if not str(payload.team_id or "").strip():
            payload.team_id = persisted_team_id or None
        if not str(payload.team_name or "").strip():
            payload.team_name = persisted_team_name or None
        return

    has_assistant = any(
        str(msg.get("role")) == "assistant"
        for msg in (persisted.get("messages") or [])
    )
    if has_assistant and payload.mode == "team":
        raise HTTPException(status_code=409, detail=SINGLE_SESSION_TO_TEAM_DETAIL)


def apply_chat_routing_to_task(task: dict, payload: ChatRequest) -> dict:
    """Return task metadata updated with this turn's stable routing target."""
    updated = dict(task)
    mode = str(payload.mode or "single").strip() or "single"
    existing_team_id = str(updated.get("team_id") or "").strip()
    existing_team_name = str(updated.get("team_name") or "").strip()

    if mode == "team":
        updated["mode"] = "team"
        updated["team_id"] = str(payload.team_id or "").strip()
        updated["team_name"] = str(payload.team_name or "").strip()
        updated.pop("employee_name", None)
    elif existing_team_id or existing_team_name:
        # Established team tasks keep their team ownership for reconnects and
        # for frontend races that briefly emit a single/default turn.
        updated["mode"] = "team"
    else:
        updated["mode"] = "single"
        updated["employee_name"] = str(payload.employee_name or "").strip()
        updated.pop("team_id", None)
        updated.pop("team_name", None)

    return updated
