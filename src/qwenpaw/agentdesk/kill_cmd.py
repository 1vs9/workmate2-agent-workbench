# -*- coding: utf-8 -*-
"""Stop running AgentDesk backend, dev server, and CLI wrapper processes."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

import sys

from qwenpaw.cli.process_utils import (
    _is_agentdesk_wrapper_process,
    _process_table,
    _windows_process_snapshot,
)
from qwenpaw.cli.shutdown_cmd import (
    _backend_port,
    _find_desktop_wrapper_pids,
    _find_windows_wrapper_ancestor_pids,
    _listening_pids_for_port,
    _stop_pid_set,
)

_AGENTDESK_WEB_DIR = (Path(__file__).resolve().parent / "web").resolve()


def _find_agentdesk_frontend_dev_pids() -> set[int]:
    """Find Vite dev-server processes for the AgentDesk web app."""
    web_dir = str(_AGENTDESK_WEB_DIR).lower()
    matches: set[int] = set()
    for pid, command in _process_table():
        lowered = command.lower()
        if "vite" in lowered and web_dir in lowered:
            matches.add(pid)
            continue
        if "agentdesk" in lowered and (
            "npm run dev" in lowered
            or "pnpm run dev" in lowered
            or "yarn dev" in lowered
        ):
            matches.add(pid)
    return matches


def _find_agentdesk_wrapper_pids() -> set[int]:
    """Find ``agentdesk`` / ``agentdesk app`` CLI wrapper processes."""
    matches: set[int] = set()
    if sys.platform == "win32":
        for pid, (_parent, name, command) in _windows_process_snapshot().items():
            if _is_agentdesk_wrapper_process(name, command):
                matches.add(pid)
        return matches

    for pid, command in _process_table():
        if _is_agentdesk_wrapper_process("", command):
            matches.add(pid)
    return matches


@click.command(
    "kill",
    help="Stop running AgentDesk processes (backend, dev server, wrappers).",
)
@click.option(
    "--port",
    default=None,
    type=int,
    help="Backend port to stop. Defaults to global --port from config.",
)
@click.pass_context
def kill_cmd(ctx: click.Context, port: Optional[int]) -> None:
    """Force-stop AgentDesk backend and related processes.

    Stops:
    - the API server listening on the configured port (default 8088)
    - ``npm run dev`` Vite server under ``agentdesk/web/`` when present
    - ``agentdesk app`` / desktop wrapper processes on Windows
    """
    backend_port = _backend_port(ctx, port)
    backend_pids = _listening_pids_for_port(backend_port)
    frontend_pids = _find_agentdesk_frontend_dev_pids()
    desktop_pids = _find_desktop_wrapper_pids()
    wrapper_pids = (
        _find_agentdesk_wrapper_pids()
        | _find_windows_wrapper_ancestor_pids(backend_pids)
    )

    proc_table = dict(_process_table())

    def log_pid_set(title: str, pids: set[int]) -> None:
        if not pids:
            click.echo(f"{title}: nothing to stop")
            return
        click.echo(f"{title} ({len(pids)} total):")
        for pid in sorted(pids):
            cmd = proc_table.get(pid, "<unknown command line>")
            click.echo(f"  PID {pid}: {cmd}")

    log_pid_set("Backend listener processes", backend_pids)
    log_pid_set("AgentDesk frontend dev processes", frontend_pids)
    log_pid_set("Desktop wrapper processes", desktop_pids)
    log_pid_set("AgentDesk wrapper processes", wrapper_pids)

    all_targets = backend_pids | frontend_pids | desktop_pids | wrapper_pids
    if not all_targets:
        raise click.ClickException(
            "No running AgentDesk backend/frontend process was found.",
        )

    wrapper_stopped, wrapper_failed = _stop_pid_set(wrapper_pids)
    frontend_stopped, frontend_failed = _stop_pid_set(frontend_pids)
    desktop_stopped, desktop_failed = _stop_pid_set(
        desktop_pids - set(wrapper_stopped) - set(frontend_stopped),
    )
    backend_stopped, backend_failed = _stop_pid_set(
        backend_pids
        - set(wrapper_stopped)
        - set(frontend_stopped)
        - set(desktop_stopped),
    )

    stopped = (
        wrapper_stopped + frontend_stopped + desktop_stopped + backend_stopped
    )
    failed = list(
        set(
            wrapper_failed + frontend_failed + desktop_failed + backend_failed,
        ),
    )

    if stopped:
        click.echo(
            "Stopped AgentDesk processes: "
            + ", ".join(str(pid) for pid in sorted(stopped)),
        )
    if failed:
        click.echo("Failed to stop the following processes:")
        for pid in sorted(failed):
            cmd = proc_table.get(pid, "<unknown command line>")
            click.echo(f"  PID {pid}: {cmd}")
        raise click.ClickException(
            "Failed to kill process(es): "
            + ", ".join(str(pid) for pid in sorted(failed)),
        )
