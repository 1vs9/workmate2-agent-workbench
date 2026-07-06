# Plan 2 — AgentDesk React frontend: Chat page (AgentScopeRuntimeWebUI)

Status: in progress
Branch: agentdesk-react-frontend (current)
Depends on: Plan 1 (scaffold) — DONE

## Goal

Add a working Chat page to the new React app at `src/qwenpaw/agentdesk/web/`,
using the prebuilt `AgentScopeRuntimeWebUI` component from `@agentscope-ai/chat`,
talking to QwenPaw's native `POST /api/console/chat` and the `/api/chats`
session CRUD — exactly the integration QwenPaw Console uses. This realizes the
user's decisions `agentscope_strict` + `reuse_console_chat`.

## Scope decisions (lean MVP, faithful to console contract)

- Reuse `/api/console/chat` (native AgentScope SSE), NOT AgentDesk's translated
  `/api/chat/stream`. The native UI expects native envelopes; the translator
  path is for the legacy vanilla UI only.
- Port console's `sessionApi` (the AgentScope session adapter over `/api/chats`)
  largely verbatim — it is well-engineered (realId mapping, dedupe, reconnect
  patching). Keep it.
- DROP for MVP (reduce risk / deps), can add later:
  - i18n: hard-code zh strings in chat `options` instead of wiring i18next.
    The `AgentScopeRuntimeWebUI` component ships its own translations.
  - ModelSelector / provider precheck / rightHeader — backend surfaces a model
    error in-stream if unconfigured.
  - External `ChatSessionDrawer` + URL `/chat/:id` sync. Use the component's
    built-in session list (`hideBuiltInSessionList: false`), so no URL-sync
    callbacks (`onSessionCreated/Selected/Removed`) are needed — leave them null.
  - `toDisplayUrl` media rewrite = identity for MVP (files served as-is).
  - Agent-switch remount (`key={refreshKey}`) — single agent context.
- AgentDesk-specific task extras (workspace tree, stats, skill-wizard, plan/team)
  are intentionally NOT part of chat MVP; re-evaluated per feature in later plans.

## Files to add/modify (all under `src/qwenpaw/agentdesk/web/`)

1. `package.json` — add dependency `@agentscope-ai/chat` (version pinned to the
   console's: `^1.1.64-beta.1779961389231`). Install.
2. `src/api/request.ts` — generic `request<T>(path, init)` JSON helper using
   `getApiUrl` + `buildAuthHeaders`, throws on non-2xx.
3. `src/api/authHeaders.ts` — port `buildAuthHeaders()` (Authorization + optional
   X-Agent-Id from zustand storage).
4. `src/api/chat.ts` — types (`ChatSpec`, `ChatHistory`, `Message`, `ChatStatus`)
   + `listChats/getChat/createChat/updateChat/deleteChat/stopChat` + default
   export `api` aggregating them (sessionApi imports `api`).
5. `src/pages/Chat/utils.ts` — `toDisplayUrl` (identity for MVP),
   `normalizeContentUrls`, `extractUserMessageText`.
6. `src/pages/Chat/sessionApi.ts` — ported session adapter (from console
   `src/pages/Chat/sessionApi/index.ts`), imports `./utils` + `../../api/chat`.
7. `src/pages/Chat/index.tsx` — Chat page: builds `options`, `customFetch` →
   `POST /api/console/chat`, pass-through `responseParser`, `cancel`/`reconnect`,
   `session: { multiple: true, api: sessionApi }`; renders
   `<AgentScopeRuntimeWebUI options={options} ref={chatRef} />`. Reads dark mode
   from `useTheme`.
8. `src/router.tsx` — add `/chat` route under MainLayout; index redirects to
   `/chat`.
9. `src/layouts/MainLayout.tsx` — add "对话" nav item → `/chat`.
10. `src/pages/Chat/index.test.tsx` — smoke test (mock `@agentscope-ai/chat`,
    assert page renders without throwing; assert `customFetch` builds the right
    body — extract the fetch call). Add `@agentscope-ai/chat` to the vitest
    alias mock or `vi.mock` inline.

## Contract reference (verified from console + backend source)

- POST `getApiUrl("/console/chat")` body:
  `{ input:[lastMsg], session_id, user_id:"default", channel:"console", stream:true, ...biz_params }`
  headers: `Content-Type: application/json` + `buildAuthHeaders()`.
- reconnect: `{ reconnect:true, session_id, user_id, channel }`.
- stop (cancel): `POST /api/console/chat/stop?chat_id=<uuid>`.
- session CRUD: `GET/POST /api/chats`, `GET/PUT/DELETE /api/chats/{id}`.
  DELETE returns `{deleted:true}`.
- SSE envelopes are native AgentScope: `object=response|message|content`,
  `type=text|reasoning|plugin_call|plugin_call_output`, `delta` bool.
- `responseParser(chunk: string)` → `JSON.parse(chunk)` passthrough (cast options
  to `unknown as IAgentScopeRuntimeWebUIOptions`, runtime passes a string).
- `window.currentSessionId/currentUserId/currentChannel` globals are set by
  sessionApi and read by customFetch — keep that coupling.

## Verification

- `npm run build` (tsc + vite) succeeds; add chat chunks to manualChunks if a
  large new vendor appears (already covered by `@agentscope-ai/*` rule).
- `npm run test:run` green (scaffold smoke + chat smoke).
- Manual: with `AGENTDESK_FRONTEND_NEXT=1` and a running backend, `/chat` renders
  the chat UI; sending a message streams a reply via `/api/console/chat`.

## Risks

- `@agentscope-ai/chat` may need peer deps not yet installed (react-markdown,
  @ant-design/x-markdown, mermaid, etc.). Mitigation: install, build, add any
  missing module the bundler reports (iterative).
- responseParser type mismatch — handled by `unknown as` cast (same as console).
