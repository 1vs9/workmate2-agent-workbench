# -*- coding: utf-8 -*-
"""AgentDesk API request/response models (demo-plat compatible)."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    task_id: str
    message: str = ""
    reconnect: bool = False
    mode: Literal["single", "team"] = "single"
    chat_mode: Literal["chat", "plan"] = "chat"
    intent: Literal["normal", "skill_create"] = "normal"
    wizard_action: Optional[
        Literal["start", "answer", "dialogue", "revise", "confirm", "cancel"]
    ] = None
    wizard_payload: dict = Field(default_factory=dict)
    choice_payload: dict = Field(default_factory=dict)
    employee_name: Optional[str] = None
    team_id: Optional[str] = None
    team_name: Optional[str] = None
    team_member: Optional[str] = None
    skill_names: list[str] = Field(default_factory=list)
    plan_auto_continue: bool = False


class ApprovalRequest(BaseModel):
    approved: bool = True
