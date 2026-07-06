# -*- coding: utf-8 -*-
"""SSE helpers for AgentDesk-compatible responses."""

from __future__ import annotations

import json
from typing import Any


def sse_line(payload: dict[str, Any]) -> str:
    """Format a dict as one Server-Sent Events ``data:`` line."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
