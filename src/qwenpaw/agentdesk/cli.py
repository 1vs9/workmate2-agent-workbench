# -*- coding: utf-8 -*-
"""AgentDesk CLI — full command surface with AgentDesk branding."""

from __future__ import annotations

import os
import sys


def _bootstrap_default_data_dirs() -> None:
    """Ensure AgentDesk path defaults exist before ``constant`` resolves paths."""
    from .paths_config import ensure_default_paths_file, upgrade_legacy_saved_paths

    upgrade_legacy_saved_paths()
    ensure_default_paths_file()


_bootstrap_default_data_dirs()

import click

from ..__version__ import __version__
from ..cli.main import LAZY_SUBCOMMANDS as _QWENPAW_LAZY_SUBCOMMANDS
from ..cli.main import LazyGroup, log_init_timings
from ..config.utils import read_last_api
from ..utils.stdio import ensure_standard_streams

LAZY_SUBCOMMANDS = {
    **_QWENPAW_LAZY_SUBCOMMANDS,
    "kill": ("qwenpaw.agentdesk.kill_cmd", "kill_cmd", ".kill_cmd"),
}

if sys.platform == "win32":
    ensure_standard_streams()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def _enable_agentdesk_mode() -> None:
    os.environ["AGENTDESK_ENABLED"] = "1"


def _resolve_api_defaults(
    host: str | None,
    port: int | None,
) -> tuple[str, int]:
    last = read_last_api()
    if host is None or port is None:
        if last:
            host = host or last[0]
            port = port or last[1]
    return host or "127.0.0.1", port or 8088


@click.group(
    cls=LazyGroup,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    lazy_subcommands=LAZY_SUBCOMMANDS,
)
@click.version_option(version=__version__, prog_name="AgentDesk")
@click.option("--host", default=None, help="API Host")
@click.option(
    "--port",
    default=None,
    type=int,
    help="API Port",
)
@click.pass_context
def cli(ctx: click.Context, host: str | None, port: int | None) -> None:
    """AgentDesk — personal AI assistant with the AgentDesk Web UI.

    Full command-line control for setup, skills, channels, cron jobs,
    agents, and the embedded AgentDesk web interface.

    \b
    Examples:
      agentdesk                  # start backend + AgentDesk UI on :8088
      agentdesk app              # same as bare ``agentdesk``
      agentdesk skills list      # manage workspace skills
      agentdesk kill             # stop backend / dev server
      agentdesk init             # first-time setup
    """
    _enable_agentdesk_mode()

    host, port = _resolve_api_defaults(host, port)
    ctx.ensure_object(dict)
    ctx.obj["host"] = host
    ctx.obj["port"] = port

    if ctx.invoked_subcommand is None:
        from ..cli.app_cmd import app_cmd

        ctx.invoke(app_cmd)


__all__ = ["cli", "log_init_timings"]
