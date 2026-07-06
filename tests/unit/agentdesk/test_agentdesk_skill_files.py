# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from fastapi import HTTPException

from qwenpaw.agentdesk import skill_files


def test_build_skill_file_tree_sorts_directories_before_files(tmp_path) -> None:
    skill_root = tmp_path / "demo"
    nested = skill_root / "nested"
    nested.mkdir(parents=True)
    (skill_root / "b.txt").write_text("b", encoding="utf-8")
    (skill_root / "a.md").write_text("# A", encoding="utf-8")
    (nested / "child.txt").write_text("child", encoding="utf-8")

    assert skill_files.build_skill_file_tree(skill_root) == [
        {
            "name": "nested",
            "path": "nested",
            "type": "directory",
            "children": [
                {"name": "child.txt", "path": "child.txt", "type": "file"},
            ],
        },
        {"name": "a.md", "path": "a.md", "type": "file"},
        {"name": "b.txt", "path": "b.txt", "type": "file"},
    ]


@pytest.mark.parametrize("unsafe_path", ["../secret.txt", "/secret.txt", "C:secret.txt"])
def test_safe_skill_relative_path_rejects_escape(tmp_path, unsafe_path: str) -> None:
    skill_root = tmp_path / "demo"
    skill_root.mkdir()

    with pytest.raises(HTTPException) as exc:
        skill_files.safe_skill_relative_path(skill_root, unsafe_path)

    assert exc.value.status_code == 400


def test_read_skill_file_payload_reports_markdown(tmp_path) -> None:
    skill_root = tmp_path / "demo"
    skill_root.mkdir()
    skill_file = skill_root / "SKILL.md"
    skill_file.write_text("# Demo", encoding="utf-8")

    assert skill_files.read_skill_file_payload(
        "demo",
        "SKILL.md",
        skill_root=skill_root,
        location="workspace",
    ) == {
        "skill_name": "demo",
        "location": "workspace",
        "path": "SKILL.md",
        "content": "# Demo",
        "size": skill_file.stat().st_size,
        "is_markdown": True,
    }
