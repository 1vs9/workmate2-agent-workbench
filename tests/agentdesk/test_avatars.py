# -*- coding: utf-8 -*-
"""Avatar generation helpers and API tests."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import qwenpaw.constant as qwenpaw_constant
from qwenpaw.agentdesk import avatars
from qwenpaw.agentdesk.router import api_router, router
from qwenpaw.agentdesk.store import AgentDeskStore


def _fake_config(tmp_path):
    default_workspace = tmp_path / "workspaces" / "default"
    default_workspace.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        agents=SimpleNamespace(
            active_agent="default",
            profiles={
                "default": SimpleNamespace(
                    workspace_dir=str(default_workspace),
                    enabled=True,
                ),
            },
        ),
        tools=SimpleNamespace(builtin_tools={}),
        mcp=SimpleNamespace(clients={}),
    )


def _client(tmp_path, monkeypatch) -> TestClient:
    import qwenpaw.agentdesk.employee_agents as employee_agents
    import qwenpaw.agentdesk.plaza_routes as plaza_routes

    config = _fake_config(tmp_path)
    agentdesk_store = AgentDeskStore(tmp_path / "store.json")
    monkeypatch.setattr(plaza_routes, "store", agentdesk_store)
    monkeypatch.setattr(employee_agents, "store", agentdesk_store)
    monkeypatch.setattr(qwenpaw_constant, "WORKING_DIR", tmp_path)
    monkeypatch.setattr(avatars, "AVATARS_DIR", tmp_path / "avatars")
    monkeypatch.setattr(plaza_routes, "load_config", lambda: config)
    monkeypatch.setattr(employee_agents, "load_config", lambda: config)
    monkeypatch.setattr(
        employee_agents,
        "load_agent_config",
        lambda agent_id: SimpleNamespace(description=f"{agent_id} agent", skill_names=[]),
    )
    monkeypatch.setattr(
        "qwenpaw.agentdesk.mutation_reload.schedule_agent_reload",
        lambda *args, **kwargs: None,
    )
    plaza_routes.invalidate_plaza_orphan_sync()
    app = FastAPI()
    app.include_router(router)
    app.include_router(api_router)
    client = TestClient(app)
    client.agentdesk_store = agentdesk_store  # type: ignore[attr-defined]
    return client


def test_avatar_seed_is_stable_and_role_aware():
    first = avatars.avatar_seed("销售助理", "客户跟进", "employee")
    second = avatars.avatar_seed("销售助理", "客户跟进", "employee")
    team = avatars.avatar_seed("销售助理", "客户跟进", "team")
    assert first == second
    assert first != team
    assert len(first) == 16


def test_is_legacy_emoji_avatar():
    assert avatars.is_legacy_emoji_avatar("🤖") is True
    assert avatars.is_legacy_emoji_avatar("") is True
    assert avatars.is_legacy_emoji_avatar("/api/avatars/abc.svg") is False


def test_generate_portrait_url_caches_svg(tmp_path, monkeypatch):
    monkeypatch.setattr(qwenpaw_constant, "WORKING_DIR", tmp_path)
    monkeypatch.setattr(avatars, "AVATARS_DIR", tmp_path / "avatars")
    fake_svg = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"

    with patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value.read.return_value = fake_svg
        url = avatars.generate_portrait_url("销售助理", "客户跟进", role="employee")

    assert url.startswith("/api/avatars/")
    assert url.endswith(".svg")
    seed = url.removeprefix("/api/avatars/").removesuffix(".svg")
    cached = tmp_path / "avatars" / f"{seed}.svg"
    assert cached.is_file()
    assert cached.read_bytes() == fake_svg


def test_generate_avatar_api(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    fake_svg = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"

    with patch("urllib.request.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value.read.return_value = fake_svg
        response = client.post(
            "/api/avatars/generate",
            json={"name": "销售助理", "description": "客户跟进", "role": "employee"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["url"].startswith("/api/avatars/")
    assert len(payload["seed"]) == 16


def test_list_plaza_migrates_emoji_avatar(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    client.agentdesk_store.upsert_by_key(  # type: ignore[attr-defined]
        "plaza",
        "name",
        "销售助理",
        {"name": "销售助理", "desc": "客户跟进", "avatar": "🤖", "tags": ["AgentDesk"]},
    )

    with patch("urllib.request.urlopen") as urlopen:
        response = client.get("/api/plaza")

    assert response.status_code == 200
    card = response.json()[0]
    assert card["avatar"].startswith("/api/avatars/")
    urlopen.assert_not_called()
    stored = client.agentdesk_store.get_by_key(  # type: ignore[attr-defined]
        "plaza",
        "name",
        "销售助理",
    )
    assert stored["avatar"] == "🤖"
