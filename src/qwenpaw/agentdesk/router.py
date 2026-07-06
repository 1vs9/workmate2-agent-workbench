# -*- coding: utf-8 -*-
"""AgentDesk-compatible HTTP routes (BFF)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from qwenpaw.exceptions import SkillsError

from .http_boundary import (
    body_dict as _body_dict,
    raise_bad_gateway,
    raise_bad_request,
    raise_conflict,
    raise_not_found,
)
from .automation_routes import (
    AutomationJobNotFoundError,
    create_automation_job_payload as _create_automation_job_payload,
    delete_automation_job_payload as _delete_automation_job_payload,
    list_automation_history_payloads as _list_automation_history_payloads,
    list_automation_job_payloads as _list_automation_job_payloads,
    pause_automation_job_payload as _pause_automation_job_payload,
    resume_automation_job_payload as _resume_automation_job_payload,
    run_automation_job_payload as _run_automation_job_payload,
    update_automation_job_payload as _update_automation_job_payload,
)
from .avatar_routes import (
    avatar_file_path as _avatar_file_path,
    generate_avatar_payload as _generate_avatar_payload,
)
from .config_routes import (
    get_agentdesk_config_payload as _get_agentdesk_config_payload,
    set_agentdesk_active_model_payload as _set_agentdesk_active_model_payload,
    update_agentdesk_data_dirs_payload as _update_agentdesk_data_dirs_payload,
    update_agentdesk_provider_payload as _update_agentdesk_provider_payload,
)
from .document_routes import (
    create_document_payload as _create_document_payload,
    delete_document_payload as _delete_document_payload,
    list_document_payloads as _list_document_payloads,
    update_document_payload as _update_document_payload,
)
from .employee_routes import (
    create_employee_payload as _create_employee_payload,
    delete_employee_payload as _delete_employee_payload,
    list_employee_payloads as _list_employee_payloads,
    update_employee_payload as _update_employee_payload,
)
from .mcp_routes import (
    delete_active_mcp_client as _delete_active_mcp_client,
    install_active_mcp_preset as _install_active_mcp_preset,
    list_active_mcp_clients as _list_active_mcp_clients,
    list_active_mcp_presets as _list_active_mcp_presets,
    upsert_active_mcp_client as _upsert_active_mcp_client,
)
from .mutation_reload import schedule_mutation_reload as _schedule_mutation_reload
from .plaza_routes import (
    create_plaza_payload as _create_plaza_payload,
    delete_plaza_payload as _delete_plaza_payload,
    join_plaza_payload as _join_plaza_payload,
    list_plaza_payloads as _list_plaza_payloads,
    update_plaza_payload as _update_plaza_payload,
)
from .skill_file_routes import (
    list_skill_file_payloads as _list_skill_file_payloads,
    read_request_skill_file_payload as _read_request_skill_file_payload,
)
from .skill_management_routes import (
    create_skill_payload as _create_skill_payload,
    delete_skill_payload as _delete_skill_payload,
    import_builtin_skill_payload as _import_builtin_skill_payload,
    list_skill_payloads as _list_skill_payloads,
)
from .skill_records import (
    InvalidSkillPayloadError,
    SkillAlreadyExistsError,
)
from .skill_routes import mount_skill_for_request as _mount_skill_for_request
from .skill_upload_routes import (
    SkillUploadConflictError,
    upload_skill_payload as _upload_skill_payload,
)
from .stubs import health_payload
from .task_workspace_routes import (
    reveal_task_workspace_payload as _reveal_task_workspace_payload,
    task_workspace_file_payload as _task_workspace_file_payload,
    task_workspace_tree_payload as _task_workspace_tree_payload,
)
from .task_planning_routes import (
    confirm_task_plan_payload as _confirm_task_plan_payload,
    delete_task_queue_item_payload as _delete_task_queue_item_payload,
    get_task_plan_payload as _get_task_plan_payload,
    get_task_queue_payload as _get_task_queue_payload,
    reorder_task_queue_payload as _reorder_task_queue_payload,
    update_task_queue_item_payload as _update_task_queue_item_payload,
)
from .task_routes import (
    create_task_payload as _create_task_payload,
    delete_task_payload as _delete_task_payload,
    estimate_task_context_budget_payload as _estimate_task_context_budget_payload,
    get_task_payload as _get_task_payload,
    list_task_payloads as _list_task_payloads,
    stop_task_payload as _stop_task_payload,
    task_events_payload as _task_events_payload,
    task_stats_payload as _task_stats_payload,
    update_task_payload as _update_task_payload,
)
from .task_records import (
    ClientManagedTaskFieldError,
)
from .team_routes import (
    create_team_payload as _create_team_payload,
    delete_team_payload as _delete_team_payload,
    list_team_payloads as _list_team_payloads,
    update_team_payload as _update_team_payload,
)
from .tool_routes import list_tool_payloads as _list_tool_payloads

router = APIRouter(tags=["agentdesk"])

api_router = APIRouter(prefix="/api", tags=["agentdesk-api"])


@router.get("/health")
def agentdesk_health():
    """AgentDesk frontend probe (same path as demo-plat backend)."""
    return health_payload()


@api_router.get("/config")
async def get_agentdesk_settings():
    """AgentDesk settings snapshot: working dir, providers, active model."""
    return await _get_agentdesk_config_payload()


@api_router.put("/config/providers/{provider_id}")
async def update_agentdesk_provider_settings(
    provider_id: str,
    body: dict[str, Any],
):
    try:
        return await _update_agentdesk_provider_payload(provider_id, _body_dict(body))
    except ValueError as exc:
        raise_bad_request(exc)
    except LookupError as exc:
        raise_not_found(exc)


@api_router.put("/config/data-dirs")
async def update_agentdesk_data_directories(body: dict[str, Any]):
    try:
        return await _update_agentdesk_data_dirs_payload(_body_dict(body))
    except ValueError as exc:
        raise_bad_request(exc)


@api_router.put("/config/active-model")
async def update_agentdesk_active_model(body: dict[str, Any]):
    try:
        return await _set_agentdesk_active_model_payload(_body_dict(body))
    except ValueError as exc:
        raise_bad_request(exc)
    except Exception as exc:  # noqa: BLE001 - surface provider activation errors
        raise_bad_request(exc)


@api_router.post("/avatars/generate")
def generate_avatar(body: dict[str, Any]):
    try:
        return _generate_avatar_payload(_body_dict(body))
    except ValueError as exc:
        raise_bad_request(exc)
    except Exception as exc:  # noqa: BLE001 - surface generation errors
        raise_bad_gateway(exc)


@api_router.get("/avatars/{filename}")
def get_avatar_file(filename: str):
    try:
        path = _avatar_file_path(filename)
    except ValueError as exc:
        raise_bad_request(exc)
    except Exception as exc:  # noqa: BLE001 - upstream DiceBear failures
        raise_bad_gateway(exc)
    return FileResponse(path, media_type="image/svg+xml")


@api_router.get("/employees")
def list_employees():
    return _list_employee_payloads()


@api_router.post("/employees")
def create_employee(body: dict[str, Any]):
    try:
        return _create_employee_payload(_body_dict(body))
    except ValueError as exc:
        raise_bad_request(exc)


@api_router.put("/employees/{name}")
def update_employee(name: str, body: dict[str, Any]):
    return _update_employee_payload(name, _body_dict(body))


@api_router.delete("/employees/{name}")
def delete_employee(name: str):
    try:
        return _delete_employee_payload(name)
    except ValueError as exc:
        raise_bad_request(exc)
    except LookupError as exc:
        raise_not_found(exc)


@api_router.get("/plaza")
def list_plaza():
    return _list_plaza_payloads()


@api_router.post("/plaza")
def create_plaza_item(body: dict[str, Any]):
    try:
        return _create_plaza_payload(_body_dict(body))
    except ValueError as exc:
        raise_bad_request(exc)


@api_router.post("/plaza/{name}/join")
def join_plaza_item(name: str):
    return _join_plaza_payload(name)


@api_router.put("/plaza/{name}")
def update_plaza_item(name: str, body: dict[str, Any]):
    return _update_plaza_payload(name, _body_dict(body))


@api_router.delete("/plaza/{name}")
def delete_plaza_item(name: str):
    try:
        return _delete_plaza_payload(name)
    except ValueError as exc:
        raise_bad_request(exc)
    except LookupError as exc:
        raise_not_found(exc)


@api_router.get("/teams")
def list_teams():
    return _list_team_payloads()


@api_router.post("/teams")
def create_team(body: dict[str, Any]):
    try:
        return _create_team_payload(_body_dict(body))
    except ValueError as exc:
        raise_bad_request(exc)


@api_router.put("/teams/{id}")
def update_team(id: str, body: dict[str, Any]):
    try:
        return _update_team_payload(id, _body_dict(body))
    except ValueError as exc:
        raise_bad_request(exc)


@api_router.delete("/teams/{id}")
def delete_team(id: str):
    return _delete_team_payload(id)


@api_router.get("/skills")
def list_skills():
    return _list_skill_payloads()


@api_router.get("/skills/{skill_name}/files")
def list_skill_files(skill_name: str):
    return _list_skill_file_payloads(skill_name)


@api_router.get("/skills/{skill_name}/files/{file_path:path}")
def read_skill_file(skill_name: str, file_path: str):
    return _read_request_skill_file_payload(skill_name, file_path)


@api_router.post("/skills/pool/import-builtin")
def import_pool_builtin(body: dict[str, Any]):
    try:
        return _import_builtin_skill_payload(_body_dict(body))
    except InvalidSkillPayloadError as exc:
        raise_bad_request(exc)
    except SkillsError as exc:
        raise_bad_request(exc)


@api_router.post("/skills")
def create_skill(body: dict[str, Any]):
    try:
        return _create_skill_payload(_body_dict(body))
    except InvalidSkillPayloadError as exc:
        raise_bad_request(exc)
    except SkillsError as exc:
        raise_bad_request(exc)
    except SkillAlreadyExistsError as exc:
        raise_conflict(exc)


@api_router.post("/skills/upload")
async def upload_skill(
    request: Request,
    file: UploadFile | None = File(default=None),
    files: list[UploadFile] = File(default=[]),
    relative_paths: str = Form(default="[]"),
    auto_install_safe: bool = Form(default=True),
):
    try:
        result = await _upload_skill_payload(
            file=file,
            files=list(files),
            relative_paths=relative_paths,
            auto_install_safe=auto_install_safe,
        )
    except SkillsError as exc:
        raise_bad_request(exc)
    except SkillUploadConflictError as exc:
        raise_conflict(exc, detail=exc.detail)
    _schedule_mutation_reload(request, result)
    return result.payload


@api_router.post("/skills/{skill_name}/mount")
async def mount_skill(skill_name: str, body: dict[str, Any], request: Request):
    result = _mount_skill_for_request(skill_name, _body_dict(body))
    _schedule_mutation_reload(request, result)
    return result.payload


@api_router.delete("/skills/{skill_name}")
def delete_skill(skill_name: str):
    return _delete_skill_payload(skill_name)


@api_router.get("/tools")
def list_tools():
    return _list_tool_payloads()


@api_router.get("/mcp/presets")
def list_mcp_presets():
    return _list_active_mcp_presets()


@api_router.post("/mcp/presets/{preset_id}/install")
async def install_mcp_preset(preset_id: str, request: Request):
    result = _install_active_mcp_preset(preset_id)
    _schedule_mutation_reload(request, result)
    return result.payload


@api_router.get("/mcp")
def list_mcp():
    return _list_active_mcp_clients()


@api_router.post("/mcp")
async def upsert_mcp(body: dict[str, Any], request: Request):
    try:
        result = _upsert_active_mcp_client(_body_dict(body))
    except ValueError as exc:
        raise_bad_request(exc)
    _schedule_mutation_reload(request, result)
    return result.payload


@api_router.delete("/mcp/{name}")
async def delete_mcp(name: str, request: Request):
    result = _delete_active_mcp_client(name)
    _schedule_mutation_reload(request, result)
    return result.payload


@api_router.get("/knowledge")
def list_knowledge():
    return _list_document_payloads("knowledge")


@api_router.post("/knowledge")
def create_knowledge(body: dict[str, Any]):
    return _create_document_payload("knowledge", _body_dict(body))


@api_router.put("/knowledge/{id}")
def update_knowledge(id: str, body: dict[str, Any]):
    try:
        return _update_document_payload("knowledge", id, _body_dict(body))
    except LookupError as exc:
        raise_not_found(exc, detail="Not found")


@api_router.delete("/knowledge/{id}")
def delete_knowledge(id: str):
    return _delete_document_payload("knowledge", id)


@api_router.get("/cases")
def list_cases():
    return _list_document_payloads("cases")


@api_router.post("/cases")
def create_case(body: dict[str, Any]):
    return _create_document_payload("cases", _body_dict(body))


@api_router.put("/cases/{id}")
def update_case(id: str, body: dict[str, Any]):
    try:
        return _update_document_payload("cases", id, _body_dict(body))
    except LookupError as exc:
        raise_not_found(exc, detail="Not found")


@api_router.delete("/cases/{id}")
def delete_case(id: str):
    return _delete_document_payload("cases", id)


@api_router.get("/tasks")
def list_tasks():
    return _list_task_payloads()


@api_router.post("/tasks")
def create_task(body: dict[str, Any]):
    try:
        return _create_task_payload(_body_dict(body))
    except ClientManagedTaskFieldError as exc:
        raise_bad_request(exc)


@api_router.patch("/tasks/{id}")
def update_task(id: str, body: dict[str, Any]):
    try:
        return _update_task_payload(id, _body_dict(body))
    except LookupError as exc:
        raise_not_found(exc, detail="Task not found")


@api_router.get("/tasks/{id}")
async def get_task(id: str):
    return await _get_task_payload(id)


@api_router.delete("/tasks/{id}")
async def delete_task(id: str, request: Request):
    return await _delete_task_payload(id, request)


@api_router.get("/tasks/{id}/events")
def get_task_events(id: str):
    return _task_events_payload(id)


@api_router.get("/tasks/{id}/workspace/tree")
def get_task_workspace_tree(id: str):
    return _task_workspace_tree_payload(id)


@api_router.get("/tasks/{id}/workspace/file")
def get_task_workspace_file(id: str, path: str):
    return _task_workspace_file_payload(id, path)


@api_router.post("/tasks/{id}/workspace/reveal")
def reveal_task_workspace_path(id: str, body: dict[str, Any]):
    return _reveal_task_workspace_payload(id, _body_dict(body))


@api_router.get("/tasks/{id}/stats")
def get_task_stats(id: str):
    return _task_stats_payload(id)


@api_router.post("/tasks/{task_id}/context/budget")
def estimate_task_context_budget(task_id: str, body: dict[str, Any]):
    return _estimate_task_context_budget_payload(task_id, _body_dict(body))


@api_router.post("/tasks/{id}/stop")
async def stop_task(id: str, request: Request):
    return await _stop_task_payload(id, request)


@api_router.get("/tasks/{id}/queue")
def get_task_queue(id: str):
    return _get_task_queue_payload(id)


@api_router.put("/tasks/{id}/queue/{item_id}")
def update_task_queue_item(id: str, item_id: str, body: dict[str, Any]):
    return _update_task_queue_item_payload(id, item_id, _body_dict(body))


@api_router.delete("/tasks/{id}/queue/{item_id}")
def delete_task_queue_item(id: str, item_id: str):
    return _delete_task_queue_item_payload(id, item_id)


@api_router.post("/tasks/{id}/queue/reorder")
def reorder_task_queue(id: str, body: dict[str, Any]):
    return _reorder_task_queue_payload(id, _body_dict(body))


@api_router.get("/tasks/{id}/plan")
def get_task_plan(id: str):
    return _get_task_plan_payload(id)


@api_router.post("/tasks/{id}/plan/confirm")
def confirm_task_plan(id: str, body: dict[str, Any]):
    return _confirm_task_plan_payload(id, _body_dict(body))


@api_router.get("/automation/jobs")
def list_automation_jobs():
    return _list_automation_job_payloads()


@api_router.post("/automation/jobs")
async def create_automation_job(body: dict[str, Any], request: Request):
    return await _create_automation_job_payload(_body_dict(body), request)


@api_router.put("/automation/jobs/{id}")
async def update_automation_job(id: str, body: dict[str, Any], request: Request):
    try:
        return await _update_automation_job_payload(id, _body_dict(body), request)
    except AutomationJobNotFoundError as exc:
        raise_not_found(exc, detail="Not found")


@api_router.post("/automation/jobs/{id}/run")
async def run_automation_job(id: str, request: Request):
    try:
        return await _run_automation_job_payload(id, request)
    except AutomationJobNotFoundError as exc:
        raise_not_found(exc, detail="Not found")


@api_router.post("/automation/jobs/{id}/pause")
async def pause_automation_job(id: str, request: Request):
    try:
        return await _pause_automation_job_payload(id, request)
    except AutomationJobNotFoundError as exc:
        raise_not_found(exc, detail="Not found")


@api_router.post("/automation/jobs/{id}/resume")
async def resume_automation_job(id: str, request: Request):
    try:
        return await _resume_automation_job_payload(id, request)
    except AutomationJobNotFoundError as exc:
        raise_not_found(exc, detail="Not found")


@api_router.delete("/automation/jobs/{id}")
async def delete_automation_job(id: str, request: Request):
    try:
        return await _delete_automation_job_payload(id, request)
    except AutomationJobNotFoundError as exc:
        raise_not_found(exc, detail="Not found")


@api_router.get("/automation/history")
def list_automation_history():
    return _list_automation_history_payloads()
