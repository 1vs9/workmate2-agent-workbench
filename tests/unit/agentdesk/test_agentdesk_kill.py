# -*- coding: utf-8 -*-
from __future__ import annotations

from click.testing import CliRunner

from qwenpaw.cli.main import cli as qwenpaw_cli
from qwenpaw.cli.process_utils import _is_agentdesk_wrapper_process
from qwenpaw.agentdesk.cli import cli as agentdesk_cli
from qwenpaw.agentdesk.kill_cmd import _find_agentdesk_wrapper_pids


def test_agentdesk_kill_help() -> None:
    result = CliRunner().invoke(agentdesk_cli, ["kill", "--help"])

    assert result.exit_code == 0
    assert "Stop running AgentDesk processes" in result.output


def test_agentdesk_help_lists_kill_command() -> None:
    result = CliRunner().invoke(agentdesk_cli, ["--help"])

    assert result.exit_code == 0
    assert "kill" in result.output
    assert "agentdesk kill" in result.output


def test_qwenpaw_cli_does_not_expose_kill() -> None:
    result = CliRunner().invoke(qwenpaw_cli, ["--help"])

    assert result.exit_code == 0
    assert "shutdown" in result.output
    assert "\n  kill " not in f"\n{result.output}\n"


def test_agentdesk_kill_stops_backend_and_wrappers(monkeypatch) -> None:
    monkeypatch.setattr(
        "qwenpaw.agentdesk.kill_cmd._listening_pids_for_port",
        lambda _port: {4242},
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.kill_cmd._find_agentdesk_frontend_dev_pids",
        set,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.kill_cmd._find_desktop_wrapper_pids",
        set,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.kill_cmd._find_agentdesk_wrapper_pids",
        lambda: {1052},
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.kill_cmd._find_windows_wrapper_ancestor_pids",
        lambda _pids: set(),
    )
    monkeypatch.setattr(
        "qwenpaw.cli.shutdown_cmd._terminate_pid",
        lambda _pid: True,
    )

    result = CliRunner().invoke(agentdesk_cli, ["kill"])

    assert result.exit_code == 0
    assert "4242" in result.output
    assert "1052" in result.output
    assert "Stopped AgentDesk processes" in result.output


def test_agentdesk_kill_reports_nothing_found(monkeypatch) -> None:
    monkeypatch.setattr(
        "qwenpaw.agentdesk.kill_cmd._listening_pids_for_port",
        lambda _port: set(),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.kill_cmd._find_agentdesk_frontend_dev_pids",
        set,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.kill_cmd._find_desktop_wrapper_pids",
        set,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.kill_cmd._find_agentdesk_wrapper_pids",
        set,
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.kill_cmd._find_windows_wrapper_ancestor_pids",
        lambda _pids: set(),
    )

    result = CliRunner().invoke(agentdesk_cli, ["kill"])

    assert result.exit_code != 0
    assert "No running AgentDesk" in result.output


def test_is_agentdesk_wrapper_process_detects_bare_invocation() -> None:
    assert _is_agentdesk_wrapper_process("agentdesk.exe", r"C:\Tools\agentdesk.exe")
    assert _is_agentdesk_wrapper_process(
        "python.exe",
        "python -m qwenpaw.agentdesk.cli",
    )


def test_is_agentdesk_wrapper_process_ignores_kill_command() -> None:
    assert not _is_agentdesk_wrapper_process(
        "agentdesk.exe",
        r"C:\Tools\agentdesk.exe kill",
    )


def test_find_agentdesk_wrapper_pids_on_windows(monkeypatch) -> None:
    monkeypatch.setattr("qwenpaw.agentdesk.kill_cmd.sys.platform", "win32")
    monkeypatch.setattr(
        "qwenpaw.agentdesk.kill_cmd._windows_process_snapshot",
        lambda: {
            1052: (900, "agentdesk.exe", r"C:\Tools\agentdesk.exe"),
            24692: (1052, "python.exe", "python -m uvicorn qwenpaw.app"),
            3001: (900, "agentdesk.exe", r"C:\Tools\agentdesk.exe kill"),
        },
    )

    assert _find_agentdesk_wrapper_pids() == {1052}
