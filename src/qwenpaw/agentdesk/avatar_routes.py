# -*- coding: utf-8 -*-
"""AgentDesk avatar endpoint orchestration helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .avatars import (
    avatar_seed,
    ensure_portrait_file,
    generate_portrait_url,
)


def generate_avatar_payload(body: dict[str, Any] | None) -> dict[str, str]:
    payload = dict(body or {})
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    description = str(
        payload.get("description") or payload.get("desc") or ""
    ).strip()
    role = str(payload.get("role") or "employee").strip().lower()
    if role not in {"employee", "team"}:
        role = "employee"
    return {
        "url": generate_portrait_url(name, description, role=role),
        "seed": avatar_seed(name, description, role),
    }


def avatar_file_path(filename: str) -> Path:
    if not filename.endswith(".svg") or len(filename) != 20:
        raise ValueError("Invalid avatar filename")
    return ensure_portrait_file(filename[:16])
