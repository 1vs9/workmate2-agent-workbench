# AgentDesk Frontend → React + Vite Migration — Design Spec

**Date:** 2026-06-12
**Status:** Approved (user: 「直接开干吧」)
**Branch:** `workbuddy/mvp` (big-bang rewrite, single cutover)
**Base stack reference:** QwenPaw Console (`console/`) — React 18 + Vite + Ant Design 5 + `@agentscope-ai/*`

## 1. Problem

The current AgentDesk frontend (`src/qwenpaw/agentdesk/static/index.html`) is a single ~12k-line HTML file with inline vanilla JS. It is noticeably laggy. Root causes identified during systematic debugging:

- **`innerHTML` full-subtree rewrites** on every stream tick (`refreshChatMessagesInPlace`, `refreshTurnRuntimePanelInPlace`, streaming bubble repaint).
- **Markdown re-render per delta** (`marked` + `DOMPurify`) over the entire message on each chunk.
- **Heavy `localStorage` persistence** of the full `tasksData` tree, re-triggered every ~3s during streaming (`PERSIST_DURING_STREAM_MS`).
- **Tailwind CSS compiled at runtime from CDN** (`https://cdn.tailwindcss.com`) — no build step, recompiles on the client.
- No virtualization, no component diffing, no code-splitting.

QwenPaw Console does not have these problems because it is a compiled React + Vite SPA using `AgentScopeRuntimeWebUI` (which diffs the DOM and renders streams incrementally).

## 2. Goal

Rewrite the **entire** AgentDesk frontend as a React + Vite SPA that mirrors the QwenPaw Console stack, while **preserving every existing AgentDesk feature/page**. Chat uses the `AgentScopeRuntimeWebUI` component wired to QwenPaw's native `/api/console/chat`. All other pages are rewritten in React and reuse the existing AgentDesk REST APIs.

### Decisions (locked)

| Topic | Decision |
|---|---|
| Refactor scope | Full rewrite of all pages (`full_react`) |
| Chat component | `AgentScopeRuntimeWebUI`, strict AgentScope protocol (`agentscope_strict`) |
| Codebase location | New independent React+Vite app under `src/qwenpaw/agentdesk/`, reusing console patterns (`new_app_reuse`) |
| Chat backend | Reuse QwenPaw `/api/console/chat` + console `sessionApi` (`reuse_console_chat`) |
| Feature scope | Keep all AgentDesk pages, reuse existing AgentDesk backend APIs (`keep_all`) |
| Migration strategy | Big-bang rewrite on branch, single cutover (Approach B) |
| Task-vs-session model | **Re-evaluate AgentDesk task extras per feature** during implementation (see §5) |

## 3. Architecture

```
src/qwenpaw/agentdesk/web/            ← NEW React + Vite source
        │  npm run build
        ▼
src/qwenpaw/agentdesk/static_next/    ← build output (served)
        │  FastAPI StaticFiles + SPA history fallback
        ▼
frontend.py / settings.py            ← serve static_next at "/"
        ▼
Backend APIs
  ├─ Chat:   /api/console/chat  (QwenPaw native, AgentScope SSE)  ← via AgentScopeRuntimeWebUI
  └─ Pages:  /api/* (AgentDesk REST: employees, plaza, teams, skills, cases, knowledge, automation, ...)
```

The legacy `static/index.html` stays in place until cutover, then is removed/retired.

## 4. Project layout (new app)

```
src/qwenpaw/agentdesk/web/
  package.json
  vite.config.ts            ← adapted from console/vite.config.ts (manualChunks, less, aliases)
  tsconfig.json
  index.html
  src/
    main.tsx
    App.tsx                 ← ThemeProvider + ConfigProvider + AuthGuard + Router (mirror console/src/App.tsx)
    router.tsx              ← react-router-dom routes for all AgentDesk pages
    api/
      config.ts             ← reuse console getApiUrl/token pattern
      agentdesk.ts           ← typed port of static/js/api.js
      session.ts            ← console sessionApi (for chat)
    pages/
      Chat/                 ← AgentScopeRuntimeWebUI wired to /api/console/chat
      Plaza/                ← Digital Employee Plaza
      Team/                 ← My Team
      Skills/
      Cases/
      Knowledge/
      CloudLinks/
      Automation/           ← scheduled tasks
      Config/               ← settings + model config
    components/
    stores/                 ← zustand
    i18n/
    theme/
```

Shared reuse from console (copy + adapt, do not import cross-app): `vite.config.ts` build/chunk config, `api/config.ts` auth/url helpers, `App.tsx` provider shell, theme tokens (`bailianTheme`/`bailianDarkTheme`), Chat `customFetch`/`responseParser`/`customToolRenderConfig` patterns.

## 5. Pages & data flow

### Chat (`task-conversation` / `new-task`)
- Rendered by `AgentScopeRuntimeWebUI` (`@agentscope-ai/chat`).
- `options.fetch = customFetch` → posts to `/api/console/chat`; `responseParser` consumes native AgentScope SSE (`object`/`content`/`plugin_call`/`reasoning`). Inline thinking + tool/trace steps rendered by the component (replaces AgentDesk's hand-rolled trace panel).
- Sessions via console `sessionApi` (list/create/switch). Maps to AgentDesk's "task" concept.
- **Per-feature re-evaluation:** AgentDesk task extras (workspace file tree, stats, queue, run-status, plan-confirm, skill-wizard) are NOT assumed to drop. Each is assessed when its page is built:
  - Skill-wizard is the biggest unknown → first spike in the Chat phase.
  - Workspace tree / stats / queue → likely a side panel around the chat component, fed by AgentDesk REST.

### Other pages (Plaza, Team, Skills, Cases, Knowledge, CloudLinks, Automation, Config)
- Plain React pages using Ant Design components.
- Data via typed `api/agentdesk.ts` (port of `static/js/api.js`) against existing AgentDesk REST endpoints in `router.py` (`/api/employees`, `/api/plaza`, `/api/teams`, `/api/skills`, `/api/tools`, `/api/mcp`, `/api/knowledge`, `/api/cases`, `/api/tasks`, `/api/automation/jobs`, `/api/config`).
- No backend API changes expected for these pages (verify endpoint-by-endpoint during build).

## 6. Build, serve & cutover

- **Build:** `npm run build` in `web/` → outputs to `../static_next/`.
- **Serve:** update `frontend.py` to mount `static_next/` at `/` with SPA history fallback (any non-`/api` route returns `index.html`); update `settings.py` frontend-dir resolution.
- **Dev:** Vite dev server with proxy to backend for `/api/*` and `/api/console/chat`.
- **Cutover (Approach B):** build the full app on `workbuddy/mvp`, validate all pages, then switch `frontend.py` to serve `static_next` and retire `static/index.html` in one commit.

## 7. Internal development phasing

1. **Scaffold** — Vite app, App shell (theme/auth/router), api/config, CI build wiring.
2. **Chat** — `AgentScopeRuntimeWebUI` + `/api/console/chat` + sessions; **skill-wizard spike**; decide task side-panel.
3. **Team / Plaza**.
4. **Skills** (incl. tools/mcp).
5. **Cases / Knowledge / CloudLinks**.
6. **Automation** (scheduled tasks).
7. **Config / Models**.
8. **Cutover** — serve `static_next`, retire legacy HTML.

## 8. Error handling & testing

- Errors: reuse console patterns (Ant Design `message`/`notification`, error boundaries, auth redirect via `AuthGuard`).
- Tests: Vitest + React Testing Library (mirror console setup). API modules unit-tested with mocked fetch; stream parsing tested against captured AgentScope SSE fixtures.

## 9. Top risks

1. **Skill-wizard / AgentDesk task semantics vs console chat model** — biggest unknown. Mitigate with an early spike in the Chat phase; keep AgentDesk REST-backed side panels rather than forcing into session model.
2. **`/api/console/chat` availability in AgentDesk mode** — confirm the endpoint and auth are reachable when running in AgentDesk mode (not only console mode).
3. **`@agentscope-ai/*` bundle size** — mitigate via `manualChunks` code-splitting (copied from console).
4. **Feature parity gaps** — each page verified against the legacy view before cutover.

## 10. Out of scope

- Backend domain refactors (task→session unification) — only adapters as needed.
- New product features beyond current AgentDesk parity.
