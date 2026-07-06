# -*- coding: utf-8 -*-
"""Ship AgentDesk plaza / employee / team templates from packaged JSON."""

from __future__ import annotations

import json
import logging
import os
import threading
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from .employee_agents import ensure_employee_agent_profile, sync_orphan_employee_agents_to_plaza
from .store import store
from .team_leader_agents import provision_team_leader_agent, sync_team_leader_agent

logger = logging.getLogger(__name__)

_DATA_PATH = Path(__file__).resolve().parent / "data" / "builtin_agents.json"
_BUILTIN_USAGE = "内置岗位模板"
_TEAM_USAGE = "内置团队模板"
_RESEED_ENV = "AGENTDESK_RESEED_BUILTINS"


@lru_cache(maxsize=1)
def load_builtin_catalog() -> dict[str, Any]:
    """Load packaged builtin plaza/team definitions."""
    raw = _DATA_PATH.read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid builtin catalog format in {_DATA_PATH}")
    payload.setdefault("plaza", [])
    payload.setdefault("teams", [])
    return payload


def catalog_version() -> int:
    """Monotonic catalog version; bump when adding packaged plaza/team entries."""
    return int(load_builtin_catalog().get("version") or 0)


def _stored_seed_version() -> int:
    return int(store.read_meta().get("builtin_seed_version") or 0)


def _is_force_reseed() -> bool:
    raw = os.environ.get(_RESEED_ENV, "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def dismissed_builtin_ids() -> set[str]:
    raw = store.read_meta().get("dismissed_builtin_ids") or []
    if not isinstance(raw, list):
        return set()
    return {str(item).strip() for item in raw if str(item).strip()}


def _resolve_catalog_builtin_id(name: str) -> str:
    trimmed = str(name or "").strip()
    if not trimmed:
        return ""
    for item in load_builtin_catalog().get("plaza", []):
        if str(item.get("name") or "").strip() == trimmed:
            return str(item.get("builtin_id") or "").strip()
    for team in load_builtin_catalog().get("teams", []):
        if str(team.get("name") or "").strip() == trimmed:
            return str(team.get("builtin_id") or team.get("id") or "").strip()
    return ""


def dismiss_builtin_agent(name: str) -> None:
    """Record that the user removed a packaged builtin so seed won't restore it."""
    builtin_id = _resolve_catalog_builtin_id(name)
    if not builtin_id:
        plaza_item = store.get_by_key("plaza", "name", name)
        team_item = store.get_by_key("teams", "name", name)
        builtin_id = str(
            (plaza_item or team_item or {}).get("builtin_id") or "",
        ).strip()
    if not builtin_id:
        return
    dismissed = sorted(dismissed_builtin_ids() | {builtin_id})
    store.patch_meta({"dismissed_builtin_ids": dismissed})


def should_seed_builtin_agents() -> bool:
    """Decide whether startup should run packaged seed logic."""
    if _is_force_reseed():
        return True
    if store.is_uninitialized():
        return True
    return catalog_version() > _stored_seed_version()


def _plaza_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(item)
    payload.pop("auto_join", None)
    payload.pop("team_id", None)
    payload.setdefault("tags", [])
    payload.setdefault("skills", [])
    payload.setdefault("tools", [])
    payload.setdefault("mcp", [])
    payload.setdefault("usage", _BUILTIN_USAGE)
    return payload


def _should_auto_join(item: dict[str, Any]) -> bool:
    if str(item.get("kind") or "").strip().lower() == "team":
        return False
    return bool(item.get("auto_join", True))


def _is_dismissed(item: dict[str, Any]) -> bool:
    builtin_id = str(item.get("builtin_id") or "").strip()
    return bool(builtin_id and builtin_id in dismissed_builtin_ids())


def ensure_builtin_plaza_catalog() -> int:
    """Insert missing builtin plaza cards without overwriting user edits."""
    added = 0
    for item in load_builtin_catalog().get("plaza", []):
        if _is_dismissed(item):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if store.get_by_key("plaza", "name", name) is not None:
            continue
        store.upsert_by_key("plaza", "name", name, _plaza_payload(item))
        added += 1
    if added:
        logger.info("Seeded %s builtin plaza card(s)", added)
    return added


def ensure_builtin_employee_records() -> int:
    """Create employee store rows for auto-join builtins without provisioning agents."""
    added = 0
    for item in load_builtin_catalog().get("plaza", []):
        if _is_dismissed(item) or not _should_auto_join(item):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if store.get_by_key("employees", "name", name) is not None:
            continue
        plaza_item = store.get_by_key("plaza", "name", name) or _plaza_payload(item)
        store.upsert_by_key(
            "employees",
            "name",
            name,
            {
                "name": name,
                "desc": plaza_item.get("desc", ""),
                "tools": plaza_item.get("tools", []),
                "skills": plaza_item.get("skills", []),
                "mcp": plaza_item.get("mcp", []),
                "avatar": plaza_item.get("avatar"),
            },
        )
        added += 1
    if added:
        logger.info("Seeded %s builtin employee record(s)", added)
    return added


def provision_builtin_employee_agents() -> int:
    """Provision QwenPaw agent profiles for joined builtin employees."""
    provisioned = 0
    for item in load_builtin_catalog().get("plaza", []):
        if _is_dismissed(item) or not _should_auto_join(item):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        agent_id = ensure_employee_agent_profile(name)
        if agent_id:
            current = store.get_by_key("employees", "name", name)
            if current and current.get("agent_id") != agent_id:
                store.upsert_by_key(
                    "employees",
                    "name",
                    name,
                    {**current, "agent_id": agent_id},
                )
                provisioned += 1
    if provisioned:
        logger.info("Provisioned %s builtin employee agent profile(s)", provisioned)
    return provisioned


def ensure_builtin_employees() -> int:
    """Join builtin plaza roles and provision QwenPaw agent profiles."""
    added = ensure_builtin_employee_records()
    provisioned = provision_builtin_employee_agents()
    return added + provisioned


def _normalize_team_seed(team: dict[str, Any]) -> dict[str, Any]:
    team_id = str(team.get("id") or "").strip()
    team_name = str(team.get("name") or "").strip()
    members_raw = team.get("members") or []
    members = (
        [str(name).strip() for name in members_raw if str(name).strip()]
        if isinstance(members_raw, list)
        else []
    )
    return {
        "id": team_id,
        "name": team_name,
        "desc": str(team.get("desc") or "").strip(),
        "tags": list(team.get("tags") or []),
        "members": members,
        "skills": list(team.get("skills") or []),
        "usage": str(team.get("usage") or _TEAM_USAGE),
        "builtin_id": str(team.get("builtin_id") or team_id),
    }


def ensure_builtin_teams() -> int:
    """Create packaged multi-agent teams when missing."""
    created = 0
    for team in load_builtin_catalog().get("teams", []):
        if _is_dismissed(team):
            continue
        normalized = _normalize_team_seed(team)
        team_id = normalized["id"]
        team_name = normalized["name"]
        if not team_id or not team_name:
            continue
        if store.get_by_key("teams", "id", team_id) is not None:
            existing = store.get_by_key("teams", "id", team_id) or {}
            if existing.get("leader_agent_id"):
                sync_team_leader_agent(existing)
            continue

        for member_name in normalized["members"]:
            ensure_employee_agent_profile(member_name)

        payload = {
            "id": team_id,
            "name": team_name,
            "desc": normalized["desc"],
            "tags": normalized["tags"],
            "members": normalized["members"],
            "usage": normalized["usage"],
            "builtin_id": normalized["builtin_id"],
        }
        leader_info = provision_team_leader_agent(
            team_id=team_id,
            team_name=team_name,
            team_prompt=normalized["desc"],
            workers=normalized["members"],
        )
        payload["leader"] = leader_info["leader_name"]
        payload["leader_agent_id"] = leader_info["agent_id"]
        store.upsert_by_key("teams", "id", team_id, payload)
        created += 1
    if created:
        logger.info("Seeded %s builtin team(s)", created)
    return created


def _record_seed_complete() -> None:
    store.patch_meta({"builtin_seed_version": catalog_version()})


def ensure_builtin_agents(*, defer_agent_provision: bool = True) -> dict[str, int]:
    """Seed plaza catalog, employees, and teams for out-of-box use."""
    summary = {
        "plaza_added": ensure_builtin_plaza_catalog(),
        "employees_provisioned": ensure_builtin_employee_records(),
        "teams_created": ensure_builtin_teams(),
    }
    _record_seed_complete()

    def _provision_profiles() -> None:
        try:
            provision_builtin_employee_agents()
            sync_orphan_employee_agents_to_plaza()
        except Exception:
            logger.exception("Background builtin agent provision failed")

    if defer_agent_provision:
        threading.Thread(
            target=_provision_profiles,
            daemon=True,
            name="builtin-agent-provision",
        ).start()
    else:
        _provision_profiles()
    return summary


def maybe_seed_builtin_agents() -> dict[str, int] | None:
    """Run packaged seed on first launch, catalog upgrade, or explicit reseed."""
    if not should_seed_builtin_agents():
        logger.debug("Skipping builtin agent seed (store already initialized)")
        return None
    logger.info("Seeding AgentDesk builtin plaza, employees, and teams")
    return ensure_builtin_agents()
