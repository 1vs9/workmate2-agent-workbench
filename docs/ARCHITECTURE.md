# AgentDesk2 Architecture

AgentDesk2 is a product layer over QwenPaw. The architectural goal is to keep
runtime execution and product semantics separate:

- QwenPaw runs agents, tools, sessions, workspaces, memory, cron, and approvals.
- AgentDesk owns task UX, team orchestration, stream projection, persistence, and
  artifact indexing.

## High-Level Flow

```text
User
  |
  v
React AgentDesk UI
  - TaskChat
  - team tabs
  - execution trace panel
  - artifact preview
  |
  | REST + SSE
  v
AgentDesk BFF
  - /api/tasks
  - /api/chat/stream
  - stream translator
  - task store
  - team orchestration
  - skill mounting
  |
  | runtime adapter calls
  v
QwenPaw runtime
  - agent run
  - tool calls
  - SafeJSONSession
  - Workspace
  - worker_stream_bus
```

## Layer Responsibilities

| Layer | Owns | Avoids |
| --- | --- | --- |
| React UI | rendering, tabs, reducer state, trace panels, artifacts | direct LLM calls, direct disk writes |
| AgentDesk BFF | task metadata, SSE translation, transcript persistence, team product state | replacing QwenPaw's agent loop |
| QwenPaw runtime | model calls, tools, sessions, workspaces, approvals | AgentDesk task list and team UX semantics |

## Why A BFF Layer

Agent runtimes expose low-level concepts: sessions, tools, channels, workspace
files, and event streams. Product UIs need different concepts: tasks, employees,
 teams, trace panels, recoverable conversations, and artifacts tied to a task.

The BFF isolates those mappings:

- `task_id` maps to QwenPaw `session_id`.
- product employees map to agent profiles.
- team members map to deterministic member session ids.
- QwenPaw stream events map to a stable frontend event contract.
- workspace files become task-scoped artifacts.

This lets the frontend stay predictable without forcing product concerns into
the runtime core.

## Data Model

| Data | Location | Notes |
| --- | --- | --- |
| task metadata | `{data_dir}/agentdesk/store.json` | title, run status, agent id, lightweight transcript |
| archived transcripts | `{data_dir}/agentdesk/task_archives/{task_id}.json` | cold task hydration |
| hot transcript state | process memory in `task_store.py` | ordered streaming updates |
| AgentDesk sessions | `{data_dir}/agentdesk/sessions/` | bridge over QwenPaw sessions |
| artifacts | `{data_dir}/workspaces/{agent_id}/` | owned by QwenPaw workspace tools |

Artifacts are not embedded in `store.json`. Messages store references, and
preview APIs resolve those references through task/workspace boundaries.

## Stream Contract

The backend normalizes runtime events into frontend-facing SSE events:

- `reply_start`
- `text_delta`
- `tool_start`
- `tool_delta`
- `tool_done`
- `trace`
- `artifact`
- `reply_end`
- `done`
- `error`

The frontend consumes these events through a single reducer. This is important
because streaming UI can otherwise accumulate duplicate messages, stale deltas,
and out-of-order trace updates.

## Reconnect Strategy

Long-running agent tasks can outlive a browser tab. AgentDesk treats reconnect as
a first-class product behavior:

- if the runtime tracker is still running, reconnect attaches to the live stream;
- if the leader run is idle but workers are still draining, AgentDesk drains the
  worker bus before sending final `done`;
- if a stale producer never emits a normal finish, backend finalization closes
  open message bubbles and persists `runStatus=idle`;
- late events update cached task state but must not corrupt the currently viewed
  task.

## Runtime Boundary

Strongly coupled QwenPaw APIs:

- `get_agent_for_request`
- `workspace.task_tracker`
- `console_channel.stream_one`
- `SafeJSONSession`
- `SkillPoolService` / `SkillService`
- `cron_manager`
- tool guard approval service

AgentDesk-owned product mechanisms:

- task list and task metadata;
- team leader/member orchestration;
- unified SSE protocol;
- frontend stream reducer;
- task transcript compaction/archive;
- task-scoped artifact projection;
- local digital employee and team records.

Future migration to another runtime should start with a runtime adapter
interface around single-agent run, workspace, session, tools, skill mounting, and
cron. Team semantics should remain in AgentDesk.

