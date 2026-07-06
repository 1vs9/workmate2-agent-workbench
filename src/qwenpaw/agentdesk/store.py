# -*- coding: utf-8 -*-
"""Small JSON-backed persistence for AgentDesk-only product data."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from contextlib import contextmanager, suppress
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator

from ..constant import WORKING_DIR

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows
    msvcrt = None

logger = logging.getLogger(__name__)

_REPLACE_MAX_ATTEMPTS = 8
_REPLACE_BASE_DELAY_SECONDS = 0.02
_LOCK_REGION_SIZE = 1
# Trace events are debug telemetry, not conversation content. Cap them per task
# so a long-running task can't bloat the shared store.json into a multi-MB blob
# that has to be re-serialized on every write (which stalls streaming).
_MAX_TASK_EVENTS = 1000
_MAX_TEAM_TIMELINE = 2000
# Keep store.json bounded so create/list/chat do not rewrite a multi-MB blob.
_STORE_COMPACT_BYTES = 5 * 1024 * 1024
_MAX_STORE_TASKS_TOTAL = 400
_MAX_STORE_TASKS_WITH_PAYLOAD = 60
_MAX_EVENT_DETAIL_CHARS = 4096


def _slim_event_for_store(event: dict[str, Any]) -> None:
    """Truncate huge trace payloads so one browser_use step cannot bloat store.json."""
    detail = event.get("detail")
    if isinstance(detail, str) and len(detail) > _MAX_EVENT_DETAIL_CHARS:
        omitted = len(detail) - _MAX_EVENT_DETAIL_CHARS
        event["detail"] = (
            detail[:_MAX_EVENT_DETAIL_CHARS]
            + f"\n… [{omitted} chars truncated for storage]"
        )
    result = event.get("result")
    if isinstance(result, str) and len(result) > _MAX_EVENT_DETAIL_CHARS:
        omitted = len(result) - _MAX_EVENT_DETAIL_CHARS
        event["result"] = (
            result[:_MAX_EVENT_DETAIL_CHARS]
            + f"\n… [{omitted} chars truncated for storage]"
        )


def _slim_task_events(events: list[dict[str, Any]]) -> None:
    for event in events:
        if isinstance(event, dict):
            _slim_event_for_store(event)


# Delegation traces (the leader's submit_to_agent / chat_with_agent calls) are
# what render the leader's bubble in each member conversation. They happen at the
# very START of a team task, so a naive "keep the newest N" trim would drop them
# once a task accumulates lots of worker output. Always preserve them.
_DELEGATION_TOOL_NAMES = frozenset({"submit_to_agent", "chat_with_agent"})


def _is_delegation_event(event: dict[str, Any]) -> bool:
    return str(event.get("tool_name") or "") in _DELEGATION_TOOL_NAMES


def _trim_task_events(events: list[dict[str, Any]]) -> None:
    """Cap ``events`` in place at ``_MAX_TASK_EVENTS`` while keeping every
    delegation trace (regardless of age) so leader bubbles never disappear."""
    _slim_task_events(events)
    if len(events) <= _MAX_TASK_EVENTS:
        return
    keep_idx = {i for i, e in enumerate(events) if _is_delegation_event(e)}
    budget = _MAX_TASK_EVENTS - len(keep_idx)
    if budget > 0:
        for i in range(len(events) - 1, -1, -1):
            if i in keep_idx:
                continue
            keep_idx.add(i)
            budget -= 1
            if budget <= 0:
                break
    events[:] = [events[i] for i in sorted(keep_idx)]


def _trim_team_timeline(entries: list[dict[str, Any]]) -> None:
    if len(entries) <= _MAX_TEAM_TIMELINE:
        return
    entries[:] = entries[-_MAX_TEAM_TIMELINE:]


def _compact_tasks_list(
    tasks: list[dict[str, Any]],
    *,
    pin_task_id: str | None = None,
    archive_to: Path | None = None,
) -> None:
    """Drop cold task payloads so ``store.json`` stays small enough to rewrite quickly."""
    if not tasks:
        return
    tasks.sort(
        key=lambda item: float(
            item.get("updated_at") or item.get("created_at") or 0,
        ),
        reverse=True,
    )
    if len(tasks) > _MAX_STORE_TASKS_TOTAL:
        del tasks[_MAX_STORE_TASKS_TOTAL:]
    for idx, task in enumerate(tasks):
        task_id = str(task.get("id") or "")
        if task_id and task_id == pin_task_id:
            continue
        events = task.get("events")
        if isinstance(events, list):
            _trim_task_events(events)
        timeline = task.get("teamTimeline")
        if isinstance(timeline, list):
            _trim_team_timeline(timeline)
        if idx >= _MAX_STORE_TASKS_WITH_PAYLOAD:
            if archive_to is not None:
                _write_task_archive(archive_to, task)
            task["messages"] = []
            task["events"] = []
            task["teamTimeline"] = []
            task.pop("queue", None)
            task["payloadArchived"] = True
_path_thread_locks: dict[str, threading.RLock] = {}
_path_thread_locks_guard = threading.Lock()


def _thread_lock_for(path: Path) -> threading.RLock:
    """One in-process lock per store path so instances sharing a file serialize."""
    key = str(path.resolve())
    with _path_thread_locks_guard:
        lock = _path_thread_locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _path_thread_locks[key] = lock
        return lock


def _lock_path_for(json_path: Path) -> Path:
    return json_path.with_name(f".{json_path.name}.lock")


@contextmanager
def _cross_process_file_lock(lock_path: Path) -> Iterator[None]:
    """Serialize store.json access across processes (and threads)."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    last_exc: OSError | None = None
    for attempt in range(_REPLACE_MAX_ATTEMPTS):
        try:
            with lock_path.open("a+b") as lock_file:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                elif msvcrt is not None:  # pragma: no cover - exercised on Windows
                    # Do not read the lock region before LK_LOCK: when another
                    # thread/process holds the lock, read() raises PermissionError
                    # instead of blocking.
                    try:
                        if lock_path.stat().st_size == 0:
                            lock_path.write_bytes(b"\0")
                    except OSError:
                        pass
                    lock_file.seek(0)
                    msvcrt.locking(
                        lock_file.fileno(),
                        msvcrt.LK_LOCK,
                        _LOCK_REGION_SIZE,
                    )
                try:
                    yield
                finally:
                    if fcntl is not None:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    elif msvcrt is not None:  # pragma: no cover
                        lock_file.seek(0)
                        msvcrt.locking(
                            lock_file.fileno(),
                            msvcrt.LK_UNLCK,
                            _LOCK_REGION_SIZE,
                        )
            return
        except OSError as exc:
            if not _is_transient_replace_error(exc):
                raise
            last_exc = exc
            if attempt + 1 >= _REPLACE_MAX_ATTEMPTS:
                raise
            time.sleep(_REPLACE_BASE_DELAY_SECONDS * (2**attempt))
    if last_exc is not None:
        raise last_exc


def _is_transient_replace_error(exc: OSError) -> bool:
    winerr = getattr(exc, "winerror", None)
    return exc.errno in {13, 16, 17, 26} or winerr in {5, 32}


def _atomic_replace_with_retry(src: Path, dst: Path) -> None:
    last_exc: OSError | None = None
    for attempt in range(_REPLACE_MAX_ATTEMPTS):
        try:
            src.replace(dst)
            return
        except OSError as exc:
            if not _is_transient_replace_error(exc):
                raise
            last_exc = exc
            if attempt + 1 >= _REPLACE_MAX_ATTEMPTS:
                raise
            delay = _REPLACE_BASE_DELAY_SECONDS * (2**attempt)
            logger.debug(
                "Retrying atomic replace %s -> %s after %s (attempt %s/%s)",
                src,
                dst,
                exc,
                attempt + 1,
                _REPLACE_MAX_ATTEMPTS,
            )
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc


def format_agentdesk_persistence_error(exc: BaseException) -> str | None:
    """Map store I/O failures to a short user-facing message."""
    if isinstance(exc, PermissionError):
        return (
            "保存任务数据时文件被占用，请稍后重试。"
            "如持续出现，请确保只运行一个 QwenPaw 实例。"
        )
    if isinstance(exc, OSError) and _is_transient_replace_error(exc):
        return (
            "保存任务数据时文件被占用，请稍后重试。"
            "如持续出现，请确保只运行一个 QwenPaw 实例。"
        )
    return None


def format_agentdesk_stream_error(
    exc: BaseException,
    *,
    default: str,
) -> str:
    """Map stream failures to a short user-facing message."""
    persistence = format_agentdesk_persistence_error(exc)
    if persistence:
        return persistence
    detail = str(exc).strip()
    if detail:
        return f"{default.rstrip('。')}：{detail}"
    return default


def _now() -> float:
    return time.time()


def _task_archive_path(store_path: Path, task_id: str) -> Path:
    return store_path.parent / "task_archives" / f"{task_id}.json"


def _write_task_archive(store_path: Path, task: dict[str, Any]) -> None:
    """Persist cold task transcript to per-task JSON before stripping from store.json."""
    task_id = str(task.get("id") or "").strip()
    if not task_id:
        return
    messages = task.get("messages")
    events = task.get("events")
    timeline = task.get("teamTimeline")
    if not (
        (isinstance(messages, list) and messages)
        or (isinstance(events, list) and events)
        or (isinstance(timeline, list) and timeline)
    ):
        return
    archive_path = _task_archive_path(store_path, task_id)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": task_id,
        "messages": deepcopy(messages) if isinstance(messages, list) else [],
        "events": deepcopy(events) if isinstance(events, list) else [],
        "teamTimeline": deepcopy(timeline) if isinstance(timeline, list) else [],
        "queue": deepcopy(task.get("queue")) if isinstance(task.get("queue"), list) else [],
        "archived_at": _now(),
    }
    tmp = archive_path.with_name(f"{archive_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        _atomic_replace_with_retry(tmp, archive_path)
    finally:
        if tmp.exists():
            with suppress(OSError):
                tmp.unlink()


def _read_task_archive(store_path: Path, task_id: str) -> dict[str, Any] | None:
    archive_path = _task_archive_path(store_path, task_id)
    if not archive_path.is_file():
        return None
    try:
        data = json.loads(archive_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _hydrate_task_record(store_path: Path, task: dict[str, Any]) -> dict[str, Any]:
    """Merge archived transcript back when loading a compacted task."""
    task_id = str(task.get("id") or "").strip()
    if not task_id:
        return task
    if task.get("messages") or task.get("events") or task.get("teamTimeline"):
        if not task.get("payloadArchived"):
            return task
    archived = _read_task_archive(store_path, task_id)
    if archived is None:
        return task
    merged = dict(task)
    if not merged.get("messages") and archived.get("messages"):
        merged["messages"] = archived["messages"]
    if not merged.get("events") and archived.get("events"):
        merged["events"] = archived["events"]
    if not merged.get("teamTimeline") and archived.get("teamTimeline"):
        merged["teamTimeline"] = archived["teamTimeline"]
    if not merged.get("queue") and archived.get("queue"):
        merged["queue"] = archived["queue"]
    return merged


class AgentDeskStore:
    """Persist AgentDesk metadata that has no native QwenPaw equivalent yet."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (WORKING_DIR / "agentdesk" / "store.json")

    @property
    def _lock(self) -> threading.RLock:
        return _thread_lock_for(self.path)

    @contextmanager
    def _exclusive_access(self) -> Iterator[None]:
        """Hold thread + cross-process locks for one read-modify-write cycle."""
        with self._lock:
            with _cross_process_file_lock(_lock_path_for(self.path)):
                yield

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._empty()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty()
        return self._merge_defaults(data)

    def _persist_unlocked(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_text(
                json.dumps(
                    self._merge_defaults(data),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            _atomic_replace_with_retry(tmp, self.path)
        finally:
            if tmp.exists():
                with suppress(OSError):
                    tmp.unlink()

    def _maybe_compact_tasks(
        self,
        data: dict[str, Any],
        *,
        pin_task_id: str | None = None,
    ) -> None:
        try:
            oversized = self.path.is_file() and self.path.stat().st_size > _STORE_COMPACT_BYTES
        except OSError:
            oversized = False
        tasks = data.get("tasks")
        if not isinstance(tasks, list):
            return
        if oversized or len(tasks) > _MAX_STORE_TASKS_WITH_PAYLOAD:
            _compact_tasks_list(tasks, pin_task_id=pin_task_id, archive_to=self.path)

    def read(self) -> dict[str, Any]:
        with self._exclusive_access():
            return deepcopy(self._load_unlocked())

    def write(self, data: dict[str, Any]) -> None:
        with self._exclusive_access():
            self._persist_unlocked(data)

    def list_items(self, collection: str) -> list[dict[str, Any]]:
        with self._exclusive_access():
            return deepcopy(list(self._load_unlocked().get(collection, [])))

    def upsert_by_key(
        self,
        collection: str,
        key: str,
        value: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._exclusive_access():
            data = self._load_unlocked()
            items = list(data.get(collection, []))
            now = _now()
            for idx, item in enumerate(items):
                if str(item.get(key)) == value:
                    merged = {**item, **payload, key: value, "updated_at": now}
                    items[idx] = merged
                    data[collection] = items
                    self._persist_unlocked(data)
                    return deepcopy(merged)
            created = {**payload, key: value, "created_at": now, "updated_at": now}
            items.append(created)
            data[collection] = items
            self._persist_unlocked(data)
            return deepcopy(created)

    def delete_by_key(self, collection: str, key: str, value: str) -> bool:
        with self._exclusive_access():
            data = self._load_unlocked()
            items = list(data.get(collection, []))
            kept = [item for item in items if str(item.get(key)) != value]
            if len(kept) == len(items):
                return False
            data[collection] = kept
            self._persist_unlocked(data)
            return True

    def get_by_key(
        self,
        collection: str,
        key: str,
        value: str,
    ) -> dict[str, Any] | None:
        with self._exclusive_access():
            for item in self._load_unlocked().get(collection, []):
                if str(item.get(key)) == value:
                    found = deepcopy(item)
                    if collection == "tasks" and key == "id":
                        found = _hydrate_task_record(self.path, found)
                    return found
        return None

    def ensure_task(self, task_id: str, title: str | None = None) -> dict[str, Any]:
        with self._exclusive_access():
            data = self._load_unlocked()
            tasks = list(data.get("tasks", []))
            for item in tasks:
                if str(item.get("id")) == task_id:
                    return deepcopy(_hydrate_task_record(self.path, item))
            now = _now()
            created = {
                "id": task_id,
                "title": title or "新任务",
                "messages": [],
                "events": [],
                "teamTimeline": [],
                "queue": [],
                "runStatus": "idle",
                "created_at": now,
                "updated_at": now,
            }
            tasks.append(created)
            data["tasks"] = tasks
            self._maybe_compact_tasks(data, pin_task_id=task_id)
            self._persist_unlocked(data)
            return deepcopy(created)

    def append_task_message(self, task_id: str, message: dict[str, Any]) -> None:
        with self._exclusive_access():
            data = self._load_unlocked()
            tasks = list(data.get("tasks", []))
            now = _now()
            payload = {
                "id": message.get("id") or uuid.uuid4().hex,
                "artifacts": [],
                "streaming": False,
                "updatedAt": now,
                **message,
            }
            for task in tasks:
                if str(task.get("id")) == task_id:
                    task.setdefault("messages", []).append(payload)
                    task["updated_at"] = now
                    data["tasks"] = tasks
                    self._persist_unlocked(data)
                    return
            created = {
                "id": task_id,
                "title": "新任务",
                "messages": [payload],
                "events": [],
                "teamTimeline": [],
                "queue": [],
                "runStatus": "idle",
                "created_at": now,
                "updated_at": now,
            }
            tasks.append(created)
            data["tasks"] = tasks
            self._maybe_compact_tasks(data, pin_task_id=task_id)
            self._persist_unlocked(data)

    def append_task_event(
        self,
        task_id: str,
        event: dict[str, Any],
        *,
        message_id: str | None = None,
    ) -> None:
        with self._exclusive_access():
            data = self._load_unlocked()
            tasks = list(data.get("tasks", []))
            now = _now()
            payload = {
                **deepcopy(event),
                "created_at": event.get("created_at") or now,
            }
            if message_id:
                payload["message_id"] = message_id
            for task in tasks:
                if str(task.get("id")) == task_id:
                    events = task.setdefault("events", [])
                    events.append(payload)
                    _trim_task_events(events)
                    task["updated_at"] = now
                    data["tasks"] = tasks
                    self._persist_unlocked(data)
                    return
            events = [payload]
            _trim_task_events(events)
            created = {
                "id": task_id,
                "title": "新任务",
                "messages": [],
                "events": events,
                "teamTimeline": [],
                "queue": [],
                "runStatus": "idle",
                "created_at": now,
                "updated_at": now,
            }
            tasks.append(created)
            data["tasks"] = tasks
            self._maybe_compact_tasks(data, pin_task_id=task_id)
            self._persist_unlocked(data)

    def append_team_timeline_entry(
        self,
        task_id: str,
        entry: dict[str, Any],
    ) -> dict[str, Any]:
        with self._exclusive_access():
            data = self._load_unlocked()
            tasks = list(data.get("tasks", []))
            now = _now()
            payload = {
                **deepcopy(entry),
                "created_at": entry.get("created_at") or now,
            }
            for task in tasks:
                if str(task.get("id")) == task_id:
                    timeline = task.setdefault("teamTimeline", [])
                    timeline.append(payload)
                    _trim_team_timeline(timeline)
                    task["updated_at"] = now
                    data["tasks"] = tasks
                    self._persist_unlocked(data)
                    return deepcopy(payload)
            timeline = [payload]
            _trim_team_timeline(timeline)
            created = {
                "id": task_id,
                "title": "新任务",
                "messages": [],
                "events": [],
                "teamTimeline": timeline,
                "queue": [],
                "runStatus": "idle",
                "created_at": now,
                "updated_at": now,
            }
            tasks.append(created)
            data["tasks"] = tasks
            self._maybe_compact_tasks(data, pin_task_id=task_id)
            self._persist_unlocked(data)
            return deepcopy(payload)

    def replace_team_timeline(
        self,
        task_id: str,
        timeline: list[dict[str, Any]],
    ) -> None:
        """Replace the full team timeline for *task_id* (debounced persist path)."""
        with self._exclusive_access():
            data = self._load_unlocked()
            tasks = list(data.get("tasks", []))
            now = _now()
            trimmed = deepcopy(list(timeline))
            _trim_team_timeline(trimmed)
            for task in tasks:
                if str(task.get("id")) == task_id:
                    task["teamTimeline"] = trimmed
                    task["updated_at"] = now
                    data["tasks"] = tasks
                    self._persist_unlocked(data)
                    return
            created = {
                "id": task_id,
                "title": "新任务",
                "messages": [],
                "events": [],
                "teamTimeline": trimmed,
                "queue": [],
                "runStatus": "idle",
                "created_at": now,
                "updated_at": now,
            }
            tasks.append(created)
            data["tasks"] = tasks
            self._maybe_compact_tasks(data, pin_task_id=task_id)
            self._persist_unlocked(data)

    def get_team_timeline(self, task_id: str) -> list[dict[str, Any]]:
        task = self.get_by_key("tasks", "id", task_id) or {}
        timeline = task.get("teamTimeline")
        if not isinstance(timeline, list):
            return []
        return deepcopy(timeline)

    def replace_task_messages(
        self,
        task_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        with self._exclusive_access():
            data = self._load_unlocked()
            tasks = list(data.get("tasks", []))
            now = _now()
            for task in tasks:
                if str(task.get("id")) == task_id:
                    task["messages"] = deepcopy(messages)
                    task["updated_at"] = now
                    task.pop("payloadArchived", None)
                    data["tasks"] = tasks
                    self._persist_unlocked(data)
                    return
            created = {
                "id": task_id,
                "title": "新任务",
                "messages": deepcopy(messages),
                "events": [],
                "teamTimeline": [],
                "queue": [],
                "runStatus": "idle",
                "created_at": now,
                "updated_at": now,
            }
            tasks.append(created)
            data["tasks"] = tasks
            self._maybe_compact_tasks(data, pin_task_id=task_id)
            self._persist_unlocked(data)

    def is_uninitialized(self) -> bool:
        """True when plaza, employees, and teams have never been populated."""
        data = self.read()
        return not any(data.get(key) for key in ("plaza", "employees", "teams"))

    def read_meta(self) -> dict[str, Any]:
        meta = self.read().get("meta")
        return deepcopy(meta) if isinstance(meta, dict) else {}

    def patch_meta(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._exclusive_access():
            data = self._load_unlocked()
            meta = dict(data.get("meta") or {})
            meta.update(patch)
            data["meta"] = meta
            self._persist_unlocked(data)
            return deepcopy(meta)

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "employees": [],
            "plaza": [],
            "teams": [],
            "skills": [],
            "mcp_clients": [],
            "knowledge": [],
            "cases": [],
            "tasks": [],
            "automation_jobs": [],
            "automation_history": [],
            "meta": {},
        }

    @classmethod
    def _merge_defaults(cls, data: dict[str, Any]) -> dict[str, Any]:
        merged = cls._empty()
        for key, value in data.items():
            merged[key] = value
        return merged


store = AgentDeskStore()
