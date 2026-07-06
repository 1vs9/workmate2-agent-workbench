# -*- coding: utf-8 -*-
"""Hidden team Leader agents — orchestration-only, not plaza employees."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

from ..app.routers.agents import _initialize_agent_workspace
from ..config.config import (
    AgentProfileConfig,
    AgentProfileRef,
    AgentsRunningConfig,
    ChannelConfig,
    HeartbeatConfig,
    MCPConfig,
    ToolsConfig,
    load_agent_config,
    save_agent_config,
    validate_agent_id,
)
from ..config.utils import load_config, save_config
from ..constant import WORKING_DIR
from ..agents.utils.setup_utils import (
    _template_fallback_language_order,
    normalize_agent_language,
)
from .store import store

logger = logging.getLogger(__name__)

_LEADER_ID_PREFIX = "lead_"
_LEADER_NAME_SUFFIX = "·leader"
_LEGACY_LEADER_NAME_SUFFIX = "·编排者"
_TEAM_LEADER_TEMPLATE_ID = "team-leader"
_TEAM_PROMPT_SECTION_HEADERS = {
    "zh": "### 团队提示词（上下文）",
    "en": "### Team prompt (context)",
}
_AGENTS_ROOT = Path(__file__).resolve().parent.parent / "agents"
_TEAM_LEADER_SKILLS = ["multi_agent_collaboration", "make_plan"]

# Team leaders delegate with the SYNCHRONOUS ``chat_with_agent`` primitive so the
# QwenPaw leader run blocks on each worker reply, receives it into context, and
# synthesizes the final answer natively in a single run. This makes the AgentDesk
# team stream a pure passthrough: there is no fire-and-forget background task, so
# the leader run never ends before workers finish and no AgentDesk-side coordinator
# / polling / synthesis-injection layer is needed. ``chat_with_agent`` already
# publishes the worker's live SSE to the worker bus keyed by the member session,
# so member tabs still stream in real time. Async ``submit_to_agent`` is
# intentionally NOT in the whitelist. The leader is a coordinator: it only ever
# needs these delegation tools; every other builtin stays disabled via
# ``_team_leader_tools_config``.
_LEADER_REQUIRED_TOOLS = ("chat_with_agent", "list_agents")
_TEAM_LEADER_MAX_ITERS = 24
# Bump when leader PROFILE/SOUL orchestration rules change to force re-sync.
_LEADER_PROFILE_VERSION = "2026-06-team-sync-passthrough"

# Upper bound a leader should allow a single synchronous ``chat_with_agent``
# delegation to run before giving up (passed as the tool ``timeout``). Deep
# research members can take several minutes, so keep this generous.
ASYNC_WORKER_WAIT_S = 600.0

# Process-level cache of leader workspace signatures already synced this run.
# ``sync_team_leader_agent`` runs at the start of every team chat; without this
# cache it re-initializes the leader workspace (template copy + skill install +
# markdown rewrite) each time, a main cause of slow team-run startup. The
# signature captures team name / id / prompt / members, so any team edit
# naturally invalidates it.
_synced_leader_signatures: dict[str, str] = {}


def _leader_sync_signature(
    team_name: str,
    team_id: str,
    team_prompt: str,
    workers: list[str],
) -> str:
    payload = json.dumps(
        {
            "name": team_name,
            "id": team_id,
            "prompt": (team_prompt or "").strip(),
            "workers": [str(n).strip() for n in workers],
            "profile_version": _LEADER_PROFILE_VERSION,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def invalidate_leader_sync_cache(agent_id: str | None = None) -> None:
    """Drop cached leader sync signatures so the next sync re-writes to disk."""
    if agent_id is None:
        _synced_leader_signatures.clear()
        return
    _synced_leader_signatures.pop(str(agent_id).strip(), None)


def _team_leader_tools_config() -> ToolsConfig:
    """Tools preset for hidden team leaders.

    The leader is a pure coordinator: it plans and delegates but never executes
    work itself. So we WHITELIST only the delegation tools and disable every
    other builtin (shell, file read/write/edit, grep/glob, browser, screenshot,
    image/video, etc.). This matters for two reasons:

    1. Latency: each enabled tool's JSON schema is serialized into the model
       input on *every* leader turn. Carrying ~17 tools instead of ~3 adds
       several thousand prompt tokens per turn, which directly inflates
       time-to-first-token even when the agent is warm.
    2. Role correctness: it structurally prevents the leader from doing a
       worker's job (reading files, running shell, browsing) instead of
       delegating.
    """
    tools = ToolsConfig()
    required = set(_LEADER_REQUIRED_TOOLS)
    for name, tool in tools.builtin_tools.items():
        if tool is not None:
            tool.enabled = name in required
    return tools


def _enforce_leader_tools_config(agent_config: Any) -> bool:
    """Apply the coordinator-only tool whitelist to an existing leader config.

    Returns ``True`` when the configuration was modified so the caller knows
    it must be persisted.
    """
    if not hasattr(agent_config, "tools"):
        return False
    tools = getattr(agent_config, "tools", None)
    if tools is None or not hasattr(tools, "builtin_tools"):
        agent_config.tools = _team_leader_tools_config()
        return True
    required = set(_LEADER_REQUIRED_TOOLS)
    changed = False
    for name, tool in tools.builtin_tools.items():
        if tool is None:
            continue
        desired = name in required
        if getattr(tool, "enabled", False) != desired:
            tool.enabled = desired
            changed = True
    return changed


def team_leader_agent_id(team_id: str) -> str:
    """Stable hidden agent id for a team leader."""
    slug = re.sub(r"[^a-zA-Z0-9]", "", str(team_id or ""))[:16] or "team"
    candidate = f"{_LEADER_ID_PREFIX}{slug}"
    existing = set(load_config().agents.profiles.keys())
    if candidate not in existing:
        try:
            validate_agent_id(candidate, existing)
            return candidate
        except ValueError:
            pass
    for suffix in range(2, 20):
        alt = f"{_LEADER_ID_PREFIX}{slug}_{suffix}"
        if alt not in existing:
            try:
                validate_agent_id(alt, existing)
                return alt
            except ValueError:
                continue
    raise RuntimeError(f"Failed to allocate team leader agent id for team {team_id!r}")


def team_leader_display_name(team_name: str) -> str:
    name = str(team_name or "").strip() or "团队"
    return f"{name}{_LEADER_NAME_SUFFIX}"


def is_team_leader_agent_id(agent_id: str | None) -> bool:
    normalized = str(agent_id or "").strip()
    return normalized.startswith(_LEADER_ID_PREFIX)


def is_team_leader_hidden(name_or_id: str | None) -> bool:
    """True when *name_or_id* refers to a hidden team leader agent."""
    normalized = str(name_or_id or "").strip()
    if not normalized:
        return False
    if is_team_leader_agent_id(normalized):
        return True
    return normalized.endswith(_LEADER_NAME_SUFFIX) or normalized.endswith(
        _LEGACY_LEADER_NAME_SUFFIX,
    )


def team_roster_for_leader_agent(leader_agent_id: str | None) -> list[str] | None:
    """Return worker names for a team leader agent, or ``None`` if not a leader."""
    normalized = str(leader_agent_id or "").strip()
    if not normalized or not is_team_leader_agent_id(normalized):
        return None
    for team in store.list_items("teams"):
        stored = str(team.get("leader_agent_id") or "").strip()
        if stored == normalized:
            return [
                str(name).strip()
                for name in (team.get("members") or [])
                if str(name).strip()
            ]
    return []


def agent_matches_team_roster(resolved_agent_id: str, roster: list[str]) -> bool:
    """True when *resolved_agent_id* maps to a worker on *roster*."""
    agent_id = str(resolved_agent_id or "").strip()
    if not agent_id or not roster:
        return False
    roster_keys = {name.casefold() for name in roster if name.strip()}
    if agent_id.casefold() in roster_keys:
        return True
    try:
        cfg = load_agent_config(agent_id)
        display = str(cfg.name or "").strip()
        if display and display.casefold() in roster_keys:
            return True
    except Exception:  # noqa: BLE001 - best-effort roster match
        pass
    for name in roster:
        worker_id = _resolve_worker_agent_id(name)
        if worker_id and worker_id == agent_id:
            return True
    return False


def format_team_roster_hint(roster: list[str]) -> str:
    """Human-readable roster for delegation error messages."""
    parts: list[str] = []
    for name in roster:
        agent_id = _resolve_worker_agent_id(name)
        if agent_id:
            parts.append(f"{name} ({agent_id})")
        else:
            parts.append(name)
    return ", ".join(parts) if parts else "(none configured)"


def team_roster_for_worker_agent(worker_agent_id: str | None) -> list[str] | None:
    """Return roster when *worker_agent_id* is a team worker, else ``None``."""
    normalized = str(worker_agent_id or "").strip()
    if not normalized or is_team_leader_agent_id(normalized):
        return None
    for team in store.list_items("teams"):
        roster = [
            str(name).strip()
            for name in (team.get("members") or [])
            if str(name).strip()
        ]
        if roster and agent_matches_team_roster(normalized, roster):
            return roster
    return None


def team_delegation_role(agent_id: str | None) -> str | None:
    """Return ``leader`` or ``worker`` when *agent_id* is under team delegation rules."""
    normalized = str(agent_id or "").strip()
    if not normalized:
        return None
    if team_roster_for_leader_agent(normalized) is not None:
        return "leader"
    if team_roster_for_worker_agent(normalized) is not None:
        return "worker"
    return None


def _load_team_leader_soul_template(language: str) -> str:
    """Load the built-in orchestrator SOUL template for *language*."""
    lang = normalize_agent_language(language)
    template_root = _AGENTS_ROOT / "md_files" / _TEAM_LEADER_TEMPLATE_ID
    for lang_opt in _template_fallback_language_order(lang):
        candidate = template_root / lang_opt / "SOUL.md"
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError(
        f"Team leader SOUL template not found under {template_root}",
    )


def _render_leader_soul(team_prompt: str, *, language: str) -> str:
    """Compose SOUL from the built-in template plus optional team context."""
    template = _load_team_leader_soul_template(language).rstrip()
    custom = (team_prompt or "").strip()
    if not custom:
        return f"{template}\n"
    lang = normalize_agent_language(language)
    header = _TEAM_PROMPT_SECTION_HEADERS.get(
        lang,
        _TEAM_PROMPT_SECTION_HEADERS["en"],
    )
    return f"{template}\n\n{header}\n\n{custom}\n"


def _resolve_worker_agent_id(name: str) -> str | None:
    """Best-effort, read-only lookup of a worker's real agent id by name."""
    trimmed = str(name or "").strip()
    if not trimmed:
        return None
    try:
        from .employee_agents import _match_agent_id_by_display_name

        profiles = load_config().agents.profiles
        return _match_agent_id_by_display_name(trimmed, profiles)
    except Exception:  # noqa: BLE001 - rendering must never fail provisioning
        return None


def _render_worker_lines(workers: list[str]) -> str:
    if not workers:
        return "- （暂无，请在团队设置中添加执行者）"
    lines = []
    for name in workers:
        agent_id = _resolve_worker_agent_id(name)
        if agent_id:
            lines.append(f"- {name} — agent id: `{agent_id}`")
        else:
            lines.append(f"- {name}")
    return "\n".join(lines)


def _render_leader_profile(
    team_name: str,
    team_id: str,
    workers: list[str],
) -> str:
    worker_lines = _render_worker_lines(workers)
    wait_seconds = int(ASYNC_WORKER_WAIT_S)
    return f"""---
summary: "团队 Leader 身份"
read_when:
  - 手动引导工作区
---

## 身份

- **名字：** {team_leader_display_name(team_name)}
- **定位：** {team_name} 团队 leader
- **团队 ID：** `{team_id}`
- **类型：** 隐藏 leader Agent（不出现在员工广场）

## 团队成员（Workers）

{worker_lines}

### 行为准则

- 你是本团队的 Leader，只负责协调与派工，不亲自执行具体任务。
- 派工时调用同步工具 `chat_with_agent` 咨询成员，`to_agent` **只能**传上方列表中成员的 agent id（推荐）或成员名称（如「研究员」）；不得派工给团队外智能体。
- `chat_with_agent` 会**等待该成员完成并把其完整回复返回给你**，你据此继续推理；系统会自动把任务绑定到该成员会话，无需你手动指定 `session_id`。
- 需要多位成员且任务可并行时，**在同一步一次性发起多个** `chat_with_agent`（系统会并行执行）；有依赖关系时按规划 → 执行 → 汇总顺序依次调用。每位成员的产出会实时显示在其对应气泡。
- 估算成员所需时间并通过 `timeout` 适当放大，深度任务建议设为 {wait_seconds} 秒左右，避免提前超时。
- 收齐所有需要的成员回复后，**由你直接撰写面向用户的最终综述**（基于成员真实回复，不要编造），写完即结束，无需再调用任何工具。
- **不要**使用 `submit_to_agent` 或 `check_agent_task`（后台异步会让本轮在成员完成前提前结束）。
- **不要自行拼造 agent id**（例如把名字和团队编号拼在一起）；如不确定，先调用 `list_agents` 查询真实 id（该工具仅返回本团队成员，不得派工给团队外智能体）。
- 用户用中文提问时，全文使用中文回复。
"""


def _ensure_leader_runtime_workspace(
    workspace_dir: Path,
    *,
    language: str,
    team_name: str,
    team_id: str,
    team_prompt: str,
    workers: list[str],
) -> None:
    """Ensure leader workspace has runtime dirs and team-specific markdown."""
    workspace_dir.mkdir(parents=True, exist_ok=True)
    _initialize_agent_workspace(
        workspace_dir,
        skill_names=_TEAM_LEADER_SKILLS,
        language=language,
    )
    _write_leader_workspace(
        workspace_dir,
        language=language,
        team_name=team_name,
        team_id=team_id,
        team_prompt=team_prompt,
        workers=workers,
    )
    _finalize_leader_workspace(workspace_dir)


def _finalize_leader_workspace(workspace_dir: Path) -> None:
    """Skip generic agent bootstrap for pre-configured team leader orchestrators."""
    from ..agents.utils.setup_utils import _remove_bootstrap_from_workspace

    _remove_bootstrap_from_workspace(workspace_dir)
    flag = workspace_dir / ".bootstrap_completed"
    try:
        flag.touch(exist_ok=True)
    except OSError as exc:
        logger.warning(
            "Could not mark bootstrap completed for leader %s: %s",
            workspace_dir,
            exc,
        )


def _write_leader_workspace(
    workspace_dir: Path,
    *,
    language: str,
    team_name: str,
    team_id: str,
    team_prompt: str,
    workers: list[str],
) -> None:
    workspace_dir.mkdir(parents=True, exist_ok=True)
    soul_path = workspace_dir / "SOUL.md"
    profile_path = workspace_dir / "PROFILE.md"
    meta_path = workspace_dir / "TEAM_LEADER.json"
    soul_content = _render_leader_soul(team_prompt, language=language)
    profile_content = _render_leader_profile(team_name, team_id, workers)
    meta_content = (
        '{"is_team_leader":true,"hidden":true,"team_id":"'
        + team_id.replace("\\", "\\\\").replace('"', '\\"')
        + '"}'
    )
    for path, content in (
        (soul_path, soul_content),
        (profile_path, profile_content),
        (meta_path, meta_content),
    ):
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            path.write_text(content, encoding="utf-8")


def _sync_leader_agent_config(
    agent_id: str,
    *,
    display_name: str,
    team_name: str,
    description: str,
) -> None:
    try:
        agent_config = load_agent_config(agent_id)
    except Exception:  # noqa: BLE001
        return

    updated = False
    if (agent_config.name or "").strip() != display_name:
        agent_config.name = display_name
        updated = True
    desc = description or f"{team_name} 团队 leader"
    if (agent_config.description or "").strip() != desc:
        agent_config.description = desc
        updated = True
    if _enforce_leader_tools_config(agent_config):
        updated = True
    cap = _TEAM_LEADER_MAX_ITERS
    running = getattr(agent_config, "running", None)
    if running is None:
        agent_config.running = AgentsRunningConfig(max_iters=cap)
        updated = True
    elif getattr(running, "max_iters", cap) != cap:
        running.max_iters = cap
        updated = True
    if updated:
        save_agent_config(agent_id, agent_config)


def _create_leader_agent_profile(
    *,
    agent_id: str,
    team_name: str,
    team_id: str,
    team_prompt: str,
    workers: list[str],
) -> None:
    config = load_config()
    existing_ids = set(config.agents.profiles.keys())
    display_name = team_leader_display_name(team_name)
    description = (team_prompt or "").strip() or f"{team_name} 团队 leader"

    workspace_dir = Path(WORKING_DIR) / "workspaces" / agent_id
    language = normalize_agent_language(config.agents.language or "zh")
    signature = _leader_sync_signature(team_name, team_id, team_prompt, workers)

    if agent_id in existing_ids:
        if _synced_leader_signatures.get(agent_id) == signature:
            # Already synced with these exact inputs in this process -- skip the
            # workspace re-init / config rewrite on the hot team-run path.
            return
        _ensure_leader_runtime_workspace(
            workspace_dir,
            language=language,
            team_name=team_name,
            team_id=team_id,
            team_prompt=team_prompt,
            workers=workers,
        )
        _sync_leader_agent_config(
            agent_id,
            display_name=display_name,
            team_name=team_name,
            description=description,
        )
        _synced_leader_signatures[agent_id] = signature
        return

    _ensure_leader_runtime_workspace(
        workspace_dir,
        language=language,
        team_name=team_name,
        team_id=team_id,
        team_prompt=team_prompt,
        workers=workers,
    )

    agent_config = AgentProfileConfig(
        id=agent_id,
        name=display_name,
        description=description,
        workspace_dir=str(workspace_dir),
        language=language,
        channels=ChannelConfig(),
        mcp=MCPConfig(),
        heartbeat=HeartbeatConfig(),
        tools=_team_leader_tools_config(),
        running=AgentsRunningConfig(max_iters=_TEAM_LEADER_MAX_ITERS),
    )
    agent_ref = AgentProfileRef(
        id=agent_id,
        workspace_dir=str(workspace_dir),
        enabled=True,
    )

    config.agents.profiles[agent_id] = agent_ref
    order = list(config.agents.agent_order or [])
    if agent_id not in order:
        order.append(agent_id)
    config.agents.agent_order = order
    save_config(config)
    save_agent_config(agent_id, agent_config)
    _synced_leader_signatures[agent_id] = signature
    logger.info("Provisioned team leader agent %s for team %r", agent_id, team_name)


def provision_team_leader_agent(
    *,
    team_id: str,
    team_name: str,
    team_prompt: str,
    workers: list[str] | None = None,
    agent_id: str | None = None,
) -> dict[str, str]:
    """Create or refresh the hidden leader agent for a team."""
    trimmed_name = str(team_name or "").strip()
    if not trimmed_name:
        raise ValueError("team_name is required")
    resolved_id = str(agent_id or "").strip()
    if not resolved_id or not is_team_leader_agent_id(resolved_id):
        resolved_id = team_leader_agent_id(team_id)
    worker_names = [str(n).strip() for n in (workers or []) if str(n).strip()]
    _create_leader_agent_profile(
        agent_id=resolved_id,
        team_name=trimmed_name,
        team_id=team_id,
        team_prompt=str(team_prompt or ""),
        workers=worker_names,
    )
    return {
        "agent_id": resolved_id,
        "leader_name": team_leader_display_name(trimmed_name),
    }


def sync_team_leader_agent(team: dict[str, Any]) -> dict[str, str]:
    """Ensure leader agent exists and matches team record."""
    team_id = str(team.get("id") or "").strip()
    team_name = str(team.get("name") or "").strip()
    if not team_id or not team_name:
        raise ValueError("team id and name are required")
    stored_id = str(team.get("leader_agent_id") or "").strip()
    agent_id = (
        stored_id
        if stored_id and is_team_leader_agent_id(stored_id)
        else team_leader_agent_id(team_id)
    )
    return provision_team_leader_agent(
        team_id=team_id,
        team_name=team_name,
        team_prompt=str(team.get("desc") or ""),
        workers=list(team.get("members") or []),
        agent_id=agent_id,
    )


def delete_team_leader_agent(team: dict[str, Any]) -> None:
    """Remove hidden leader profile when a team is deleted."""
    agent_id = str(team.get("leader_agent_id") or "").strip()
    if not agent_id:
        agent_id = team_leader_agent_id(str(team.get("id") or ""))
    config = load_config()
    if agent_id not in config.agents.profiles:
        return
    if agent_id == "default":
        return
    agent_ref = config.agents.profiles.get(agent_id)
    workspace_dir = Path(
        getattr(agent_ref, "workspace_dir", None) or f"{WORKING_DIR}/workspaces/{agent_id}"
    )
    if workspace_dir.exists():
        try:
            shutil.rmtree(workspace_dir)
        except OSError:
            logger.warning("Failed to remove workspace dir %s", workspace_dir)
    # agent.json is saved inside workspace_dir by save_agent_config; rm tree covers it.
    del config.agents.profiles[agent_id]
    config.agents.agent_order = [
        item for item in (config.agents.agent_order or []) if item != agent_id
    ]
    save_config(config)
    invalidate_leader_sync_cache(agent_id)
    logger.info("Removed team leader agent %s", agent_id)
