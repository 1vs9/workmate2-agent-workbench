# -*- coding: utf-8 -*-
"""Shared agent provisioning utilities for native and AgentDesk flows."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from ..agents.skill_system import SkillPoolService, get_workspace_skills_dir
from ..agents.utils import copy_workspace_md_files, normalize_agent_language
from ..config.config import (
    AgentProfileConfig,
    AgentProfileRef,
    ChannelConfig,
    HeartbeatConfig,
    MCPConfig,
    ModelSlotConfig,
    ToolsConfig,
    generate_short_agent_id,
    save_agent_config,
    validate_agent_id,
)
from ..config.utils import load_config, save_config
from ..constant import WORKING_DIR

logger = logging.getLogger(__name__)


def normalized_agent_order(config) -> list[str]:
    """Return a deduplicated agent order covering every configured agent."""
    profile_ids = list(config.agents.profiles.keys())
    ordered_ids: list[str] = []

    for agent_id in config.agents.agent_order:
        if agent_id in config.agents.profiles and agent_id not in ordered_ids:
            ordered_ids.append(agent_id)

    for agent_id in profile_ids:
        if agent_id not in ordered_ids:
            ordered_ids.append(agent_id)

    return ordered_ids


def _generate_unique_id(existing_ids: set[str]) -> str:
    """Generate a unique random short agent ID."""
    max_attempts = 10
    for _ in range(max_attempts):
        candidate_id = generate_short_agent_id()
        if candidate_id not in existing_ids:
            return candidate_id
    raise RuntimeError("Failed to generate unique agent ID after 10 attempts")


def _apply_workspace_md_templates(
    workspace_dir: Path,
    language: str,
    *,
    md_template_id: str | None,
) -> None:
    """Copy common and template-specific markdown files for a workspace."""
    copy_workspace_md_files(
        language,
        workspace_dir,
        md_template_id=md_template_id,
    )


def _ensure_heartbeat_file(workspace_dir: Path, language: str) -> None:
    """Create the default HEARTBEAT.md if it is missing."""
    heartbeat_file = workspace_dir / "HEARTBEAT.md"
    if heartbeat_file.exists():
        return

    default_heartbeat_mds = {
        "zh": """# Heartbeat checklist
- 扫描收件箱紧急邮件
- 查看未来 2h 的日历
- 检查待办是否卡住
- 若安静超过 8h，轻量 check-in
""",
        "en": """# Heartbeat checklist
- Scan inbox for urgent email
- Check calendar for next 2h
- Check tasks for blockers
- Light check-in if quiet for 8h
""",
        "ru": """# Heartbeat checklist
- Проверить входящие на срочные письма
- Просмотреть календарь на ближайшие 2 часа
- Проверить задачи на наличие блокировок
- Лёгкая проверка при отсутствии активности более 8 часов
""",
    }
    heartbeat_content = default_heartbeat_mds.get(
        language,
        default_heartbeat_mds["en"],
    )
    with open(heartbeat_file, "w", encoding="utf-8") as file:
        file.write(heartbeat_content.strip())


def _install_initial_skills(
    workspace_dir: Path,
    skill_names: list[str] | None,
) -> None:
    """Install requested initial skills from the skill pool."""
    if not skill_names:
        return

    pool_service = SkillPoolService()
    for skill_name in skill_names:
        try:
            result = pool_service.download_to_workspace(
                skill_name=skill_name,
                workspace_dir=workspace_dir,
                overwrite=False,
            )
            if result.get("success"):
                continue
            logger.warning(
                "Failed to install initial skill %s for %s: %s",
                skill_name,
                workspace_dir,
                result.get("reason", "unknown"),
            )
        except Exception as e:
            logger.warning(
                "Failed to install initial skill %s for %s: %s",
                skill_name,
                workspace_dir,
                e,
            )


def _initialize_agent_workspace(
    workspace_dir: Path,
    skill_names: list[str] | None = None,
    md_template_id: str | None = None,
    language: str | None = None,
) -> None:
    """Initialize agent workspace with only explicitly requested skills."""
    from ..config import load_config as load_global_config

    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (workspace_dir / "memory").mkdir(parents=True, exist_ok=True)
    get_workspace_skills_dir(workspace_dir).mkdir(parents=True, exist_ok=True)

    config = load_global_config()
    if not language:
        language = config.agents.language or "zh"

    _apply_workspace_md_templates(
        workspace_dir,
        language,
        md_template_id=md_template_id,
    )
    _ensure_heartbeat_file(workspace_dir, language)
    _install_initial_skills(workspace_dir, skill_names)

    jobs_file = workspace_dir / "jobs.json"
    if not jobs_file.exists():
        with open(jobs_file, "w", encoding="utf-8") as file:
            json.dump(
                {"version": 1, "jobs": []},
                file,
                ensure_ascii=False,
                indent=2,
            )

    chats_file = workspace_dir / "chats.json"
    if not chats_file.exists():
        with open(chats_file, "w", encoding="utf-8") as file:
            json.dump(
                {"version": 1, "chats": []},
                file,
                ensure_ascii=False,
                indent=2,
            )


def provision_agent_profile(
    *,
    name: str,
    description: str = "",
    requested_id: str | None = None,
    workspace_dir: str | Path | None = None,
    language: str | None = None,
    skill_names: list[str] | None = None,
    active_model: ModelSlotConfig | None = None,
    post_workspace_init: Callable[[Path, str], None] | None = None,
) -> AgentProfileRef:
    """Provision and persist an agent profile.

    Raises:
        ValueError: Invalid requested_id.
        RuntimeError: Failed to allocate a unique ID.
    """
    config = load_config()
    existing_ids = set(config.agents.profiles.keys())

    if requested_id:
        validate_agent_id(requested_id, existing_ids)
        agent_id = requested_id
    else:
        agent_id = _generate_unique_id(existing_ids)

    resolved_workspace = Path(
        workspace_dir or f"{WORKING_DIR}/workspaces/{agent_id}",
    ).expanduser()
    resolved_workspace.mkdir(parents=True, exist_ok=True)

    resolved_language = normalize_agent_language(
        language or config.agents.language or "en",
    )

    agent_config = AgentProfileConfig(
        id=agent_id,
        name=name,
        description=description,
        workspace_dir=str(resolved_workspace),
        language=resolved_language,
        channels=ChannelConfig(),
        mcp=MCPConfig(),
        heartbeat=HeartbeatConfig(),
        tools=ToolsConfig(),
        active_model=active_model,
    )

    _initialize_agent_workspace(
        resolved_workspace,
        skill_names=skill_names if skill_names is not None else [],
        language=resolved_language,
    )

    if post_workspace_init is not None:
        post_workspace_init(resolved_workspace, agent_id)

    agent_ref = AgentProfileRef(
        id=agent_id,
        workspace_dir=str(resolved_workspace),
        enabled=True,
    )

    config.agents.profiles[agent_id] = agent_ref
    config.agents.agent_order = normalized_agent_order(config)
    save_config(config)
    save_agent_config(agent_id, agent_config)
    return agent_ref
