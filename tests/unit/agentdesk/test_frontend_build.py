# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

import pytest

from qwenpaw.agentdesk import frontend_build


def test_should_build_when_output_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    web_dir = tmp_path / "web"
    src_dir = web_dir / "src"
    src_dir.mkdir(parents=True)
    (src_dir / "App.tsx").write_text("export default function App() {}", encoding="utf-8")
    out_dir = tmp_path / "static_next"

    monkeypatch.delenv("AGENTDESK_SKIP_FRONTEND_BUILD", raising=False)
    monkeypatch.delenv("AGENTDESK_FRONTEND_DIR", raising=False)
    monkeypatch.delenv("AGENTDESK_FRONTEND_NEXT", raising=False)

    assert frontend_build.should_build_frontend(web_dir=web_dir, output_dir=out_dir) is True


def test_should_not_build_when_output_is_fresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    web_dir = tmp_path / "web"
    src_dir = web_dir / "src"
    src_dir.mkdir(parents=True)
    source = src_dir / "App.tsx"
    source.write_text("v1", encoding="utf-8")

    out_dir = tmp_path / "static_next"
    out_dir.mkdir()
    index = out_dir / "index.html"
    index.write_text("<html></html>", encoding="utf-8")
    os.utime(index, (source.stat().st_mtime + 10, source.stat().st_mtime + 10))

    monkeypatch.delenv("AGENTDESK_SKIP_FRONTEND_BUILD", raising=False)
    monkeypatch.delenv("AGENTDESK_FRONTEND_DIR", raising=False)
    monkeypatch.delenv("AGENTDESK_FRONTEND_NEXT", raising=False)

    assert frontend_build.should_build_frontend(web_dir=web_dir, output_dir=out_dir) is False


def test_should_build_when_source_newer_than_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_dir = tmp_path / "web"
    src_dir = web_dir / "src"
    src_dir.mkdir(parents=True)
    source = src_dir / "App.tsx"
    source.write_text("v1", encoding="utf-8")

    out_dir = tmp_path / "static_next"
    out_dir.mkdir()
    index = out_dir / "index.html"
    index.write_text("<html></html>", encoding="utf-8")
    os.utime(index, (source.stat().st_mtime - 10, source.stat().st_mtime - 10))

    monkeypatch.delenv("AGENTDESK_SKIP_FRONTEND_BUILD", raising=False)
    monkeypatch.delenv("AGENTDESK_FRONTEND_DIR", raising=False)
    monkeypatch.delenv("AGENTDESK_FRONTEND_NEXT", raising=False)

    assert frontend_build.should_build_frontend(web_dir=web_dir, output_dir=out_dir) is True


def test_skip_build_when_env_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    web_dir = tmp_path / "web"
    web_dir.mkdir()
    out_dir = tmp_path / "static_next"

    monkeypatch.setenv("AGENTDESK_SKIP_FRONTEND_BUILD", "1")
    assert frontend_build.should_build_frontend(web_dir=web_dir, output_dir=out_dir) is False


def test_ensure_frontend_built_force_rebuilds_when_fresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    web_dir = tmp_path / "web"
    src_dir = web_dir / "src"
    src_dir.mkdir(parents=True)
    source = src_dir / "App.tsx"
    source.write_text("v1", encoding="utf-8")
    (web_dir / "package.json").write_text("{}", encoding="utf-8")

    out_dir = tmp_path / "static_next"
    out_dir.mkdir()
    index = out_dir / "index.html"
    index.write_text("<html></html>", encoding="utf-8")
    os.utime(index, (source.stat().st_mtime + 10, source.stat().st_mtime + 10))

    monkeypatch.setattr(frontend_build, "_WEB_DIR", web_dir)
    monkeypatch.setattr(frontend_build, "_STATIC_NEXT_DIR", out_dir)
    monkeypatch.delenv("AGENTDESK_SKIP_FRONTEND_BUILD", raising=False)
    monkeypatch.delenv("AGENTDESK_FRONTEND_DIR", raising=False)
    monkeypatch.delenv("AGENTDESK_FRONTEND_NEXT", raising=False)

    build_calls: list[list[str]] = []

    def fake_run_npm(npm: str, args: list[str], *, cwd: Path) -> None:
        build_calls.append(args)
        (out_dir / "index.html").write_text("<html>rebuilt</html>", encoding="utf-8")

    monkeypatch.setattr(frontend_build, "_find_npm", lambda: "npm")
    monkeypatch.setattr(frontend_build, "_run_npm", fake_run_npm)
    (web_dir / "node_modules").mkdir()

    assert frontend_build.should_build_frontend(web_dir=web_dir, output_dir=out_dir) is False
    assert frontend_build.ensure_frontend_built(force=True) is True
    assert build_calls == [["run", "build"]]


def test_skip_env_overrides_force_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "static_next"
    out_dir.mkdir()
    index = out_dir / "index.html"
    index.write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(frontend_build, "_STATIC_NEXT_DIR", out_dir)
    monkeypatch.setenv("AGENTDESK_SKIP_FRONTEND_BUILD", "1")

    build_called = False

    def fake_run_npm(npm: str, args: list[str], *, cwd: Path) -> None:
        nonlocal build_called
        build_called = True

    monkeypatch.setattr(frontend_build, "_find_npm", lambda: "npm")
    monkeypatch.setattr(frontend_build, "_run_npm", fake_run_npm)

    assert frontend_build.ensure_frontend_built(force=True) is True
    assert build_called is False
