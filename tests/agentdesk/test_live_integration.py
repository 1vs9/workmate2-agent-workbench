# -*- coding: utf-8 -*-
"""Live integration tests against a running AgentDesk backend (127.0.0.1:8088).

Run manually:
  python tests/agentdesk/test_live_integration.py

Requires the server to be up with AgentDesk mode enabled.
"""

from __future__ import annotations

import json
import sys
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass, field

BASE = "http://127.0.0.1:8088"


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Suite:
    results: list[Result] = field(default_factory=list)

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        self.results.append(Result(name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        line = f"  [{mark}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok)


def _request(
    method: str,
    path: str,
    body: dict | None = None,
    *,
    raw_body: bytes | None = None,
    content_type: str = "application/json",
) -> tuple[int, object]:
    url = f"{BASE}{path}"
    headers = {"Accept": "application/json"}
    data = raw_body
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
            payload = json.loads(text) if text else None
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = text
        return exc.code, payload


def run_suite() -> Suite:
    suite = Suite()
    created: dict[str, str] = {}
    suffix = uuid.uuid4().hex[:8]
    skill_name = f"integration-skill-{suffix}"
    mcp_name = f"test-mcp-{suffix}"
    employee_name = f"TestEmployee-{suffix}"
    team_name = f"TestTeam-{suffix}"

    # --- Health / Config (sidebar probe, settings page) ---
    status, payload = _request("GET", "/health")
    suite.record("GET /health", status == 200, f"status={status}")

    status, payload = _request("GET", "/api/tools")
    suite.record("GET /api/tools", status == 200 and isinstance(payload, list))

    status, payload = _request("GET", "/api/config")
    suite.record(
        "GET /api/config",
        status == 200 and isinstance(payload, dict) and "providers" in payload,
    )

    # --- Tasks (home create, sidebar list/delete, task chat) ---
    status, task = _request(
        "POST",
        "/api/tasks",
        {"title": "Integration Test Task"},
    )
    task_id = task.get("id", "") if isinstance(task, dict) else ""
    suite.record("POST /api/tasks (create)", status == 200 and bool(task_id), task_id)
    created["task_id"] = task_id

    status, listed = _request("GET", "/api/tasks")
    suite.record(
        "GET /api/tasks (list)",
        status == 200 and any(t.get("id") == task_id for t in listed),
    )

    status, got = _request("GET", f"/api/tasks/{task_id}")
    suite.record("GET /api/tasks/{id}", status == 200 and got.get("id") == task_id)

    status, _ = _request("POST", f"/api/tasks/{task_id}/stop")
    suite.record("POST /api/tasks/{id}/stop", status == 200)

    status, tree = _request("GET", f"/api/tasks/{task_id}/workspace/tree")
    suite.record(
        "GET /api/tasks/{id}/workspace/tree",
        status == 200 and isinstance(tree, (dict, list)),
    )

    status, budget = _request(
        "POST",
        f"/api/tasks/{task_id}/context/budget",
        {"message": "hello", "skill_names": []},
    )
    suite.record(
        "POST /api/tasks/{id}/context/budget",
        status == 200 and isinstance(budget, dict) and budget.get("used_tokens", 0) >= 0,
    )

    status, events = _request("GET", f"/api/tasks/{task_id}/events")
    suite.record("GET /api/tasks/{id}/events", status == 200 and isinstance(events, list))

    status, queue = _request("GET", f"/api/tasks/{task_id}/queue")
    suite.record("GET /api/tasks/{id}/queue", status == 200 and isinstance(queue, list))

    status, plan = _request("GET", f"/api/tasks/{task_id}/plan")
    suite.record("GET /api/tasks/{id}/plan", status == 200)

    # --- Plaza (岗位智能体 page) ---
    status, plaza_card = _request(
        "POST",
        "/api/plaza",
        {
            "name": employee_name,
            "desc": "Integration test employee",
            "avatar": "🤖",
            "tags": ["test"],
        },
    )
    suite.record("POST /api/plaza (create)", status == 200)

    status, joined = _request("POST", f"/api/plaza/{employee_name}/join")
    suite.record("POST /api/plaza/{name}/join", status == 200)

    status, updated_plaza = _request(
        "PUT",
        f"/api/plaza/{employee_name}",
        {"desc": "Updated desc", "tags": ["test", "updated"]},
    )
    suite.record("PUT /api/plaza/{name}", status == 200)

    status, employees = _request("GET", "/api/employees")
    suite.record(
        "GET /api/employees",
        status == 200 and any(e.get("name") == employee_name for e in employees),
    )

    status, emp_updated = _request(
        "PUT",
        f"/api/employees/{employee_name}",
        {"desc": "Employee updated"},
    )
    suite.record("PUT /api/employees/{name}", status == 200)

    status, plaza_list = _request("GET", "/api/plaza")
    suite.record("GET /api/plaza", status == 200 and isinstance(plaza_list, list))

    # --- Teams (多智能体团队 page) ---
    status, team = _request(
        "POST",
        "/api/teams",
        {
            "name": team_name,
            "members": [employee_name],
            "avatar": "🧠",
            "desc": "Integration team",
        },
    )
    team_id = team.get("id", "") if isinstance(team, dict) else ""
    suite.record("POST /api/teams (create)", status == 200 and bool(team_id), team_id)
    created["team_id"] = team_id

    status, team_updated = _request(
        "PUT",
        f"/api/teams/{team_id}",
        {"desc": "Updated team"},
    )
    suite.record("PUT /api/teams/{id}", status == 200)

    status, teams = _request("GET", "/api/teams")
    suite.record(
        "GET /api/teams",
        status == 200 and any(t.get("id") == team_id for t in teams),
    )

    # --- Skills (技能 page + composer toolbar) ---
    status, skill = _request(
        "POST",
        "/api/skills",
        {
            "name": skill_name,
            "description": "Test skill",
            "body": "Use this skill for integration testing.",
        },
    )
    suite.record("POST /api/skills (create)", status == 200)

    status, skills = _request("GET", "/api/skills")
    suite.record(
        "GET /api/skills",
        status == 200 and any(s.get("name") == skill_name for s in skills),
    )

    status, mounted = _request(
        "POST",
        f"/api/skills/{skill_name}/mount",
        {"scope": "agent"},
    )
    suite.record("POST /api/skills/{name}/mount", status == 200)

    # --- MCP (MCP工具 page) ---
    status, mcp = _request(
        "POST",
        "/api/mcp",
        {"name": mcp_name, "transport": "stdio", "command": "echo", "enabled": True},
    )
    suite.record("POST /api/mcp (create)", status == 200)

    status, mcp_list = _request("GET", "/api/mcp")
    suite.record(
        "GET /api/mcp",
        status == 200 and any(m.get("name") == mcp_name for m in mcp_list),
    )

    # --- Docs: cases & knowledge (案例库 / 资料库) ---
    status, case = _request(
        "POST",
        "/api/cases",
        {"title": "Test Case", "content": "Case body", "tags": ["test"]},
    )
    case_id = case.get("id", "") if isinstance(case, dict) else ""
    suite.record("POST /api/cases", status == 200 and bool(case_id), case_id)
    created["case_id"] = case_id

    status, _ = _request(
        "PUT",
        f"/api/cases/{case_id}",
        {"content": "Updated case"},
    )
    suite.record("PUT /api/cases/{id}", status == 200)

    status, cases = _request("GET", "/api/cases")
    suite.record("GET /api/cases", status == 200 and isinstance(cases, list))

    status, knowledge = _request(
        "POST",
        "/api/knowledge",
        {"title": "Test Knowledge", "content": "Knowledge body"},
    )
    knowledge_id = knowledge.get("id", "") if isinstance(knowledge, dict) else ""
    suite.record("POST /api/knowledge", status == 200 and bool(knowledge_id), knowledge_id)
    created["knowledge_id"] = knowledge_id

    status, _ = _request(
        "PUT",
        f"/api/knowledge/{knowledge_id}",
        {"content": "Updated knowledge"},
    )
    suite.record("PUT /api/knowledge/{id}", status == 200)

    status, knowledge_list = _request("GET", "/api/knowledge")
    suite.record("GET /api/knowledge", status == 200 and isinstance(knowledge_list, list))

    # --- Automation (定时任务 page) ---
    status, job = _request(
        "POST",
        "/api/automation/jobs",
        {
            "name": "Integration Job",
            "workspace": "default",
            "prompt": "Say hello",
            "employee_name": None,
            "model_name": None,
            "skill_names": [],
            "chat_mode": "chat",
            "schedule": {"mode": "cron", "cron": "0 9 * * *", "timezone": "Asia/Shanghai"},
            "date_range": {"start": None, "end": None},
        },
    )
    job_id = job.get("id", "") if isinstance(job, dict) else ""
    suite.record("POST /api/automation/jobs", status == 200 and bool(job_id), job_id)
    created["job_id"] = job_id

    status, jobs = _request("GET", "/api/automation/jobs")
    suite.record(
        "GET /api/automation/jobs",
        status == 200 and any(j.get("id") == job_id for j in jobs),
    )

    status, paused = _request("POST", f"/api/automation/jobs/{job_id}/pause")
    suite.record("POST /api/automation/jobs/{id}/pause", status == 200)

    status, resumed = _request("POST", f"/api/automation/jobs/{job_id}/resume")
    suite.record("POST /api/automation/jobs/{id}/resume", status == 200)

    status, run_result = _request("POST", f"/api/automation/jobs/{job_id}/run")
    suite.record(
        "POST /api/automation/jobs/{id}/run",
        status == 200 and isinstance(run_result, dict),
    )

    status, history = _request("GET", "/api/automation/history")
    suite.record("GET /api/automation/history", status == 200 and isinstance(history, list))

    status, job_updated = _request(
        "PUT",
        f"/api/automation/jobs/{job_id}",
        {"name": "Integration Job Updated"},
    )
    suite.record("PUT /api/automation/jobs/{id}", status == 200)

    # --- Chat stream (send message button) ---
    status, stream_task = _request(
        "POST",
        "/api/tasks",
        {"title": "Stream Test"},
    )
    stream_task_id = stream_task.get("id", "") if isinstance(stream_task, dict) else ""
    stream_status = 0
    stream_detail = "no task"
    if stream_task_id:
        url = f"{BASE}/api/chat/stream"
        body = json.dumps(
            {
                "task_id": stream_task_id,
                "message": "ping",
                "mode": "single",
                "chat_mode": "chat",
            },
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                stream_status = resp.status
                chunk = resp.read(512).decode("utf-8", errors="replace")
                stream_detail = f"status={stream_status}, bytes={len(chunk)}"
        except urllib.error.HTTPError as exc:
            stream_status = exc.code
            stream_detail = f"HTTP {exc.code}"
        except Exception as exc:
            stream_detail = str(exc)
    suite.record(
        "POST /api/chat/stream",
        stream_status == 200,
        stream_detail,
    )
    if stream_task_id:
        _request("DELETE", f"/api/tasks/{stream_task_id}")

    # --- Chat endpoints (approve) ---
    status, chat_resp = _request(
        "POST",
        "/api/chat/approve",
        {"task_id": task_id, "approved": True},
    )
    suite.record(
        "POST /api/chat/approve",
        status in {200, 204, 400, 404},
        f"status={status}",
    )

    # --- Cleanup (delete buttons) ---
    status, _ = _request("DELETE", f"/api/automation/jobs/{job_id}")
    suite.record("DELETE /api/automation/jobs/{id}", status == 200)

    status, _ = _request("DELETE", f"/api/cases/{case_id}")
    suite.record("DELETE /api/cases/{id}", status == 200)

    status, _ = _request("DELETE", f"/api/knowledge/{knowledge_id}")
    suite.record("DELETE /api/knowledge/{id}", status == 200)

    status, _ = _request("DELETE", f"/api/mcp/{mcp_name}")
    suite.record("DELETE /api/mcp/{name}", status == 200)

    status, _ = _request("DELETE", f"/api/skills/{skill_name}")
    suite.record("DELETE /api/skills/{name}", status == 200)

    status, _ = _request("DELETE", f"/api/teams/{team_id}")
    suite.record("DELETE /api/teams/{id}", status == 200)

    status, _ = _request("DELETE", f"/api/employees/{employee_name}")
    suite.record("DELETE /api/employees/{name}", status == 200)

    status, _ = _request("DELETE", f"/api/plaza/{employee_name}")
    suite.record("DELETE /api/plaza/{name}", status == 200)

    status, _ = _request("DELETE", f"/api/tasks/{task_id}")
    suite.record("DELETE /api/tasks/{id}", status == 200)

    return suite


def main() -> int:
    print(f"AgentDesk live integration tests → {BASE}\n")
    try:
        urllib.request.urlopen(f"{BASE}/health", timeout=5)
    except Exception as exc:
        print(f"ERROR: backend not reachable at {BASE}: {exc}")
        return 1

    suite = run_suite()
    print(f"\nSummary: {suite.passed} passed, {suite.failed} failed")
    if suite.failed:
        print("\nFailed tests:")
        for r in suite.results:
            if not r.ok:
                print(f"  - {r.name}: {r.detail}")
        return 1
    print("\nAll button-connected API endpoints verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
