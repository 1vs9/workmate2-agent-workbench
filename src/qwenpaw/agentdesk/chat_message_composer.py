# -*- coding: utf-8 -*-
"""Compose AgentDesk user turns for QwenPaw chat execution."""

from __future__ import annotations

from pathlib import Path

import frontmatter as fm

from ..agents.skill_system.store import get_workspace_skills_dir
from ..agents.utils.file_handling import read_text_file_with_encoding_fallback
from .locale import (
    build_chat_response_language_hint,
    detect_user_language,
    is_chinese_language,
)
from .skill_wizard import (
    EMPLOYEE_CREATOR_SKILL,
    build_employee_create_agent_message,
    build_skill_find_agent_message,
    is_skill_find_message,
)


def skill_invocation_block(skill_dir: Path, user_input: str) -> str | None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return None
    raw = read_text_file_with_encoding_fallback(skill_md)
    post = fm.loads(raw)
    display_name = post.get("name") or skill_dir.name
    body = (post.content or "").strip()
    if not body:
        return None
    if is_chinese_language(detect_user_language(user_input)):
        return (
            f"使用工作区技能 `[{display_name}]`（`{skill_dir}`）完成用户任务："
            f"{user_input}\n\n{body}"
        )
    return (
        f"Use the [{display_name}] skill in `{skill_dir}` to fulfill "
        f"the user's task: {user_input}\n\n{body}"
    )


def augment_user_message_with_skills(
    workspace_dir: Path,
    user_text: str,
    skill_names: list[str],
) -> str:
    """Inject selected skill instructions into the user turn."""
    trimmed = (user_text or "").strip()
    if not trimmed or not skill_names:
        return user_text

    skill_root = get_workspace_skills_dir(workspace_dir)
    blocks: list[str] = []
    for skill_name in skill_names:
        skill_dir = skill_root / skill_name
        block = skill_invocation_block(skill_dir, trimmed)
        if block:
            blocks.append(block)

    if not blocks:
        return user_text
    if len(blocks) == 1:
        return blocks[0]
    joined = "\n\n---\n\n".join(blocks)
    return f"{joined}\n\n---\n\nUser message:\n{trimmed}"


def resolve_chat_user_messages(
    workspace_dir: Path,
    user_text: str,
    skill_names: list[str],
) -> tuple[str, str]:
    """Return ``(display_text, agent_message)`` for a composer turn."""
    display = (user_text or "").strip()
    if not display:
        return display, display

    if is_skill_find_message(display):
        hint = build_chat_response_language_hint(display)
        return display, f"{hint}{build_skill_find_agent_message(display)}"

    if EMPLOYEE_CREATOR_SKILL in skill_names:
        hint = build_chat_response_language_hint(display)
        return display, f"{hint}{build_employee_create_agent_message(display)}"

    agent = (
        augment_user_message_with_skills(workspace_dir, display, skill_names)
        if skill_names
        else display
    )
    hint = build_chat_response_language_hint(display)
    return display, f"{hint}{agent}"
