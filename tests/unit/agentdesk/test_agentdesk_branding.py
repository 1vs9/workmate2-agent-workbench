# -*- coding: utf-8 -*-
from pathlib import Path

from qwenpaw.agentdesk.branding import rebrand_skill_directory, rebrand_user_text


def test_rebrand_skill_directory_rewrites_skill_md(tmp_path: Path) -> None:
    skill_dir = tmp_path / "cron"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: cron\n"
        "description: Use qwenpaw cron list/create.\n"
        "metadata:\n"
        "  qwenpaw:\n"
        "    emoji: \"⏰\"\n"
        "---\n\n"
        "Run `qwenpaw cron list --agent-id default`.\n",
        encoding="utf-8",
    )

    rebrand_skill_directory(skill_dir)

    updated = skill_md.read_text(encoding="utf-8")
    assert "agentdesk cron" in updated
    assert "qwenpaw" not in updated
    assert "agentdesk:" in updated


def test_rebrand_user_text_preserves_unrelated_content() -> None:
    text = "Use cron for scheduling without brand names."
    assert rebrand_user_text(text) == text
