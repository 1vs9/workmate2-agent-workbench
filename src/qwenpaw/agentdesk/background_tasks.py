# -*- coding: utf-8 -*-
"""Shared fire-and-forget task scheduling for AgentDesk async side effects."""

from __future__ import annotations

import asyncio
from typing import Any, Coroutine

_background_tasks: set[asyncio.Task[Any]] = set()


def spawn_background(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    """Schedule *coro* and keep a strong reference until it completes."""

    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
