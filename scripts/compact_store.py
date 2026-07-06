# -*- coding: utf-8 -*-
"""One-time compaction of a bloated agentdesk store.json (no server lock needed)."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qwenpaw.agentdesk.store import (
    AgentDeskStore,
    _atomic_replace_with_retry,
    _compact_tasks_list,
    _slim_task_events,
    _trim_task_events,
)


def compact_store(store_path: Path, *, backup: bool = True) -> None:
    if not store_path.is_file():
        raise SystemExit(f"store not found: {store_path}")

    before = store_path.stat().st_size
    if backup:
        backup_path = store_path.with_suffix(".json.pre-compact.bak")
        if not backup_path.exists():
            print(f"backing up {before / 1024 / 1024:.1f} MB -> {backup_path.name}")
            shutil.copy2(store_path, backup_path)

    t0 = time.perf_counter()
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    tasks = raw.get("tasks", [])
    print(f"loaded {len(tasks)} tasks in {time.perf_counter() - t0:.1f}s")

    _compact_tasks_list(tasks, archive_to=store_path)
    for task in tasks:
        events = task.get("events")
        if isinstance(events, list):
            _trim_task_events(events)
    raw["tasks"] = tasks
    merged = AgentDeskStore._merge_defaults(raw)

    tmp = store_path.with_name(f"{store_path.name}.{uuid.uuid4().hex}.tmp")
    t1 = time.perf_counter()
    tmp.write_text(
        json.dumps(merged, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    _atomic_replace_with_retry(tmp, store_path)
    after = store_path.stat().st_size
    print(
        f"compacted {before / 1024 / 1024:.1f} MB -> {after / 1024 / 1024:.1f} MB "
        f"in {time.perf_counter() - t1:.1f}s",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "store_path",
        nargs="?",
        default="D:/agentdesk/agentdesk/store.json",
        type=Path,
    )
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()
    compact_store(args.store_path, backup=not args.no_backup)


if __name__ == "__main__":
    main()
