# WorkBuddy MVP Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans for subsequent tasks.

**Goal:** Stand up `workbuddy` repo with AgentDesk frontend mounted on QwenPaw AS2 backend and stub APIs.

**Architecture:** Env-gated `agentdesk` package; compat router at `/health` + `/api/*` stubs; StaticFiles mount replaces QwenPaw console SPA when enabled.

**Tech Stack:** QwenPaw (FastAPI, AS2), demo-plat frontend (vanilla JS)

---

### Task 1: AgentDesk settings + health

**Files:**
- Create: `src/qwenpaw/agentdesk/settings.py`
- Create: `src/qwenpaw/agentdesk/router.py`
- Create: `src/qwenpaw/agentdesk/__init__.py`

- [x] `is_agentdesk_enabled()`, `get_frontend_dir()`
- [x] `GET /health` returns AgentDesk-shaped JSON

### Task 2: API stubs for UI bootstrap

**Files:**
- Create: `src/qwenpaw/agentdesk/stubs.py`

- [x] Stub employees, plaza, teams, skills, tools, mcp, knowledge, tasks

### Task 3: Frontend mount + app wiring

**Files:**
- Create: `src/qwenpaw/agentdesk/frontend.py`
- Modify: `src/qwenpaw/app/_app.py`
- Create: `.env.agentdesk.example`

- [x] Mount `AGENTDESK_FRONTEND_DIR` with `html=True`
- [x] Skip QwenPaw console catch-all when AgentDesk enabled

### Task 4: Docs + README

**Files:**
- Create: `WORKBUDDY.md`

- [x] How to run, env vars, roadmap pointer
