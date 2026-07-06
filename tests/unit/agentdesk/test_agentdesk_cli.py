# -*- coding: utf-8 -*-
import os

import pytest
from click.testing import CliRunner

from qwenpaw.__version__ import __version__
from qwenpaw.cli.main import LAZY_SUBCOMMANDS, cli as qwenpaw_cli
from qwenpaw.agentdesk.branding import rebrand_user_text
from qwenpaw.agentdesk.cli import cli


def test_agentdesk_cli_help() -> None:
    result = CliRunner().invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "AgentDesk" in result.output
    assert "agentdesk skills list" in result.output
    assert "agentdesk kill" in result.output
    assert "agentdesk init" in result.output


def test_agentdesk_cli_version() -> None:
    result = CliRunner().invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_agentdesk_cli_exposes_qwenpaw_subcommands() -> None:
    runner = CliRunner()
    agentdesk_commands = set(runner.invoke(cli, ["--help"]).output.split())
    qwenpaw_commands = set(runner.invoke(qwenpaw_cli, ["--help"]).output.split())

    for command in sorted(LAZY_SUBCOMMANDS):
        assert command in agentdesk_commands
        assert command in qwenpaw_commands


def test_agentdesk_app_enables_agentdesk_mode(monkeypatch) -> None:
    monkeypatch.delenv("AGENTDESK_ENABLED", raising=False)
    monkeypatch.setattr("qwenpaw.cli.app_cmd.uvicorn.run", lambda *a, **k: None)
    build_calls: list[bool] = []
    monkeypatch.setattr(
        "qwenpaw.agentdesk.frontend_build.ensure_frontend_built",
        lambda *, force=False: build_calls.append(force) or True,
    )

    result = CliRunner().invoke(cli, ["app"])

    assert result.exit_code == 0
    assert os.environ.get("AGENTDESK_ENABLED") == "1"
    assert build_calls == [False]


def test_agentdesk_app_rebuild_frontend_flag(monkeypatch) -> None:
    monkeypatch.delenv("AGENTDESK_ENABLED", raising=False)
    monkeypatch.setattr("qwenpaw.cli.app_cmd.uvicorn.run", lambda *a, **k: None)
    build_calls: list[bool] = []
    monkeypatch.setattr(
        "qwenpaw.agentdesk.frontend_build.ensure_frontend_built",
        lambda *, force=False: build_calls.append(force) or True,
    )

    result = CliRunner().invoke(cli, ["app", "--rebuild-frontend"])

    assert result.exit_code == 0
    assert build_calls == [True]


def test_agentdesk_default_invocation_starts_app(monkeypatch) -> None:
    monkeypatch.delenv("AGENTDESK_ENABLED", raising=False)
    monkeypatch.setattr("qwenpaw.cli.app_cmd.uvicorn.run", lambda *a, **k: None)
    build_calls: list[bool] = []
    monkeypatch.setattr(
        "qwenpaw.agentdesk.frontend_build.ensure_frontend_built",
        lambda *, force=False: build_calls.append(force) or True,
    )

    result = CliRunner().invoke(cli, [])

    assert result.exit_code == 0
    assert os.environ.get("AGENTDESK_ENABLED") == "1"
    assert build_calls == [False]


def test_agentdesk_skills_subcommand_loads() -> None:
    result = CliRunner().invoke(cli, ["skills", "--help"])

    assert result.exit_code == 0
    assert "list" in result.output


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("qwenpaw cron list", "agentdesk cron list"),
        ("QwenPaw Console", "AgentDesk Console"),
        ("copaw skills import", "agentdesk skills import"),
        ("  qwenpaw:\n    emoji: ⏰", "  agentdesk:\n    emoji: ⏰"),
    ],
)
def test_rebrand_user_text(original: str, expected: str) -> None:
    assert rebrand_user_text(original) == expected
