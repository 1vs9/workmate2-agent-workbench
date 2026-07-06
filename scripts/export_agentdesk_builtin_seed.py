#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export a live AgentDesk store.json into the packaged builtin_agents.json catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

_CATALOG_FIELDS = (
    "builtin_id",
    "name",
    "tags",
    "desc",
    "author",
    "usage",
    "skills",
    "tools",
    "mcp",
    "kind",
    "team_id",
    "auto_join",
)
_TEAM_FIELDS = ("id", "name", "desc", "tags", "members", "skills", "usage", "builtin_id")


def _load_store(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid store format: {path}")
    return data


def _plaza_entry(item: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {}
    for key in _CATALOG_FIELDS:
        if key in item and item[key] not in (None, "", []):
            entry[key] = item[key]
    if "auto_join" not in entry:
        entry["auto_join"] = not str(item.get("kind") or "").strip().lower() == "team"
    return entry


def _team_entry(item: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {}
    for key in _TEAM_FIELDS:
        if key in item and item[key] not in (None, "", []):
            entry[key] = item[key]
    if "builtin_id" not in entry:
        entry["builtin_id"] = entry.get("id", "")
    return entry


def export_catalog(store: dict[str, Any], *, version: int) -> dict[str, Any]:
    plaza = [_plaza_entry(item) for item in store.get("plaza") or [] if item.get("name")]
    teams = [_team_entry(item) for item in store.get("teams") or [] if item.get("id")]
    return {
        "version": version,
        "plaza": plaza,
        "teams": teams,
    }


def _default_store_path() -> Path | None:
    """Resolve live store from AgentDesk paths.json or common defaults."""
    candidates: list[Path] = []
    paths_file = Path.home() / ".agentdesk" / "paths.json"
    if paths_file.is_file():
        try:
            payload = json.loads(paths_file.read_text(encoding="utf-8"))
            working_dir = str(payload.get("working_dir") or "").strip()
            if working_dir:
                candidates.append(Path(working_dir).expanduser() / "agentdesk" / "store.json")
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    candidates.extend(
        [
            Path.home() / "agentdesk" / "agentdesk" / "store.json",
            Path.home() / ".agentdesk" / "agentdesk" / "store.json",
        ],
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def main() -> None:
    default_store = _default_store_path()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store",
        type=Path,
        default=default_store,
        required=default_store is None,
        help="Path to agentdesk/store.json under WORKING_DIR "
        "(defaults to ~/.agentdesk/paths.json working_dir, then ~/agentdesk)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("src/qwenpaw/agentdesk/data/builtin_agents.json"),
        help="Output catalog JSON path",
    )
    parser.add_argument(
        "--version",
        type=int,
        default=None,
        help="Catalog version (defaults to current file version + 1, or 1)",
    )
    args = parser.parse_args()

    store = _load_store(args.store.expanduser().resolve())
    current_version = 0
    if args.out.is_file():
        try:
            current_version = int(json.loads(args.out.read_text(encoding="utf-8")).get("version") or 0)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            current_version = 0
    version = args.version if args.version is not None else max(current_version + 1, 1)

    catalog = export_catalog(store, version=version)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {len(catalog['plaza'])} plaza + {len(catalog['teams'])} team "
        f"entries to {args.out} (version {version})",
    )


if __name__ == "__main__":
    main()
