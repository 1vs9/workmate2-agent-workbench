# -*- coding: utf-8 -*-
"""Provision QwenPaw agent profiles for AgentDesk plaza / store employees."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from ..agents.provisioning import _install_initial_skills, provision_agent_profile
from ..agents.skill_system.store import read_skill_manifest
from ..config.config import (
    generate_short_agent_id,
    load_agent_config,
    save_agent_config,
    validate_agent_id,
)
from ..config.utils import load_config, save_config
from ..constant import WORKING_DIR
from ..agents.utils.setup_utils import normalize_agent_language
from .default_agent import DEFAULT_AGENT_ID, is_default_agentdesk_assignee, is_plaza_hidden_assignee
from .team_leader_agents import is_team_leader_hidden
from .store import store

logger = logging.getLogger(__name__)

_EMPLOYEE_ID_PREFIX = "emp_"
_EMPLOYEE_PROFILE_TEMPLATE_VERSION = 1

# Process-level cache of employee workspace signatures already synced this run.
# ``ensure_employee_agent_profile`` runs on every chat turn for a position
# agent; without this cache it re-writes PROFILE.md, re-finalizes bootstrap and
# re-installs skills each time (a main cause of slow position-agent replies).
# The signature captures everything ``_sync_employee_agent`` applies, so any
# edit to the employee (name / desc / skills) naturally invalidates it; a code
# change to the profile template invalidates it on the next process start.
_synced_employee_signatures: dict[str, str] = {}


def _employee_sync_signature(name: str, desc: str, skills: list[str]) -> str:
    skill_names = sorted(str(item).strip() for item in skills if str(item).strip())
    payload = json.dumps(
        {
            "name": name,
            "desc": (desc or "").strip(),
            "skills": skill_names,
            "template_version": _EMPLOYEE_PROFILE_TEMPLATE_VERSION,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def invalidate_employee_sync_cache(agent_id: str | None = None) -> None:
    """Drop cached sync signatures so the next ensure call re-syncs to disk."""
    if agent_id is None:
        _synced_employee_signatures.clear()
        return
    _synced_employee_signatures.pop(str(agent_id).strip(), None)


def invalidate_employee_sync_cache_for_name(employee_name: str) -> None:
    """Drop cached sync signature for a store employee before profile edits."""
    trimmed = str(employee_name or "").strip()
    if not trimmed:
        return
    employee = store.get_by_key("employees", "name", trimmed)
    agent_id = str((employee or {}).get("agent_id") or "").strip()
    if agent_id:
        invalidate_employee_sync_cache(agent_id)
        return
    if trimmed in _synced_employee_signatures:
        invalidate_employee_sync_cache(trimmed)


def _skills_present_in_workspace(workspace_dir: Path, skill_names: list[str]) -> bool:
    """Return True when every requested skill appears in the workspace manifest."""
    if not skill_names:
        return True
    try:
        state = read_skill_manifest(workspace_dir).get("skills", {})
    except Exception:  # noqa: BLE001 - corrupt manifest
        return False
    for raw in skill_names:
        name = str(raw).strip()
        if not name:
            continue
        if name in state:
            continue
        lowered = name.lower()
        if not any(str(key).lower() == lowered for key in state):
            return False
    return True


def _employee_record(name: str) -> dict | None:
    trimmed = str(name or "").strip()
    if not trimmed:
        return None
    record = store.get_by_key("employees", "name", trimmed)
    if record is not None:
        return dict(record)
    plaza = store.get_by_key("plaza", "name", trimmed)
    if plaza is None:
        return None
    return {
        "name": trimmed,
        "desc": plaza.get("desc", ""),
        "tools": plaza.get("tools", []),
        "skills": plaza.get("skills", []),
        "mcp": plaza.get("mcp", []),
        "agent_id": plaza.get("agent_id", ""),
    }


def _allocate_agent_id(display_name: str, existing_ids: set[str]) -> str:
    digest = hashlib.sha256(display_name.encode("utf-8")).hexdigest()[:10]
    candidates = [
        f"{_EMPLOYEE_ID_PREFIX}{digest}",
        *(
            f"{_EMPLOYEE_ID_PREFIX}{digest}_{suffix}"
            for suffix in range(2, 12)
        ),
    ]
    for candidate in candidates:
        if candidate in existing_ids:
            continue
        try:
            validate_agent_id(candidate, existing_ids)
        except ValueError:
            continue
        return candidate

    for _ in range(10):
        candidate = generate_short_agent_id()
        if candidate not in existing_ids:
            return candidate
    raise RuntimeError(f"Failed to allocate agent id for employee {display_name!r}")


def _render_employee_profile(name: str, desc: str) -> str:
    role_desc = (desc or "").strip() or f"AgentDesk 数字员工 · {name}"
    return f"""---
summary: "AgentDesk 数字员工身份"
read_when:
  - 手动引导工作区
---

## 身份

- **名字：** {name}
- **定位：** AgentDesk 数字员工 · {name}
- **风格：** 专业、清晰，符合岗位职责

## 角色说明

{role_desc}

### 行为准则

- 你就是「{name}」，请以此身份与用户交流。
- **不要**自称 default 代理、AgentDesk企伴或其他岗位名称。
- 用户用中文提问时，全文使用中文回复。
- 先理解用户目标，再选择合适工具或技能；需要时主动澄清关键约束。

## 用户资料

*了解你在帮的人。边走边更新。*

- **名字：**
- **怎么叫他们：**
- **代词：** *（可选）*
- **笔记：**

### 背景

*（他们在意什么？在做啥项目？什么让他们烦？什么逗他们笑？边走边积累。）*
"""


def _write_employee_meta(workspace_dir: Path, name: str) -> None:
    """Mark workspace as a pre-configured AgentDesk employee (skip BOOTSTRAP)."""
    meta_path = workspace_dir / "EMPLOYEE.json"
    meta_content = json.dumps(
        {"is_agentdesk_employee": True, "name": name},
        ensure_ascii=False,
    )
    if meta_path.exists():
        current = meta_path.read_text(encoding="utf-8")
        if current == meta_content:
            return
    meta_path.write_text(meta_content, encoding="utf-8")


def _write_employee_profile(workspace_dir: Path, name: str, desc: str) -> None:
    profile_path = workspace_dir / "PROFILE.md"
    content = _render_employee_profile(name, desc)
    if profile_path.exists():
        current = profile_path.read_text(encoding="utf-8")
        if current == content:
            _write_employee_meta(workspace_dir, name)
            return
    profile_path.write_text(content, encoding="utf-8")
    _write_employee_meta(workspace_dir, name)


def _finalize_employee_workspace(workspace_dir: Path) -> None:
    """Skip generic agent bootstrap for pre-configured AgentDesk employees."""
    from ..agents.utils.setup_utils import _remove_bootstrap_from_workspace

    _remove_bootstrap_from_workspace(workspace_dir)
    flag = workspace_dir / ".bootstrap_completed"
    try:
        flag.touch(exist_ok=True)
    except OSError as exc:
        logger.warning("Could not mark bootstrap completed for %s: %s", workspace_dir, exc)


def _sync_employee_agent(agent_id: str, name: str, desc: str, skills: list[str]) -> None:
    signature = _employee_sync_signature(name, desc, skills)
    if _synced_employee_signatures.get(agent_id) == signature:
        # Already synced with these exact inputs in this process -- nothing on
        # disk would change, so skip the IO on the hot chat path.
        return

    config = load_config()
    ref = config.agents.profiles.get(agent_id)
    if ref is None:
        return

    workspace_dir = Path(getattr(ref, "workspace_dir", "") or f"{WORKING_DIR}/workspaces/{agent_id}")
    workspace_dir.mkdir(parents=True, exist_ok=True)
    _write_employee_profile(workspace_dir, name, desc)
    _finalize_employee_workspace(workspace_dir)

    try:
        agent_config = load_agent_config(agent_id)
    except Exception:  # noqa: BLE001 - user-edited config
        return

    updated = False
    if (agent_config.name or "").strip() != name:
        agent_config.name = name
        updated = True
    description = (desc or "").strip() or f"AgentDesk 数字员工 · {name}"
    if (agent_config.description or "").strip() != description:
        agent_config.description = description
        updated = True

    skill_names = [str(item).strip() for item in skills if str(item).strip()]
    if skill_names:
        _install_initial_skills(workspace_dir, skill_names)

    if updated:
        save_agent_config(agent_id, agent_config)
        invalidate_agent_display_name_index()

    # Record the signature only after a successful sync so transient failures
    # (e.g. load_agent_config raising) retry next time. Do not cache when skills
    # are still missing from the workspace — _install_initial_skills can fail
    # silently and the edit modal would otherwise skip remounting them.
    if skill_names and not _skills_present_in_workspace(workspace_dir, skill_names):
        _synced_employee_signatures.pop(agent_id, None)
    else:
        _synced_employee_signatures[agent_id] = signature


def _create_employee_agent(
    *,
    agent_id: str,
    name: str,
    desc: str,
    skills: list[str],
) -> None:
    config = load_config()
    existing_ids = set(config.agents.profiles.keys())
    if agent_id in existing_ids:
        _sync_employee_agent(agent_id, name, desc, skills)
        return

    language = normalize_agent_language(config.agents.language or "zh")
    skill_names = [str(item).strip() for item in skills if str(item).strip()]
    description = (desc or "").strip() or f"AgentDesk 数字员工 · {name}"

    def _post_workspace_init(workspace_dir: Path, _created_agent_id: str) -> None:
        _write_employee_profile(workspace_dir, name, desc)
        _finalize_employee_workspace(workspace_dir)

    provision_agent_profile(
        name=name,
        description=description,
        requested_id=agent_id,
        workspace_dir=Path(WORKING_DIR) / "workspaces" / agent_id,
        language=language,
        skill_names=skill_names,
        post_workspace_init=_post_workspace_init,
    )
    logger.info("Provisioned AgentDesk employee agent %s for %r", agent_id, name)


# Process-level cache for display-name -> agent_id lookups used by list APIs.
_display_name_index: dict[str, str] | None = None
_display_name_index_profile_keys: frozenset[str] | None = None


def invalidate_agent_display_name_index() -> None:
    """Drop the cached display-name index after profile create/delete."""
    global _display_name_index, _display_name_index_profile_keys
    _display_name_index = None
    _display_name_index_profile_keys = None


def build_agent_display_name_index(profiles: dict | None = None) -> dict[str, str]:
    """Map human-readable agent names to profile ids in one pass."""
    global _display_name_index, _display_name_index_profile_keys
    if profiles is None:
        profiles = load_config().agents.profiles
    profile_keys = frozenset(profiles.keys())
    if (
        _display_name_index is not None
        and _display_name_index_profile_keys == profile_keys
    ):
        return _display_name_index

    index: dict[str, str] = {}
    for agent_id in profiles:
        if is_plaza_hidden_assignee(agent_id):
            continue
        try:
            cfg = load_agent_config(agent_id)
        except Exception:  # noqa: BLE001 - user-edited config
            continue
        display = (cfg.name or "").strip()
        if display and display not in index:
            index[display] = agent_id

    _display_name_index = index
    _display_name_index_profile_keys = profile_keys
    return index


def _match_agent_id_by_display_name(
    name: str,
    profiles: dict,
    name_index: dict[str, str] | None = None,
) -> str | None:
    trimmed = str(name or "").strip()
    if not trimmed or is_team_leader_hidden(trimmed):
        return None
    if name_index is None:
        name_index = build_agent_display_name_index(profiles)
    return name_index.get(trimmed)


def ensure_employee_agent_profile(employee_name: str) -> str | None:
    """Ensure a store/plaza employee has a QwenPaw agent profile.

    Returns the resolved agent id, or ``None`` when the name is unknown.
    """
    name = str(employee_name or "").strip()
    if not name or is_default_agentdesk_assignee(name):
        return DEFAULT_AGENT_ID

    config = load_config()
    profiles = config.agents.profiles
    if name in profiles:
        employee = _employee_record(name) or {"name": name, "desc": "", "skills": []}
        _sync_employee_agent(
            name,
            name,
            str(employee.get("desc") or ""),
            list(employee.get("skills") or []),
        )
        return name

    employee = _employee_record(name)
    if employee is None:
        return None

    stored_id = str(employee.get("agent_id") or "").strip()
    if stored_id and stored_id in profiles:
        _sync_employee_agent(
            stored_id,
            name,
            str(employee.get("desc") or ""),
            list(employee.get("skills") or []),
        )
        return stored_id

    matched = _match_agent_id_by_display_name(name, profiles)
    if matched:
        store.upsert_by_key(
            "employees",
            "name",
            name,
            {**employee, "agent_id": matched},
        )
        _sync_employee_agent(
            matched,
            name,
            str(employee.get("desc") or ""),
            list(employee.get("skills") or []),
        )
        return matched

    agent_id = _allocate_agent_id(name, set(profiles.keys()))
    _create_employee_agent(
        agent_id=agent_id,
        name=name,
        desc=str(employee.get("desc") or ""),
        skills=list(employee.get("skills") or []),
    )
    store.upsert_by_key(
        "employees",
        "name",
        name,
        {**employee, "agent_id": agent_id},
    )
    invalidate_agent_display_name_index()
    return agent_id


def is_employee_agent_id(agent_id: str | None) -> bool:
    """Return True when *agent_id* looks like a AgentDesk employee agent profile."""
    trimmed = str(agent_id or "").strip()
    if not trimmed or is_plaza_hidden_assignee(trimmed):
        return False
    from .team_leader_agents import is_team_leader_agent_id

    if is_team_leader_agent_id(trimmed):
        return False
    if trimmed.startswith(_EMPLOYEE_ID_PREFIX):
        return True

    config = load_config()
    ref = config.agents.profiles.get(trimmed)
    if ref is None:
        return False
    workspace_dir = Path(getattr(ref, "workspace_dir", "") or f"{WORKING_DIR}/workspaces/{trimmed}")
    meta_path = workspace_dir / "EMPLOYEE.json"
    if not meta_path.is_file():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(meta.get("is_agentdesk_employee"))


def _read_employee_meta_name(workspace_dir: Path) -> str | None:
    meta_path = workspace_dir / "EMPLOYEE.json"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    name = str(meta.get("name") or "").strip()
    return name or None


def _resolve_agent_display_name(agent_id: str) -> str:
    """Human-readable employee name for a provisioned agent profile."""
    config = load_config()
    ref = config.agents.profiles.get(agent_id)
    workspace_dir = (
        Path(getattr(ref, "workspace_dir", "") or f"{WORKING_DIR}/workspaces/{agent_id}")
        if ref is not None
        else Path(WORKING_DIR) / "workspaces" / agent_id
    )

    meta_name = _read_employee_meta_name(workspace_dir)
    if meta_name:
        return meta_name

    try:
        cfg = load_agent_config(agent_id)
        name = str(cfg.name or "").strip()
        if name and not name.startswith(_EMPLOYEE_ID_PREFIX) and name != agent_id:
            return name
    except Exception:  # noqa: BLE001 - user-edited config
        pass

    if agent_id.startswith(_EMPLOYEE_ID_PREFIX):
        suffix = agent_id[len(_EMPLOYEE_ID_PREFIX) :].strip("_")
        if suffix:
            return suffix.replace("_", " ")
    return agent_id


def _employee_store_name_for_agent(agent_id: str) -> str | None:
    for item in store.list_items("employees"):
        if str(item.get("agent_id") or "").strip() == agent_id:
            name = str(item.get("name") or "").strip()
            if name:
                return name
    return None


_DESC_ALIAS_FIELDS = (
    "description",
    "prompt",
    "system_prompt",
    "systemPrompt",
    "responsibilities",
    "persona",
)


def _resolve_item_desc(item: dict | None) -> str:
    """Read canonical desc from store records that may use alias field names."""
    if not item:
        return ""
    direct = str(item.get("desc") or "").strip()
    if direct:
        return direct
    parts: list[str] = []
    for key in _DESC_ALIAS_FIELDS:
        value = str(item.get(key) or "").strip()
        if value and value not in parts:
            parts.append(value)
    return "\n\n".join(parts) if parts else ""


def register_provisioned_agent_in_plaza(agent_id: str) -> bool:
    """Ensure a provisioned employee agent appears in plaza + employees store.

    Returns True when a new plaza card was created or linked for *agent_id*.
    """
    trimmed = str(agent_id or "").strip()
    if not is_employee_agent_id(trimmed):
        return False

    existing_name = _employee_store_name_for_agent(trimmed)
    display_name = existing_name or _resolve_agent_display_name(trimmed)
    if not display_name or is_plaza_hidden_assignee(display_name):
        return False

    plaza_item = store.get_by_key("plaza", "name", display_name)
    employee_item = store.get_by_key("employees", "name", display_name)
    stored_plaza_desc = _resolve_item_desc(plaza_item)
    stored_employee_desc = _resolve_item_desc(employee_item)
    if (
        plaza_item is not None
        and employee_item is not None
        and str(employee_item.get("agent_id") or "").strip() == trimmed
        and stored_plaza_desc
        and stored_employee_desc
    ):
        return False

    try:
        cfg = load_agent_config(trimmed)
        description = str(cfg.description or "").strip() or f"AgentDesk 数字员工 · {display_name}"
        skill_names = [str(item).strip() for item in (getattr(cfg, "skill_names", []) or []) if str(item).strip()]
    except Exception:  # noqa: BLE001 - user-edited config
        description = f"AgentDesk 数字员工 · {display_name}"
        skill_names = []

    resolved_desc = stored_plaza_desc or stored_employee_desc or description
    was_missing = plaza_item is None or employee_item is None
    needs_desc_backfill = not stored_plaza_desc or not stored_employee_desc

    plaza_payload = {
        **(plaza_item or {}),
        "name": display_name,
        "desc": resolved_desc,
        "tags": list((plaza_item or {}).get("tags") or ["AgentDesk"]),
        "skills": list((plaza_item or {}).get("skills") or skill_names),
        "tools": list((plaza_item or {}).get("tools") or []),
        "mcp": list((plaza_item or {}).get("mcp") or []),
        "usage": (plaza_item or {}).get("usage") or "作为 AgentDesk 数字员工执行任务",
        "joined": True,
    }
    store.upsert_by_key("plaza", "name", display_name, plaza_payload)

    employee_payload = {
        **(employee_item or {}),
        "name": display_name,
        "agent_id": trimmed,
        "desc": resolved_desc,
        "skills": list((employee_item or {}).get("skills") or skill_names),
        "tools": list((employee_item or {}).get("tools") or []),
        "mcp": list((employee_item or {}).get("mcp") or []),
    }
    store.upsert_by_key("employees", "name", display_name, employee_payload)

    _sync_employee_agent(
        trimmed,
        display_name,
        str(employee_payload.get("desc") or ""),
        list(employee_payload.get("skills") or []),
    )
    return was_missing or needs_desc_backfill


def delete_employee_agent(display_name: str) -> bool:
    """Remove plaza card, employee record, and QwenPaw agent profile."""
    trimmed = str(display_name or "").strip()
    if not trimmed or is_default_agentdesk_assignee(trimmed) or is_plaza_hidden_assignee(trimmed):
        return False

    from .builtin_agents import dismiss_builtin_agent

    dismiss_builtin_agent(trimmed)

    deleted_any = False
    employee = store.get_by_key("employees", "name", trimmed)
    agent_id = str((employee or {}).get("agent_id") or "").strip()

    if store.delete_by_key("plaza", "name", trimmed):
        deleted_any = True
    if store.delete_by_key("employees", "name", trimmed):
        deleted_any = True

    config = load_config()
    if not agent_id:
        agent_id = _match_agent_id_by_display_name(trimmed, config.agents.profiles) or ""

    if (
        agent_id
        and agent_id != DEFAULT_AGENT_ID
        and is_employee_agent_id(agent_id)
        and agent_id in config.agents.profiles
    ):
        del config.agents.profiles[agent_id]
        config.agents.agent_order = [
            item for item in (config.agents.agent_order or []) if item != agent_id
        ]
        save_config(config)
        invalidate_employee_sync_cache(agent_id)
        invalidate_agent_display_name_index()
        deleted_any = True
        logger.info("Removed employee agent %s (%r)", agent_id, trimmed)

    return deleted_any


def sync_orphan_employee_agents_to_plaza() -> int:
    """Register configured employee agents missing from the plaza store."""
    config = load_config()
    synced = 0
    for agent_id in config.agents.profiles:
        if register_provisioned_agent_in_plaza(agent_id):
            synced += 1
    if synced:
        logger.info("Synced %s provisioned employee agent(s) to plaza", synced)
    return synced
