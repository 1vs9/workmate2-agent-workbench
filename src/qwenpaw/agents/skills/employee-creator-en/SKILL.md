---
name: employee-creator
description: "Use when the user wants to create a new AgentDesk digital employee (role agent). Triggers include 'create an XXX expert', 'add employee', 'recruit a role agent', 'new digital employee', and the AgentDesk Add Employee composer template."
metadata:
  builtin_skill_version: "1.0"
  qwenpaw:
    icon: "idcard"
---

# Create Digital Employee (AgentDesk Role Agent)

Help the user create a new **role agent** (digital employee) in AgentDesk and add it to the employee roster.

## Onboarding scope (important)

- **This skill owns the full add-employee flow**: collect name, role description, optional skills, then call APIs after confirmation.
- **Do not** trigger generic `BOOTSTRAP.md` / first-run questionnaires on the default agent or on newly created employees; onboarding happens in this skill conversation only.
- `POST /api/plaza/<name>/join` pre-fills `PROFILE.md`, removes `BOOTSTRAP.md`, writes `EMPLOYEE.json`, and marks `.bootstrap_completed`.
- After creation, the employee accepts dispatch and normal chat (e.g. “hello”) **without** another onboarding pass.

## Execution rules

- Skip `create_plan`, multi-step questionnaires, and `BOOTSTRAP.md` guidance.
- When name and description are present with no placeholders (e.g. `XXX`, `[please add…]`), **call the APIs directly** without asking again.
- Do not probe ports, start backend services, or re-discover environment repeatedly. Use known API base; default `http://127.0.0.1:8088/api`.
- Never hit frontend HTML routes for this flow. Use AgentDesk API paths only (`/api/plaza`, `/api/plaza/<name>/join`, `/api/skills/...`).
- Avoid full skill-list dumps; call `GET /api/skills` once only when exact name matching is needed.
- Do not claim success until APIs succeed; report errors clearly.

## When to Use

- User asks to add an employee, create an expert, or recruit a role agent
- User filled the creation template (expert name, specialty, background)
- User describes a new hire's responsibilities and wants a dispatchable agent

## Do Not Use For

- Editing an existing employee → `PUT /api/plaza/{name}` or `PUT /api/employees/{name}`
- Creating a raw QwenPaw agent outside AgentDesk plaza → `POST /api/agents`
- Creating a skill → use the `make-skill` skill

## Workflow

### 1. Collect fields

| Field | Required | Notes |
|-------|----------|-------|
| **name** | yes | Display name, e.g. "Sales Assistant" |
| **desc** | yes | Role and capabilities; synced to agent description / PROFILE.md |
| **tags** | no | Default `["AgentDesk"]` |
| **avatar** | no | Portrait URL (auto-generated when omitted) |
| **skills** | no | Pool skill names to mount |

If placeholders like `XXX` or `[please add…]` remain, ask the user to fill them before creating.

### 2. Call AgentDesk APIs

**For one employee, prefer the `create_agentdesk_employee` tool** (single call for plaza + join; safe JSON and URL encoding).
**For multiple employees, prefer the `create_agentdesk_employees` tool** and pass all employees as one array; do not fire several `create_agentdesk_employee` calls in parallel because provisioning, skill mounting, config writes, and workspace writes can contend locally and time out.
**Do not** use `execute_shell_command` with curl or Invoke-WebRequest — JSON escaping on Windows PowerShell fails often.

Use shell only when the tool is unavailable. Default API base: `http://127.0.0.1:8088/api`.

**A — Create plaza card** (handled inside `create_agentdesk_employee`)

```http
POST /api/plaza
Content-Type: application/json

{
  "name": "<employee name>",
  "desc": "<role description>",
  "avatar": "🤖",
  "tags": ["AgentDesk"]
}
```

**B — Join roster and provision agent** (same tool)

```http
POST /api/plaza/<url-encoded-name>/join
```

`join` writes the roster, calls `ensure_employee_agent_profile` to provision the agent workspace, and finalizes identity (BOOTSTRAP skipped).

### 3. Deterministic skill binding

Put target skills in the `skills` field of `POST /api/plaza`, then rely on `join` to provision them.
If `join` returns `joined: true`, treat skills as attached and stop.

Only if `join` returns explicit failures (for example `failed_skills`), call:

```http
POST /api/skills/<skill_name>/mount
Content-Type: application/json

{ "employee_name": "<employee name>" }
```

For fallback mount, use the skill identifier in the path; backend resolves aliases and returns idempotent success when already mounted.

### 4. Wrap up

Run only one final confirmation (prefer join payload; otherwise one `GET /api/employees`), then tell the user where to find the employee and how to dispatch tasks. On failure, explain the error (duplicate name, invalid characters, etc.).
