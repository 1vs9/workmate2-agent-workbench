# -*- coding: utf-8 -*-
"""In-process bus that forwards inter-agent (worker) stream lines to subscribers.

Team-mode chat delegates work to worker agents through ``submit_to_agent``
(background ``/console/chat/task``) or, for non-leader agents, synchronous
``chat_with_agent``. Worker SSE lines are published to this bus keyed by the
leader's ``root_session_id`` so the team UI can show live member progress.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict, List, Tuple

# Sentinel published when a background worker run finishes (see chat_task_store).
WORKER_STREAM_DONE_SENTINEL = "__worker_done__"


class WorkerStreamBus:
    """Thread-safe fan-out of worker stream items to async subscribers.

    Items are opaque to the bus. The team stream publishes
    ``(worker_agent_id, raw_sse_line)`` tuples so that, across multi-level
    delegation, each agent's events can be attributed to the correct agent.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: Dict[
            str,
            List[Tuple["asyncio.Queue[Any]", asyncio.AbstractEventLoop]],
        ] = {}

    def subscribe(self, key: str) -> "asyncio.Queue[Any]":
        """Register a subscriber for *key* and return its queue.

        Must be called from within a running event loop (the team stream).
        """
        if not key:
            raise ValueError("worker stream bus key is required")
        loop = asyncio.get_running_loop()
        queue: "asyncio.Queue[Any]" = asyncio.Queue()
        with self._lock:
            self._subscribers.setdefault(key, []).append((queue, loop))
        return queue

    def unsubscribe(self, key: str, queue: "asyncio.Queue[Any]") -> None:
        with self._lock:
            entries = self._subscribers.get(key)
            if not entries:
                return
            remaining = [(q, lp) for (q, lp) in entries if q is not queue]
            if remaining:
                self._subscribers[key] = remaining
            else:
                self._subscribers.pop(key, None)
        # Drain the removed queue so any already-enqueued items don't leak.
        while not queue.empty():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def has_subscribers(self, key: str) -> bool:
        if not key:
            return False
        with self._lock:
            return bool(self._subscribers.get(key))

    def publish(self, key: str, item: Any) -> None:
        """Deliver *item* to all subscribers of *key* (safe from any thread)."""
        if not key or not item:
            return
        with self._lock:
            entries = list(self._subscribers.get(key, ()))
        for queue, loop in entries:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, item)
            except RuntimeError:
                # Subscriber's loop is gone; drop silently.
                continue


# Process-wide singleton.
worker_stream_bus = WorkerStreamBus()
