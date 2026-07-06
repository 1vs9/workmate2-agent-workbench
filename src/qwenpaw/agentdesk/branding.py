# -*- coding: utf-8 -*-
"""User-visible AgentDesk rebranding helpers."""

from __future__ import annotations

from pathlib import Path

from .settings import is_agentdesk_enabled

_TEXT_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("QwenPaw", "AgentDesk"),
    ("qwenpaw", "agentdesk"),
    ("CoPaw", "AgentDesk"),
    ("copaw", "agentdesk"),
)

_TEXT_EXTENSIONS = frozenset(
    {
        ".md",
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".py",
        ".sh",
        ".bat",
        ".ps1",
    },
)


def rebrand_user_text(text: str) -> str:
    """Replace QwenPaw/CoPaw branding with AgentDesk in user-facing strings."""
    updated = text
    for old, new in _TEXT_REPLACEMENTS:
        updated = updated.replace(old, new)
    return updated


def should_rebrand_skills() -> bool:
    """Return True when builtin skills should be copied with AgentDesk branding."""
    return is_agentdesk_enabled()


def rebrand_skill_directory(skill_dir: Path) -> None:
    """Rewrite text artifacts inside a skill directory for AgentDesk branding."""
    for path in skill_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _TEXT_EXTENSIONS and path.name != "SKILL.md":
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        updated = rebrand_user_text(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
