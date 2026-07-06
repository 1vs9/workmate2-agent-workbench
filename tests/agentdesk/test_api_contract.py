# -*- coding: utf-8 -*-
"""Contract coverage tests for endpoints called by the AgentDesk frontend."""

from fastapi import FastAPI

from qwenpaw.agentdesk.chat import router as chat_router
from qwenpaw.agentdesk.router import api_router, router


def _agentdesk_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.include_router(api_router)
    app.include_router(chat_router)
    return app


def _registered_routes(app: FastAPI) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        for method in methods:
            if method not in {"HEAD", "OPTIONS"}:
                routes.add((method, path))
    return routes


def test_agentdesk_frontend_api_contract_routes_are_registered():
    app = _agentdesk_app()
    registered = _registered_routes(app)

    expected = {
        ("GET", "/health"),
        ("GET", "/api/config"),
        ("PUT", "/api/config/providers/{provider_id}"),
        ("PUT", "/api/config/active-model"),
        ("GET", "/api/employees"),
        ("POST", "/api/employees"),
        ("PUT", "/api/employees/{name}"),
        ("DELETE", "/api/employees/{name}"),
        ("GET", "/api/plaza"),
        ("POST", "/api/plaza"),
        ("POST", "/api/plaza/{name}/join"),
        ("PUT", "/api/plaza/{name}"),
        ("GET", "/api/teams"),
        ("POST", "/api/teams"),
        ("PUT", "/api/teams/{id}"),
        ("DELETE", "/api/teams/{id}"),
        ("GET", "/api/tools"),
        ("GET", "/api/skills"),
        ("POST", "/api/skills"),
        ("POST", "/api/skills/upload"),
        ("GET", "/api/skills/{skill_name}/files"),
        ("GET", "/api/skills/{skill_name}/files/{file_path:path}"),
        ("POST", "/api/skills/{skill_name}/mount"),
        ("DELETE", "/api/skills/{skill_name}"),
        ("GET", "/api/mcp"),
        ("GET", "/api/mcp/presets"),
        ("POST", "/api/mcp/presets/{preset_id}/install"),
        ("POST", "/api/mcp"),
        ("DELETE", "/api/mcp/{name}"),
        ("GET", "/api/knowledge"),
        ("POST", "/api/knowledge"),
        ("PUT", "/api/knowledge/{id}"),
        ("DELETE", "/api/knowledge/{id}"),
        ("GET", "/api/cases"),
        ("POST", "/api/cases"),
        ("PUT", "/api/cases/{id}"),
        ("DELETE", "/api/cases/{id}"),
        ("GET", "/api/tasks"),
        ("POST", "/api/tasks"),
        ("PATCH", "/api/tasks/{id}"),
        ("GET", "/api/tasks/{id}"),
        ("DELETE", "/api/tasks/{id}"),
        ("GET", "/api/tasks/{id}/events"),
        ("GET", "/api/tasks/{id}/workspace/tree"),
        ("GET", "/api/tasks/{id}/workspace/file"),
        ("POST", "/api/tasks/{id}/workspace/reveal"),
        ("GET", "/api/tasks/{id}/stats"),
        ("POST", "/api/tasks/{task_id}/context/budget"),
        ("POST", "/api/tasks/{id}/stop"),
        ("GET", "/api/tasks/{id}/queue"),
        ("PUT", "/api/tasks/{id}/queue/{item_id}"),
        ("DELETE", "/api/tasks/{id}/queue/{item_id}"),
        ("POST", "/api/tasks/{id}/queue/reorder"),
        ("GET", "/api/tasks/{id}/plan"),
        ("POST", "/api/tasks/{id}/plan/confirm"),
        ("POST", "/api/chat/stream"),
        ("POST", "/api/chat"),
        ("POST", "/api/chat/approve"),
        ("GET", "/api/automation/jobs"),
        ("POST", "/api/automation/jobs"),
        ("PUT", "/api/automation/jobs/{id}"),
        ("POST", "/api/automation/jobs/{id}/run"),
        ("POST", "/api/automation/jobs/{id}/pause"),
        ("POST", "/api/automation/jobs/{id}/resume"),
        ("DELETE", "/api/automation/jobs/{id}"),
        ("GET", "/api/automation/history"),
    }

    assert expected <= registered
