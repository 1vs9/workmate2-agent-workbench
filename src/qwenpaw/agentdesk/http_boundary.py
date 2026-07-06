# -*- coding: utf-8 -*-
"""Small HTTP boundary helpers for AgentDesk routes."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def body_dict(body: dict[str, Any] | None) -> dict[str, Any]:
    """Return a mutable request body mapping."""
    return dict(body or {})


def raise_bad_request(exc: Exception) -> None:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def raise_not_found(exc: Exception, *, detail: Any | None = None) -> None:
    raise HTTPException(
        status_code=404,
        detail=str(exc) if detail is None else detail,
    ) from exc


def raise_conflict(exc: Exception, *, detail: Any | None = None) -> None:
    raise HTTPException(
        status_code=409,
        detail=str(exc) if detail is None else detail,
    ) from exc


def raise_bad_gateway(exc: Exception) -> None:
    raise HTTPException(status_code=502, detail=str(exc)) from exc
