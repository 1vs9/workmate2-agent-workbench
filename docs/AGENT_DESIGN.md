# Agent Design Notes

AgentDesk2 models agent work around tasks. A task is the user-facing unit of
conversation, persistence, recovery, and artifacts.

## Task To Session Mapping

| Scenario | Runtime session id |
| --- | --- |
| single chat | `{task_id}` |
| default employee chat | `{task_id}` |
| team leader | `{task_id}:team:leader-native` |
| team member | `{task_id}:team:member:{role_name}` |

The goal is isolation. Switching tasks should never mix transcript state,
runtime events, or artifacts across conversations.

## Single-Agent Flow

```text
Home input
  -> POST /api/tasks
  -> TaskChat route
  -> POST /api/chat/stream
     -> ensure task metadata
     -> sync task workspace
     -> bind AgentDesk session bridge
     -> optional skill mount
     -> attach or start runtime tracker
     -> translate runtime events to SSE
     -> persist transcript asynchronously
```

The runtime still owns the agent loop. AgentDesk translates and records the
result in product terms.

## Team Flow

Team mode is a deterministic product orchestration layer. QwenPaw provides
single-agent runs and worker streams; AgentDesk defines the leader/member
experience.

```text
POST /api/chat/stream (mode=team)
  -> sync or create leader agent
  -> start or attach leader native run
  -> leader plans and delegates via chat_with_agent
  -> member worker events enter worker_stream_bus
  -> AgentDesk bridges worker_start / worker_done / deltas
  -> UI renders leader tab and member tabs
  -> timeline summarizes phases
  -> finalization closes all open bubbles
```

## Why Not Let The Frontend Orchestrate

Team behavior includes state transitions that must survive refreshes:

- leader run status;
- member worker status;
- stale producer detection;
- final transcript persistence;
- member-specific tab content;
- replay and reconnect behavior.

Keeping this in the backend avoids splitting the source of truth between browser
state and runtime state.

## Streaming State

Streaming conversations are append-heavy and failure-prone. The frontend reducer
is designed to handle:

- incremental deltas;
- message resets;
- tool traces;
- `done.messages` reconciliation;
- duplicate event suppression;
- late events from non-current tasks.

The backend also protects ordering by serializing hot-path persistence per task.

## Skill Mounting

Skills are mounted from a shared skill pool into an agent workspace. AgentDesk
supports:

- employee-bound skills;
- task-level temporary skill binding;
- agent reload after skill changes;
- stable user-facing skill labels.

Skill mounting stays outside the chat reducer. It is a backend preparation step
before the runtime run starts or attaches.

## Artifact Semantics

Tools write files into QwenPaw workspaces. AgentDesk does not duplicate binary
artifacts into task metadata. Instead:

- task metadata stores artifact references;
- workspace APIs resolve and list files;
- preview endpoints enforce task/workspace boundaries;
- compaction keeps task store size under control.

## Reliability Rules

The system is designed around a few invariants:

- every visible running message must eventually close;
- `runStatus=running` must have a live runtime reason or a recovery path;
- reconnect should attach when possible and finalize when necessary;
- `done.messages` is authoritative for final message shape;
- late events can update cache but cannot overwrite the active view incorrectly;
- event payloads must be slim enough for `/tasks/{id}/events` to stay usable.

