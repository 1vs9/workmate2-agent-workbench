# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from qwenpaw.agentdesk import task_workspace_routes


def test_task_workspace_tree_payload_wraps_files(monkeypatch) -> None:
    monkeypatch.setattr(
        task_workspace_routes,
        "task_workspace_tree_files",
        lambda task_id: [{"path": f"{task_id}.txt"}],
    )

    assert task_workspace_routes.task_workspace_tree_payload("task-1") == {
        "files": [{"path": "task-1.txt"}],
    }


def test_task_workspace_file_payload_reads_text(monkeypatch, tmp_path) -> None:
    file_path = tmp_path / "answer.txt"
    file_path.write_text("hello\nworld", encoding="utf-8")
    monkeypatch.setattr(
        task_workspace_routes,
        "resolve_task_workspace_file",
        lambda task_id, path: file_path,
    )

    assert task_workspace_routes.task_workspace_file_payload(
        "task-1",
        "answer.txt",
    ) == {
        "path": "answer.txt",
        "content": "hello\nworld",
        "lines": ["hello", "world"],
        "binary": False,
    }


def test_task_workspace_file_payload_marks_binary(monkeypatch, tmp_path) -> None:
    file_path = tmp_path / "blob.bin"
    file_path.write_bytes(b"\xff\xfe\x00")
    monkeypatch.setattr(
        task_workspace_routes,
        "resolve_task_workspace_file",
        lambda task_id, path: file_path,
    )

    assert task_workspace_routes.task_workspace_file_payload(
        "task-1",
        "blob.bin",
    ) == {
        "path": "blob.bin",
        "content": "",
        "lines": [],
        "binary": True,
    }


def test_reveal_task_workspace_payload_requires_path() -> None:
    with pytest.raises(HTTPException) as exc:
        task_workspace_routes.reveal_task_workspace_payload("task-1", {})

    assert exc.value.status_code == 400


def test_reveal_task_workspace_payload_reveals_file(monkeypatch, tmp_path) -> None:
    file_path = tmp_path / "answer.txt"
    file_path.write_text("hello", encoding="utf-8")
    revealed: list[Path] = []
    monkeypatch.setattr(
        task_workspace_routes,
        "resolve_task_workspace_file",
        lambda task_id, path: file_path,
    )
    monkeypatch.setattr(
        task_workspace_routes,
        "reveal_path_in_os",
        lambda path: revealed.append(path),
    )

    assert task_workspace_routes.reveal_task_workspace_payload(
        "task-1",
        {"path": "answer.txt"},
    ) == {"ok": True, "path": file_path.as_posix()}
    assert revealed == [file_path]


def test_reveal_task_workspace_payload_falls_back_to_folder(monkeypatch, tmp_path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    revealed: list[Path] = []

    def _missing(task_id: str, path: str):
        raise HTTPException(status_code=404, detail="File not found")

    monkeypatch.setattr(task_workspace_routes, "resolve_task_workspace_file", _missing)
    monkeypatch.setattr(
        task_workspace_routes,
        "task_workspace_roots",
        lambda task_id, *, persist_fallback: [root],
    )
    monkeypatch.setattr(
        task_workspace_routes,
        "reveal_path_in_os",
        lambda path: revealed.append(path),
    )

    assert task_workspace_routes.reveal_task_workspace_payload(
        "task-1",
        {"path": "missing.txt"},
    ) == {"ok": True, "path": str(root), "revealed": "folder"}
    assert revealed == [root]


def test_reveal_task_workspace_payload_preserves_non_404(monkeypatch) -> None:
    def _bad(task_id: str, path: str):
        raise HTTPException(status_code=400, detail="Bad path")

    monkeypatch.setattr(task_workspace_routes, "resolve_task_workspace_file", _bad)

    with pytest.raises(HTTPException) as exc:
        task_workspace_routes.reveal_task_workspace_payload(
            "task-1",
            {"path": "../bad"},
        )

    assert exc.value.status_code == 400
