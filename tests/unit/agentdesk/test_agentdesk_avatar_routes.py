# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pytest

from qwenpaw.agentdesk import avatar_routes


def test_generate_avatar_payload_normalizes_role_and_returns_seed(monkeypatch) -> None:
    calls: list[tuple[str, str, str]] = []

    def _generate(name: str, description: str, *, role: str) -> str:
        calls.append((name, description, role))
        return "/api/avatars/seed.svg"

    monkeypatch.setattr(avatar_routes, "generate_portrait_url", _generate)
    monkeypatch.setattr(
        avatar_routes,
        "avatar_seed",
        lambda name, description, role: f"{role}:{name}:{description}",
    )

    result = avatar_routes.generate_avatar_payload(
        {"name": " Alice ", "desc": " Analyst ", "role": "unknown"},
    )

    assert result == {
        "url": "/api/avatars/seed.svg",
        "seed": "employee:Alice:Analyst",
    }
    assert calls == [("Alice", "Analyst", "employee")]


def test_generate_avatar_payload_accepts_team_role(monkeypatch) -> None:
    monkeypatch.setattr(
        avatar_routes,
        "generate_portrait_url",
        lambda name, description, *, role: f"/api/avatars/{role}.svg",
    )
    monkeypatch.setattr(
        avatar_routes,
        "avatar_seed",
        lambda name, description, role: role,
    )

    assert avatar_routes.generate_avatar_payload(
        {"name": "Team", "description": "Group", "role": "TEAM"},
    ) == {
        "url": "/api/avatars/team.svg",
        "seed": "team",
    }


def test_generate_avatar_payload_requires_name() -> None:
    with pytest.raises(ValueError, match="name is required"):
        avatar_routes.generate_avatar_payload({"name": " "})


def test_avatar_file_path_validates_filename(monkeypatch, tmp_path) -> None:
    expected = tmp_path / "avatar.svg"
    seeds: list[str] = []

    def _ensure(seed: str) -> Path:
        seeds.append(seed)
        return expected

    monkeypatch.setattr(avatar_routes, "ensure_portrait_file", _ensure)

    assert avatar_routes.avatar_file_path("0123456789abcdef.svg") == expected
    assert seeds == ["0123456789abcdef"]


def test_avatar_file_path_rejects_invalid_filename() -> None:
    with pytest.raises(ValueError, match="Invalid avatar filename"):
        avatar_routes.avatar_file_path("../bad.svg")
