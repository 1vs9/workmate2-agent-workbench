# WorkBuddy on QwenPaw — Design Spec

**Date:** 2026-06-12  
**Status:** Approved (user: 「我们开始干吧」)  
**Base:** QwenPaw `dev/agentscope2.0` (AgentScope 2.0.0)

## Goal

Build **WorkBuddy / AgentDesk** as a product fork of QwenPaw, reusing QwenPaw application-layer capabilities (channels, cron, tool guard, skills, multi-agent workspaces) while **keeping `demo-plat/frontend` unchanged** via a compatibility API layer.

## Repository

- **New workspace:** `D:\proj\workbuddy` (git worktree, branch `workbuddy/mvp`)
- **Upstream:** `agentscope-ai/QwenPaw` branch `dev/agentscope2.0`
- **Frontend source of truth:** `D:\proj\demo-plat\frontend` (mounted via env, not copied)

## Architecture

```
demo-plat/frontend (HTML, unchanged)
        │  /health, /api/*
        ▼
agentdesk_compat (BFF — new in workbuddy)
        │  domain mapping + SSE translation (later)
        ▼
QwenPaw core (existing)
        Workspace / Channel / Runner / Skills / Cron / ToolGuard
        ▼
AgentScope 2.0 SDK
```

## Domain mapping

| AgentDesk | QwenPaw |
|----------|---------|
| `Employee` | `agent_id` + `agent.json` |
| `Task` | `chat.session_id` + workspace path |
| `POST /api/chat/stream` | Internal `ConsoleChannel` + SSE translator |
| `Skill` list | QwenPaw skill pool API (adapted shape) |
| `Team` | Phase 2: SQLite or multi-agent orchestration |

## Phases

### Phase 0 (this sprint)

- Repo `workbuddy` on `workbuddy/mvp`
- `AGENTDESK_FRONTEND_DIR` mounts demo-plat frontend on port 8088
- `GET /health` compatible with AgentDesk probe
- Stub `/api/*` routes so UI loads without 404

### Phase 1

- `POST /api/chat/stream` → QwenPaw runner + SSE event translator
- `Employee` CRUD ↔ agent config sync

### Phase 2

- Tasks, events, plan confirm
- Cron via QwenPaw crons

### Phase 3

- Feishu/DingTalk channel
- Retire demo-plat backend

## Non-goals (Phase 0)

- Full chat streaming
- Team handoffs
- SQLite migration

## Configuration

| Env | Purpose |
|-----|---------|
| `AGENTDESK_FRONTEND_DIR` | Absolute path to demo-plat `frontend/` |
| `AGENTDESK_ENABLED` | `1` to enable compat layer + frontend mount |

## Success criteria (Phase 0)

1. `qwenpaw app` serves AgentDesk HTML at `http://127.0.0.1:8088/`
2. Frontend status bar shows「后端已连接」
3. No changes required in `demo-plat/frontend/js/api.js` except optional port note
