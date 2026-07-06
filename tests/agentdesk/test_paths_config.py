# -*- coding: utf-8 -*-
"""Tests for AgentDesk data directory configuration."""

from pathlib import Path

import pytest

from qwenpaw.agentdesk import paths_config


@pytest.fixture
def isolated_paths(monkeypatch, tmp_path):
    bootstrap = tmp_path / "bootstrap"
    paths_file = bootstrap / "paths.json"
    monkeypatch.setattr(paths_config, "BOOTSTRAP_DIR", bootstrap)
    monkeypatch.setattr(paths_config, "PATHS_FILE", paths_file)
    return bootstrap, paths_file


def test_suggest_paths_prefers_d_drive_on_windows(monkeypatch):
    monkeypatch.setattr(paths_config.sys, "platform", "win32")
    monkeypatch.setattr(paths_config.Path, "exists", lambda self: str(self) in {"D:/", "D:\\"})
    working, secret = paths_config.suggest_paths()
    assert working == r"D:\agentdesk"
    assert secret == r"D:\agentdesk.secret"


def test_save_and_load_paths(isolated_paths):
    _, paths_file = isolated_paths
    saved = paths_config.save_paths(str(isolated_paths[0] / "data"), "")
    assert paths_file.is_file()
    assert saved["secret_dir"].endswith(".secret")
    loaded = paths_config.load_saved_paths()
    assert loaded is not None
    assert loaded["working_dir"] == saved["working_dir"]


def test_upgrade_legacy_qwenpaw_defaults(isolated_paths, monkeypatch):
    monkeypatch.setattr(paths_config.sys, "platform", "win32")
    monkeypatch.setattr(
        paths_config.Path,
        "exists",
        lambda self: str(self).replace("\\", "/") in {"D:/", "D:\\"},
    )
    paths_config.save_paths(r"D:\qwenpaw", r"D:\qwenpaw.secret")
    assert paths_config.upgrade_legacy_saved_paths() is True
    loaded = paths_config.load_saved_paths()
    assert loaded is not None
    assert loaded["working_dir"] == r"D:\agentdesk"
    assert loaded["secret_dir"] == r"D:\agentdesk.secret"


def test_save_paths_requires_absolute_path(isolated_paths):
    with pytest.raises(ValueError, match="absolute"):
        paths_config.save_paths("relative/path", "")
