# -*- coding: utf-8 -*-
"""Trusted AgentDesk task workspace file resolution."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from .agent_workspace import (
    agent_workspace_dir as _agent_workspace_dir,
    resolve_active_agentdesk_agent_id,
)
from .agents import resolve_agent_id
from .store import store
from .task_workspace_sync import sync_task_workspace


def normalize_artifact_path(path: str) -> str:
    raw = str(path or "").replace("\\", "/").strip()
    if not raw:
        return raw
    # Git Bash / MSYS style: /c/Users/foo -> C:/Users/foo
    if len(raw) >= 3 and raw[0] == "/" and raw[2] == "/":
        drive = raw[1]
        if drive.isalpha():
            raw = f"{drive.upper()}:{raw[2:]}"
    lower = raw.lower()
    if lower.startswith("backend/data/skills/"):
        return f"skills/{raw[len('backend/data/skills/'):]}"
    marker = "/data/skills/"
    idx = lower.find(marker)
    if idx >= 0:
        return f"skills/{raw[idx + len(marker):]}"
    if lower.startswith("data/skills/"):
        return f"skills/{raw[len('data/skills/'):]}"
    return raw


def task_agent_id(task_id: str) -> str:
    task = store.get_by_key("tasks", "id", task_id) or {}
    agent_id = str(task.get("agent_id") or "").strip()
    if agent_id:
        return agent_id
    employee_name = str(task.get("employee_name") or "").strip()
    if employee_name:
        return resolve_agent_id(employee_name)
    return resolve_active_agentdesk_agent_id()


def _same_resolved_path(left: Path, right: Path) -> bool:
    try:
        return left.expanduser().resolve() == right.expanduser().resolve()
    except OSError:
        return False


def trusted_task_workspace_dirs(task_id: str, task: dict) -> list[Path]:
    """Workspace roots derived from server-side agent/team configuration."""

    roots: list[Path] = []
    seen: set[str] = set()

    def add(path: Path | None) -> None:
        if path is None:
            return
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            return
        key = str(resolved).lower()
        if key in seen:
            return
        seen.add(key)
        roots.append(resolved)

    agent_id = str(task.get("agent_id") or "").strip()
    if agent_id:
        try:
            add(_agent_workspace_dir(agent_id))
        except HTTPException:
            pass

    employee_name = str(task.get("employee_name") or "").strip()
    if employee_name:
        try:
            add(_agent_workspace_dir(resolve_agent_id(employee_name)))
        except Exception:  # noqa: BLE001 - user-edited metadata may be stale
            pass

    team_id = str(task.get("team_id") or "").strip()
    if team_id:
        team = store.get_by_key("teams", "id", team_id) or {}
        leader_id = str(team.get("leader_agent_id") or "").strip()
        if leader_id:
            try:
                add(_agent_workspace_dir(leader_id))
            except HTTPException:
                pass
        from .employee_agents import ensure_employee_agent_profile

        members = team.get("members") or []
        if isinstance(members, list):
            for member_name in members:
                name = str(member_name or "").strip()
                if not name:
                    continue
                try:
                    member_agent_id = ensure_employee_agent_profile(name)
                    if member_agent_id:
                        add(_agent_workspace_dir(member_agent_id))
                except Exception:  # noqa: BLE001 - ignore stale team members
                    pass

    if not roots:
        try:
            add(_agent_workspace_dir(task_agent_id(task_id)))
        except HTTPException:
            pass

    return roots


def task_workspace_root(
    task_id: str,
    *,
    persist_fallback: bool = False,
) -> Path | None:
    roots = task_workspace_roots(task_id, persist_fallback=persist_fallback)
    return roots[0] if roots else None


def task_workspace_roots(
    task_id: str,
    *,
    persist_fallback: bool = False,
) -> list[Path]:
    """All workspace directories that may contain artifacts for a task."""
    task = store.get_by_key("tasks", "id", task_id) or {}
    roots: list[Path] = []
    seen: set[str] = set()

    def add_root(path: Path | None) -> None:
        if path is None:
            return
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            return
        key = str(resolved).lower()
        if key in seen or not resolved.is_dir():
            return
        seen.add(key)
        roots.append(resolved)

    trusted_roots = trusted_task_workspace_dirs(task_id, task)
    raw = str(task.get("workspace_dir") or "").strip()
    if raw:
        candidate = Path(raw)
        if any(_same_resolved_path(candidate, root) for root in trusted_roots):
            add_root(candidate)

    for root in trusted_roots:
        add_root(root)

    if not roots:
        try:
            agent_id = task_agent_id(task_id)
            root = _agent_workspace_dir(agent_id)
            if persist_fallback:
                sync_task_workspace(task_id, agent_id, root)
            add_root(root)
        except HTTPException:
            pass

    return roots


def find_file_in_workspace_roots(
    roots: list[Path],
    normalized: str,
) -> Path | None:
    rel = Path(normalized)
    if ".." in rel.parts:
        return None

    for root in roots:
        direct = (root / rel).resolve()
        try:
            direct.relative_to(root)
        except ValueError:
            continue
        if direct.is_file():
            return direct

    basename = rel.name
    if not basename:
        return None

    matches: list[Path] = []
    for root in roots:
        root_resolved = root.resolve()
        for path in root.rglob(basename):
            if not path.is_file():
                continue
            try:
                path.resolve().relative_to(root_resolved)
            except (OSError, ValueError):
                continue
            matches.append(path)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    suffix = rel.as_posix().lower()
    for path in matches:
        for root in roots:
            try:
                rel_path = path.relative_to(root).as_posix().lower()
            except ValueError:
                continue
            if rel_path.endswith(suffix):
                return path
    return sorted(
        matches,
        key=lambda path: len(path.parts),
    )[0]


def resolve_task_workspace_file(task_id: str, rel_path: str) -> Path:
    normalized = normalize_artifact_path(rel_path)
    if not normalized:
        raise HTTPException(status_code=400, detail="Invalid path")

    roots = task_workspace_roots(task_id, persist_fallback=True)
    if not roots:
        raise HTTPException(status_code=404, detail="Workspace not found")

    candidate = Path(normalized)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        try:
            resolved_candidate = candidate.expanduser().resolve()
        except OSError:
            raise HTTPException(
                status_code=400,
                detail="Workspace paths must resolve inside a task workspace",
            ) from None
        for root in roots:
            try:
                resolved_candidate.relative_to(root.resolve())
            except ValueError:
                continue
            if resolved_candidate.is_file():
                return resolved_candidate
            raise HTTPException(status_code=404, detail="File not found")
        raise HTTPException(
            status_code=400,
            detail="Workspace paths must resolve inside a task workspace",
        )

    found = find_file_in_workspace_roots(roots, normalized)
    if found is not None:
        return found

    raise HTTPException(status_code=404, detail="File not found")


def task_workspace_tree_files(task_id: str) -> list[dict[str, str]]:
    roots = task_workspace_roots(task_id, persist_fallback=True)
    files: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for root in roots:
        root_resolved = root.resolve()
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            try:
                path.resolve().relative_to(root_resolved)
            except (OSError, ValueError):
                continue
            rel = path.relative_to(root).as_posix()
            if rel in seen_paths:
                continue
            seen_paths.add(rel)
            files.append({"path": rel})
    files.sort(key=lambda item: item["path"])
    return files
