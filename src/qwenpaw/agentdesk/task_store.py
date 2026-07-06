# -*- coding: utf-8 -*-
"""In-memory AgentDesk task message history (Phase 1)."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import suppress
from copy import deepcopy
from typing import Any, Awaitable, Callable

from .message_projection import (
    assistant_messages_by_sender,
    messages_for_client,
    streaming_member_assistant_messages,
)
from .session_history import read_agentdesk_session_messages
from .store import AgentDeskStore, store
from .task_transcript_cache import TaskTranscriptCache
from .team_timeline import merge_stream_text_delta

logger = logging.getLogger(__name__)

_STREAM_PERSIST_DEBOUNCE_S = 0.25
_TIMELINE_PERSIST_DEBOUNCE_S = 0.25


class TaskStore:
    """Per-task_id message list for ``done.messages`` payloads."""

    def __init__(
        self,
        persistent_store: AgentDeskStore | None = None,
        *,
        session_history_reader: Callable[[str], Awaitable[list[dict[str, Any]]]]
        | None = None,
    ) -> None:
        self._lock = asyncio.Lock()
        self._write_locks: dict[str, asyncio.Lock] = {}
        self._messages: dict[str, list[dict[str, Any]]] = {}
        self._team_timeline: dict[str, list[dict[str, Any]]] = {}
        self._streaming: dict[str, dict[str, Any]] = {}
        self._stream_persist_tasks: dict[str, asyncio.Task[None]] = {}
        self._timeline_persist_tasks: dict[str, asyncio.Task[None]] = {}
        self._transcript_cache = TaskTranscriptCache(persistent_store or store)
        self._session_history_reader = (
            session_history_reader or read_agentdesk_session_messages
        )

    async def _ordered_write_lock(self, task_id: str) -> asyncio.Lock:
        async with self._lock:
            lock = self._write_locks.get(task_id)
            if lock is None:
                lock = asyncio.Lock()
                self._write_locks[task_id] = lock
            return lock

    async def _flush_messages_to_disk(self, task_id: str) -> None:
        async with self._lock:
            messages = self._messages.get(task_id)
            if messages is None:
                return
            snapshot = deepcopy(messages)
        # store.json can be large; serializing + rewriting it must never run on
        # the event loop or it freezes SSE streaming (send lag / "stuck at
        # 姝ｅ湪鍥炲"). Persist from a worker thread instead.
        await self._transcript_cache.replace_messages(task_id, snapshot)

    def _schedule_stream_persist(self, task_id: str) -> None:
        existing = self._stream_persist_tasks.get(task_id)
        if existing is not None and not existing.done():
            existing.cancel()

        async def _run() -> None:
            try:
                await asyncio.sleep(_STREAM_PERSIST_DEBOUNCE_S)
                await self._flush_messages_to_disk(task_id)
            except asyncio.CancelledError:
                raise
            finally:
                if self._stream_persist_tasks.get(task_id) is asyncio.current_task():
                    self._stream_persist_tasks.pop(task_id, None)

        self._stream_persist_tasks[task_id] = asyncio.create_task(_run())

    async def _flush_timeline_to_disk(self, task_id: str) -> None:
        async with self._lock:
            timeline = self._team_timeline.get(task_id)
            if timeline is None:
                return
            snapshot = deepcopy(timeline)
        await self._transcript_cache.replace_team_timeline(task_id, snapshot)

    def _schedule_timeline_persist(self, task_id: str) -> None:
        existing = self._timeline_persist_tasks.get(task_id)
        if existing is not None and not existing.done():
            existing.cancel()

        async def _run() -> None:
            try:
                await asyncio.sleep(_TIMELINE_PERSIST_DEBOUNCE_S)
                await self._flush_timeline_to_disk(task_id)
            except asyncio.CancelledError:
                raise
            finally:
                if self._timeline_persist_tasks.get(task_id) is asyncio.current_task():
                    self._timeline_persist_tasks.pop(task_id, None)

        self._timeline_persist_tasks[task_id] = asyncio.create_task(_run())

    async def flush_team_timeline(self, task_id: str) -> None:
        """Persist any debounced team timeline writes before terminal snapshots."""
        task = self._timeline_persist_tasks.pop(task_id, None)
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await self._flush_timeline_to_disk(task_id)

    @staticmethod
    def _try_coalesce_timeline_entry(
        timeline: list[dict[str, Any]],
        entry: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        """Merge streaming deltas / repeated phase rows into the tail when safe."""
        if not timeline:
            return False, deepcopy(entry)
        tail = timeline[-1]
        if entry.get("delta") and entry.get("kind") in {"leader_text", "worker_text"}:
            if (
                tail.get("kind") == entry.get("kind")
                and tail.get("actor") == entry.get("actor")
                and tail.get("delta")
            ):
                prev_text = str(tail.get("text") or "")
                next_text = str(entry.get("text") or "")
                tail["text"] = merge_stream_text_delta(prev_text, next_text)
                tail["ts"] = entry.get("ts", tail.get("ts"))
                return True, deepcopy(tail)
        if (
            entry.get("kind") == "phase"
            and entry.get("phase") == "worker_status"
            and tail.get("kind") == "phase"
            and tail.get("phase") == "worker_status"
            and tail.get("target") == entry.get("target")
        ):
            tail["label"] = entry.get("label") or tail.get("label")
            tail["ts"] = entry.get("ts", tail.get("ts"))
            return True, deepcopy(tail)
        if (
            entry.get("kind") == "phase"
            and entry.get("phase") == "round_progress"
            and tail.get("kind") == "phase"
            and tail.get("phase") == "round_progress"
        ):
            tail["label"] = merge_stream_text_delta(
                str(tail.get("label") or ""),
                str(entry.get("label") or ""),
            )
            tail["ts"] = entry.get("ts", tail.get("ts"))
            return True, deepcopy(tail)
        if (
            entry.get("kind") == "phase"
            and tail.get("kind") == "phase"
            and not entry.get("target")
            and not tail.get("target")
            and entry.get("phase") in {
                "planning",
                "waiting_workers",
                "synthesizing",
                "worker_timeout",
            }
            and tail.get("phase") == entry.get("phase")
        ):
            tail["label"] = merge_stream_text_delta(
                str(tail.get("label") or ""),
                str(entry.get("label") or ""),
            )
            tail["ts"] = entry.get("ts", tail.get("ts"))
            return True, deepcopy(tail)
        return False, deepcopy(entry)

    async def _cancel_stream_persist(self, task_id: str) -> None:
        task = self._stream_persist_tasks.pop(task_id, None)
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    def _restore_streaming_pointer_locked(self, task_id: str) -> None:
        """Re-bind in-memory streaming assistant after reload or client disconnect."""
        if task_id in self._streaming:
            return
        messages = self._messages.get(task_id, [])
        for idx in range(len(messages) - 1, -1, -1):
            msg = messages[idx]
            if msg.get("role") == "assistant" and msg.get("streaming"):
                self._streaming[task_id] = msg
                return

    async def ensure_task(self, task_id: str, *, title: str | None = None) -> None:
        async with self._lock:
            if task_id not in self._messages:
                task = await self._transcript_cache.load_task(task_id)
                self._messages[task_id] = list((task or {}).get("messages", []))
                timeline = (task or {}).get("teamTimeline")
                if isinstance(timeline, list):
                    self._team_timeline[task_id] = list(timeline)
            self._restore_streaming_pointer_locked(task_id)
            await self._transcript_cache.ensure_task(task_id, title=title)

    async def resume_streaming_assistant(self, task_id: str) -> dict[str, Any] | None:
        """Mark the tail assistant message as streaming again for SSE reconnect."""
        async with self._lock:
            messages = self._messages.setdefault(task_id, [])
            for idx in range(len(messages) - 1, -1, -1):
                msg = messages[idx]
                if msg.get("role") != "assistant":
                    continue
                msg["streaming"] = True
                msg["updatedAt"] = time.time()
                self._streaming[task_id] = msg
                await self._transcript_cache.replace_messages(task_id, messages)
                return msg
        return None

    async def append_user_message(
        self,
        task_id: str,
        content: str,
        *,
        sender: str | None = None,
    ) -> dict[str, Any]:
        msg = {
            "id": uuid.uuid4().hex,
            "role": "user",
            "content": content,
            "sender": sender,
            "artifacts": [],
            "streaming": False,
            "updatedAt": time.time(),
        }
        async with self._lock:
            self._messages.setdefault(task_id, []).append(msg)
        self._schedule_stream_persist(task_id)
        return msg

    async def begin_assistant_message(
        self,
        task_id: str,
        *,
        sender: str,
        set_streaming: bool = True,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new assistant message.

        When ``set_streaming`` is False the message is created but the per-task
        streaming pointer is left untouched. This is essential for parallel team
        delegation: each worker gets its OWN message that callers address by
        ``message_id``, so concurrent worker replies never collapse onto a single
        bubble (which happens if every worker hijacks the single streaming
        pointer).

        Optional ``session_id`` tags team member bubbles with their stable native
        session key (``{task_id}:team:member:{name}``) for reload / convergence.
        """
        msg = {
            "id": uuid.uuid4().hex,
            "role": "assistant",
            "content": "",
            "sender": sender,
            "artifacts": [],
            "streaming": True,
            "updatedAt": time.time(),
        }
        if session_id:
            msg["sessionId"] = session_id
        async with self._lock:
            self._messages.setdefault(task_id, []).append(msg)
            if set_streaming:
                self._streaming[task_id] = msg
        self._schedule_stream_persist(task_id)
        return msg

    async def current_assistant_message_id(self, task_id: str) -> str | None:
        async with self._lock:
            msg = self._streaming.get(task_id)
            if msg is None:
                return None
            return str(msg.get("id") or "") or None

    async def bind_streaming_assistant(
        self,
        task_id: str,
        message_id: str | None,
    ) -> bool:
        """Bind the streaming pointer to an existing assistant message."""
        target_id = str(message_id or "").strip()
        if not target_id:
            return False
        async with self._lock:
            messages = self._messages.get(task_id, [])
            for msg in messages:
                if (
                    msg.get("role") == "assistant"
                    and str(msg.get("id") or "") == target_id
                ):
                    msg["streaming"] = True
                    msg["updatedAt"] = time.time()
                    self._streaming[task_id] = msg
                    await self._transcript_cache.replace_messages(task_id, messages)
                    return True
        return False

    def _resolve_assistant_write_target(
        self,
        task_id: str,
        message_id: str | None = None,
    ) -> dict[str, Any] | None:
        if message_id:
            target_id = str(message_id).strip()
            for msg in self._messages.get(task_id, []):
                if (
                    msg.get("role") == "assistant"
                    and str(msg.get("id") or "") == target_id
                ):
                    return msg
            return None
        msg = self._streaming.get(task_id)
        if msg is not None:
            return msg
        messages = self._messages.get(task_id, [])
        for idx in range(len(messages) - 1, -1, -1):
            if messages[idx].get("role") == "assistant":
                return messages[idx]
        return None

    @staticmethod
    def _prefer_assistant_content(
        existing: str,
        incoming: str | None,
    ) -> str:
        if incoming is None:
            return existing
        if len(incoming) >= len(existing):
            return incoming
        return existing

    async def reset_assistant_content(
        self,
        task_id: str,
        *,
        message_id: str | None = None,
    ) -> None:
        write_lock = await self._ordered_write_lock(task_id)
        async with write_lock:
            async with self._lock:
                msg = self._resolve_assistant_write_target(task_id, message_id)
                if msg is None:
                    return
                msg["content"] = ""
                msg["updatedAt"] = time.time()
            self._schedule_stream_persist(task_id)

    async def append_assistant_delta(
        self,
        task_id: str,
        delta: str,
        *,
        message_id: str | None = None,
    ) -> None:
        if not delta:
            return
        write_lock = await self._ordered_write_lock(task_id)
        async with write_lock:
            async with self._lock:
                explicit_id = str(message_id or "").strip() or None
                msg = self._resolve_assistant_write_target(task_id, explicit_id)
                if msg is None and explicit_id:
                    logger.warning(
                        "append_assistant_delta: message_id %s not found for task %s; "
                        "falling back to streaming pointer",
                        explicit_id,
                        task_id,
                    )
                    msg = self._resolve_assistant_write_target(task_id, None)
                if msg is None:
                    if explicit_id:
                        logger.warning(
                            "append_assistant_delta: dropping delta for task %s "
                            "(message_id=%s, no write target)",
                            task_id,
                            explicit_id,
                        )
                    return
                msg["content"] = f"{msg.get('content') or ''}{delta}"
                msg["updatedAt"] = time.time()
            self._schedule_stream_persist(task_id)

    async def finalize_all_streaming_assistant_messages(self, task_id: str) -> None:
        """Finalize every assistant message still marked ``streaming`` for *task_id*."""
        async with self._lock:
            message_ids = [
                str(msg.get("id") or "")
                for msg in self._messages.get(task_id, [])
                if msg.get("role") == "assistant"
                and msg.get("streaming")
                and msg.get("id")
            ]
        for message_id in message_ids:
            await self.finalize_assistant_message(task_id, message_id=message_id)

    async def finalize_assistant_message(
        self,
        task_id: str,
        *,
        message_id: str | None = None,
        content: str | None = None,
    ) -> None:
        await self._cancel_stream_persist(task_id)
        async with self._lock:
            if message_id:
                msg = self._resolve_assistant_write_target(task_id, message_id)
            else:
                msg = self._streaming.pop(task_id, None)
                if msg is None:
                    msg = self._resolve_assistant_write_target(task_id)
            if msg is None:
                return
            if content is not None:
                msg["content"] = self._prefer_assistant_content(
                    str(msg.get("content") or ""),
                    content,
                )
            msg["streaming"] = False
            msg["updatedAt"] = time.time()
            # If we just finalized whatever the streaming pointer referenced,
            # clear it so later fallback writes don't reopen a closed bubble.
            if self._streaming.get(task_id) is msg:
                self._streaming.pop(task_id, None)
            messages_snapshot = self._messages.get(task_id, [])
        await self._transcript_cache.replace_messages(task_id, messages_snapshot)

    async def append_assistant_artifacts(
        self,
        task_id: str,
        artifacts: list[dict[str, Any]],
        *,
        message_id: str | None = None,
    ) -> None:
        """Merge product/change artifacts onto the active assistant message."""
        if not artifacts:
            return
        await self._cancel_stream_persist(task_id)
        async with self._lock:
            if message_id:
                msg = self._resolve_assistant_write_target(task_id, message_id)
            else:
                msg = self._streaming.get(task_id)
                if msg is None:
                    msg = self._resolve_assistant_write_target(task_id)
            if msg is None:
                return
            existing = list(msg.get("artifacts") or [])
            seen = {
                str(item.get("path") or "").lower()
                for item in existing
                if isinstance(item, dict)
            }
            for item in artifacts:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("path") or "").strip()
                key = path.lower()
                if not path or key in seen:
                    continue
                seen.add(key)
                existing.append(item)
            msg["artifacts"] = existing
            msg["updatedAt"] = time.time()
            messages_snapshot = self._messages.get(task_id, [])
        await self._transcript_cache.replace_messages(task_id, messages_snapshot)

    async def get_messages(self, task_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            messages = list(self._messages.get(task_id, []))
        if messages:
            return messages_for_client(messages)
        return await self._session_history_reader(task_id)

    async def streaming_member_assistant_messages(
        self,
        task_id: str,
        *,
        leader_sender: str,
    ) -> list[dict[str, Any]]:
        """Assistant bubbles for roster members still marked ``streaming``."""
        async with self._lock:
            messages = list(self._messages.get(task_id, []))
        return streaming_member_assistant_messages(
            messages,
            leader_sender=leader_sender,
        )

    async def get_assistant_messages_by_sender(
        self,
        task_id: str,
        sender: str,
    ) -> list[dict[str, Any]]:
        """All assistant messages attributed to *sender* (member tab reads)."""
        async with self._lock:
            messages = list(self._messages.get(task_id, []))
        return assistant_messages_by_sender(messages, sender)

    async def get_team_timeline(self, task_id: str) -> list[dict[str, Any]]:
        async with self._lock:
            cached = self._team_timeline.get(task_id)
            if cached is not None:
                return deepcopy(cached)
        timeline = await self._transcript_cache.get_team_timeline(task_id)
        async with self._lock:
            self._team_timeline[task_id] = list(timeline)
        return deepcopy(timeline)

    async def append_team_timeline_entry(
        self,
        task_id: str,
        entry: dict[str, Any],
    ) -> dict[str, Any]:
        async with self._lock:
            timeline = self._team_timeline.setdefault(task_id, [])
            merged, payload = self._try_coalesce_timeline_entry(timeline, entry)
            if not merged:
                # Writers reset seq each round; assign a task-global monotonic seq
                # so multi-round timelines sort chronologically in the UI.
                payload["seq"] = len(timeline)
                timeline.append(payload)
            result = deepcopy(payload)
        self._schedule_timeline_persist(task_id)
        return result

    async def remove_task(self, task_id: str) -> None:
        """Drop in-memory messages and cancel pending stream persistence."""
        await self._cancel_stream_persist(task_id)
        task = self._timeline_persist_tasks.pop(task_id, None)
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        async with self._lock:
            self._messages.pop(task_id, None)
            self._team_timeline.pop(task_id, None)
            self._streaming.pop(task_id, None)


task_store = TaskStore()
