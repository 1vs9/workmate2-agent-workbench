# -*- coding: utf-8 -*-
"""Workspace memory-manager registration tests for AgentDesk mode."""

from __future__ import annotations

from pathlib import Path

from qwenpaw.app.workspace import Workspace


def _descriptor_names(workspace: Workspace) -> set[str]:
    return set(workspace._service_manager.descriptors.keys())  # pylint: disable=protected-access


def test_workspace_keeps_native_memory_registration_when_agentdesk_disabled(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv("AGENTDESK_ENABLED", "0")
    ws = Workspace(agent_id="employee_x", workspace_dir=str(tmp_path / "employee_x"))
    names = _descriptor_names(ws)
    assert "memory_manager" in names
    assert "context_manager" in names


def test_workspace_registers_memory_for_default_agent_when_agentdesk_enabled(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv("AGENTDESK_ENABLED", "1")
    ws = Workspace(agent_id="default", workspace_dir=str(tmp_path / "default"))
    names = _descriptor_names(ws)
    assert "memory_manager" in names
    assert "context_manager" in names


def test_workspace_skips_memory_for_non_default_agent_when_agentdesk_enabled(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setenv("AGENTDESK_ENABLED", "1")
    ws = Workspace(agent_id="employee_y", workspace_dir=str(tmp_path / "employee_y"))
    names = _descriptor_names(ws)
    assert "memory_manager" not in names
    # Context manager still remains available for short-term/session behavior.
    assert "context_manager" in names
