# AgentDesk → QwenPaw Passthrough Design

**Date:** 2026-06-22  
**Branch:** `feat/agentdesk-team-timeline`  
**Status:** Approved for immediate implementation (per user instruction: "我们做全量的系统性改造")

## Goal

Converge AgentDesk chat runtime onto native QwenPaw session semantics so single chat and team chat use one consistent streaming/persistence model:

1. QwenPaw passthrough behavior for all streams
2. Team member tabs map to real independent sessions (same observable UX surface as single chat)
3. Remove AgentDesk-only latency layers in team hot path

## Scope

### In scope

- Backend team streaming/runtime in `src/qwenpaw/agentdesk/team_chat.py`
- Inter-agent session-id semantics in `src/qwenpaw/agents/tools/agent_management.py`
- Team/session partitioning in TaskChat frontend:
  - `src/qwenpaw/agentdesk/web/src/utils/partitionTeamConversation.ts`
  - `src/qwenpaw/agentdesk/web/src/utils/memberConversationThread.ts`
- Regression coverage in:
  - `tests/agentdesk/test_team_chat.py`
  - `tests/agentdesk/test_task_store_persistence.py`
  - `src/qwenpaw/agentdesk/web/src/utils/chatStreamReducer.test.ts`
  - `src/qwenpaw/agentdesk/web/src/pages/TaskChat/index.test.tsx`

### Out of scope

- Rewriting the entire AgentDesk task API surface
- Removing every timeline helper file from the repository in one pass
- Replacing QwenPaw core runner/channel internals

## Current pain points

1. Team worker session identity can drift from tab session identity (`submit_to_agent` often auto-generates non-deterministic session id)
2. Team completion relies on AgentDesk-side async polling (`check_agent_task` path), adding latency and duplicate lifecycle handling
3. Frontend partition utilities assume only one legacy member-session suffix shape

## Target architecture

### Session model

- Leader session: `{taskId}:team:leader-native`
- Member session: `{taskId}:team:member:{roleSafe}`
- Single chat remains task-root session passthrough (`task_id` based)

### Streaming model

- Keep native QwenPaw stream translation (`translate_sse_chunk`) as the only event normalization layer
- Team leader stream remains the orchestrator stream
- Worker progress/reply surfacing remains tied to worker-native stream events; no synthetic timeline-only projection

### Completion model

- Prefer stream-native completion signals (worker stream bus done sentinels) during active team turn
- Remove hot-path server-side `check_agent_task` polling loop for normal team streaming
- Keep reconnect path backward-compatible for persisted older runs

## Design decisions

### 1) Deterministic member session routing at tool layer

`submit_to_agent`/`chat_with_agent` session resolution will auto-pin to member session ids when:

- caller is a team leader
- `root_session_id` is present
- target agent resolves to a known roster member
- explicit `session_id` is not already provided

This ensures worker runs occur in the same member session that TaskChat tabs read.

### 2) Team turn completion waits on native stream signals

During an active team turn:

- worker done sentinels emitted from native background task streaming are authoritative for completion
- remove per-worker periodic HTTP polling in the main stream path
- if workers still pending past timeout, close with explicit timeout events

### 3) Member-session suffix convergence

Adopt canonical member suffix `member:{safeName}` while retaining compatibility with historical `member-{safeName}` records in frontend partition logic.

## Data flow

### Single chat

Client `POST /api/chat/stream` -> AgentDesk chat passthrough -> native console session stream -> translated SSE -> persisted task messages/events.

### Team chat

1. Client submits user turn on team task.
2. Leader runs in leader-native session.
3. Leader delegates via `submit_to_agent`.
4. Tool layer resolves member-target session id to `{taskId}:team:member:{role}`.
5. Worker-native stream events are surfaced and persisted under that member session/bubble.
6. Team stream closes when leader + worker pending lifecycle converges or timeout.

## Error handling

- Missing/blank `task_id`: hard 400 reject (existing guard retained)
- Team not found/leader provisioning failure: fatal SSE error then done snapshot
- Worker timeout: explicit worker timeout event and final done snapshot

## Performance impact

Expected improvements:

- Remove hot-path `check_agent_task` polling fan-out
- Reduce duplicate async lifecycle reconciliation
- Keep event translation single-path (native -> reducer-friendly SSE)

## Testing strategy

1. Backend regression: team flow, deterministic session ids, async completion without poll loops
2. Persistence regression: member session id tagging and per-member routing remains stable
3. Frontend regression: member tab partitioning works for both old and new suffix formats
4. Existing single-chat guard/path tests remain green

## Remaining honest gaps (Phase 2 — 2026-06-22)

Phase 2 landed:

- Worker SSE `publish_key` routes to **member native session** (`:team:member:`), not leader root.
- Leader stream subscribes to **all roster member session bus keys** plus leader fallback (nested delegation).
- **Per-member watch stream** (`team_member` on `ChatRequest`) mirrors QwenPaw session observability; frontend opens parallel member watchers during team runs.

Still present (non-hot-path):

- `_NativeTeamEventBridge` coordinator for leader follow-up rounds and async task bookkeeping.
- `team_timeline` persistence helpers (not primary UI path).

1. **Risk:** mixed historical session suffixes split old/new data.  
   **Mitigation:** frontend accepts both `member-` and `member:`.
2. **Risk:** removal of poll path misses edge cases after reconnect.  
   **Mitigation:** keep reconnect fallback behavior and add targeted tests.
3. **Risk:** leader tool-call variability may bypass deterministic sessions.  
   **Mitigation:** enforce in tool-level resolver, not prompt-only guidance.

