# -*- coding: utf-8 -*-
"""Native AgentDesk employee/plaza tools (avoid shell HTTP on Windows)."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import quote

import httpx
from agentscope.message import TextBlock
from agentscope.tool import ToolChunk
from agentscope.message import ToolResultState

from .agent_management import create_agent_api_client


AGENTDESK_EMPLOYEE_API_TIMEOUT = 120.0


class AgentDeskApiProbeError(RuntimeError):
    """Raised when the configured endpoint is not a AgentDesk API server."""


def _tool_text_response(text: str) -> ToolChunk:
    return ToolChunk(
        is_last=True,
        state=ToolResultState.SUCCESS,
        content=[TextBlock(type="text", text=text)],
    )


def _json_text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _plaza_payload(
    name: str,
    desc: str,
    skills: list[str] | None = None,
    tags: list[str] | None = None,
    avatar: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "desc": desc,
        "tags": list(tags or ["AgentDesk"]),
    }
    if skills:
        payload["skills"] = list(skills)
    if avatar:
        payload["avatar"] = avatar
    return payload


def _response_looks_like_html(response: httpx.Response) -> bool:
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" in content_type:
        return True
    text = (response.text or "").lstrip().lower()
    return text.startswith("<!doctype html") or text.startswith("<html")


def _probe_agentdesk_api(client: httpx.Client) -> None:
    """Fail fast when the tool is pointed at the frontend or wrong port."""
    try:
        response = client.get("/employees")
    except httpx.TimeoutException as exc:
        raise AgentDeskApiProbeError(
            "AgentDesk API probe timed out. The configured API endpoint may be "
            "wrong, blocked, or the backend is not running. Verify "
            "`/health` and `/api/employees` on the actual backend port.",
        ) from exc
    except httpx.RequestError as exc:
        raise AgentDeskApiProbeError(
            "AgentDesk API probe failed before creating the employee. Verify "
            "the backend is running and that the API base URL points to the "
            "AgentDesk backend, not the frontend dev server.",
        ) from exc

    if _response_looks_like_html(response):
        raise AgentDeskApiProbeError(
            "AgentDesk API probe returned HTML instead of JSON. This usually "
            "means the tool is pointed at the frontend/static server or the "
            "wrong port. Check that `/api/employees` returns JSON.",
        )
    if response.status_code == 405:
        raise AgentDeskApiProbeError(
            "AgentDesk API probe returned 405 Method Not Allowed. The endpoint "
            "is reachable, but it does not look like the AgentDesk API route. "
            "Check the backend port and API prefix.",
        )
    if response.status_code >= 400:
        detail = response.text.strip() or response.reason_phrase
        raise AgentDeskApiProbeError(
            f"AgentDesk API probe failed ({response.status_code}): {detail}. "
            "Verify AGENTDESK_ENABLED=1 and that `/api/employees` is available.",
        )
    try:
        response.json()
    except ValueError as exc:
        raise AgentDeskApiProbeError(
            "AgentDesk API probe did not return JSON. Check that the configured "
            "base URL points to the AgentDesk backend API.",
        ) from exc


def create_agentdesk_employee_data(
    name: str,
    desc: str,
    skills: list[str] | None = None,
    tags: list[str] | None = None,
    avatar: str | None = None,
    base_url: str | None = None,
    mount_failed_skills: bool = True,
) -> dict[str, Any]:
    """Create a AgentDesk employee via plaza + join API calls."""
    result = create_agentdesk_employees_data(
        [
            {
                "name": name,
                "desc": desc,
                "skills": skills,
                "tags": tags,
                "avatar": avatar,
                "mount_failed_skills": mount_failed_skills,
            },
        ],
        base_url=base_url,
    )
    if result["failed"]:
        raise RuntimeError(result["failed"][0]["error"])
    if not result["results"]:
        raise RuntimeError("employee creation returned no result")
    return result["results"][0]


def _create_one_agentdesk_employee(
    client: httpx.Client,
    *,
    name: str,
    desc: str,
    skills: list[str] | None = None,
    tags: list[str] | None = None,
    avatar: str | None = None,
    mount_failed_skills: bool = True,
) -> dict[str, Any]:
    trimmed_name = (name or "").strip()
    trimmed_desc = (desc or "").strip()
    if not trimmed_name:
        raise ValueError("name is required")
    if not trimmed_desc:
        raise ValueError("desc is required")

    payload = _plaza_payload(
        trimmed_name,
        trimmed_desc,
        skills=skills,
        tags=tags,
        avatar=avatar,
    )
    encoded_name = quote(trimmed_name, safe="")

    plaza_response = client.post("/plaza", json=payload)
    plaza_response.raise_for_status()
    plaza_item = plaza_response.json()

    join_response = client.post(f"/plaza/{encoded_name}/join")
    join_response.raise_for_status()
    join_result = join_response.json()

    mounted: list[str] = list(join_result.get("mounted_skills") or [])
    failed: list[str] = list(join_result.get("failed_skills") or [])
    mount_results: list[dict[str, Any]] = []

    if mount_failed_skills and failed:
        for skill_name in failed:
            skill = str(skill_name).strip()
            if not skill:
                continue
            mount_response = client.post(
                f"/skills/{quote(skill, safe='')}/mount",
                json={"employee_name": trimmed_name},
            )
            mount_body: Any
            try:
                mount_body = mount_response.json()
            except ValueError:
                mount_body = mount_response.text
            mount_results.append(
                {
                    "skill": skill,
                    "status_code": mount_response.status_code,
                    "response": mount_body,
                },
            )
            if mount_response.is_success:
                mounted.append(skill)
                failed = [item for item in failed if item != skill]

    return {
        "name": trimmed_name,
        "plaza": plaza_item,
        "join": join_result,
        "mounted_skills": mounted,
        "failed_skills": failed,
        "mount_attempts": mount_results,
        "joined": bool(join_result.get("joined")),
        "agent_id": join_result.get("agent_id"),
    }


def create_agentdesk_employees_data(
    employees: list[dict[str, Any]],
    base_url: str | None = None,
    mount_failed_skills: bool = True,
) -> dict[str, Any]:
    """Create multiple AgentDesk employees serially using one API client."""
    if not isinstance(employees, list) or not employees:
        raise ValueError("employees must be a non-empty list")

    results: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []

    with create_agent_api_client(
        base_url,
        default_timeout=AGENTDESK_EMPLOYEE_API_TIMEOUT,
    ) as client:
        _probe_agentdesk_api(client)
        for item in employees:
            name = str(item.get("name") or "").strip()
            try:
                result = _create_one_agentdesk_employee(
                    client,
                    name=name,
                    desc=str(item.get("desc") or ""),
                    skills=item.get("skills") if isinstance(item.get("skills"), list) else None,
                    tags=item.get("tags") if isinstance(item.get("tags"), list) else None,
                    avatar=item.get("avatar"),
                    mount_failed_skills=bool(
                        item.get("mount_failed_skills", mount_failed_skills),
                    ),
                )
            except Exception as exc:  # noqa: BLE001 - collect per employee
                failed.append({"name": name or "(missing name)", "error": str(exc)})
                continue
            results.append(result)

    return {
        "total": len(employees),
        "results": results,
        "created": [str(item.get("name") or "") for item in results],
        "failed": failed,
    }


async def create_agentdesk_employee(
    name: str,
    desc: str,
    skills: list[str] | None = None,
    tags: list[str] | None = None,
    avatar: str | None = None,
    base_url: str | None = None,
    mount_failed_skills: bool = True,
) -> ToolChunk:
    """Create a AgentDesk digital employee (plaza card + join roster).

    Prefer this tool over ``execute_shell_command`` with curl or
    Invoke-WebRequest when creating AgentDesk employees. It calls the local
    AgentDesk API directly and handles JSON encoding and URL paths safely.

    Args:
        name: Employee display name (e.g. ``舆情分析专家``).
        desc: Role and capability description; synced to PROFILE.md.
        skills: Optional pool skill names to bind (recommend 2–4).
        tags: Optional tags; defaults to ``["AgentDesk"]``.
        avatar: Optional avatar URL or emoji.
        base_url: Optional API base (default ``http://127.0.0.1:8088``).
        mount_failed_skills: When join reports ``failed_skills``, retry mount.

    Returns:
        JSON summary with plaza, join, mounted/failed skills, and agent_id.
    """
    try:
        result = await asyncio.to_thread(
            create_agentdesk_employee_data,
            name,
            desc,
            skills,
            tags,
            avatar,
            base_url,
            mount_failed_skills,
        )
        return _tool_text_response(_json_text(result))
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip() or str(exc)
        return _tool_text_response(
            f"ERROR: AgentDesk API request failed ({exc.response.status_code}): "
            f"{detail}",
        )
    except ValueError as exc:
        return _tool_text_response(f"ERROR: {exc}")


async def create_agentdesk_employees(
    employees: list[dict[str, Any]],
    base_url: str | None = None,
    mount_failed_skills: bool = True,
) -> ToolChunk:
    """Create multiple AgentDesk digital employees serially.

    Use this tool when the user asks to create a team or several employees at
    once. It avoids parallel ``create_agentdesk_employee`` calls competing for
    AgentDesk config, store, workspace and skill files.
    """
    try:
        result = await asyncio.to_thread(
            create_agentdesk_employees_data,
            employees,
            base_url,
            mount_failed_skills,
        )
        return _tool_text_response(_json_text(result))
    except ValueError as exc:
        return _tool_text_response(f"ERROR: {exc}")
    except Exception as exc:  # noqa: BLE001 - surface to agent for recovery
        return _tool_text_response(f"ERROR: {exc}")
    except Exception as exc:  # noqa: BLE001 - surface to agent for recovery
        return _tool_text_response(f"ERROR: {exc}")
