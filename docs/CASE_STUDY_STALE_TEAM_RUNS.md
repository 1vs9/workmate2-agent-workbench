# Case Study: Team Tasks Stuck In `running`

## Problem

Team tasks could stay stuck in `running` after a member turn failed to finish
normally. This was most visible when a delegated worker used long-running tools
or a browser automation path and the client refreshed or disconnected mid-run.

The frontend kept polling task and event endpoints because the task looked live,
but the backend no longer had a healthy producer that would emit the normal
finish sequence.

## Symptoms

- task card stayed in `running`;
- open assistant/member bubbles never received a closing event;
- `/tasks` and `/tasks/{id}/events` polling continued;
- event payloads could become too large when browser snapshots were included;
- reconnect could send premature `done` before member streams were drained.

## Root Cause

The original stream lifecycle assumed the active runtime stream would always
emit a normal finish path. Team mode made that assumption weaker:

- the leader run can become idle while member worker events are still draining;
- a browser refresh can detach the active SSE consumer;
- tool paths can fail or stop without producing a clean member finish event;
- finalization lived too close to live streaming code instead of being owned by
  an independent task state machine.

## Fix Direction

The reliability fix moved finalization into backend-owned lifecycle logic:

- watch leader/native tracker state after client disconnect;
- when the tracker is idle or stale, close every open assistant/member bubble;
- persist `runStatus=idle` after finalization;
- keep reconnect logic aware of the worker-drain phase;
- slim event payloads so historical event endpoints remain cheap.

## Design Lesson

Agent products need explicit lifecycle ownership. A stream is a transport, not a
state machine. If task state depends entirely on the happy path of a live SSE
connection, browser refreshes and tool failures will eventually leave the UI in
an impossible state.

The safer model is:

```text
runtime tracker state
  + worker bus state
  + persisted task status
  + open message bubbles
  -> backend finalization decision
```

Then SSE becomes only one way of observing that lifecycle.

## Regression Coverage

The focused regression suite targets:

- run-status persistence;
- stale run finalization;
- trace payload handling;
- task route event payload size;
- team chat reconnect/finalization behavior.

Useful commands:

```bash
pytest tests/unit/agentdesk/test_agentdesk_stream_side_effects.py tests/agentdesk/test_chat_run_status.py -q
pytest tests/unit/agentdesk/test_agentdesk_trace_events.py tests/unit/agentdesk/test_agentdesk_task_routes.py -q
pytest tests/agentdesk/test_team_chat.py -q
```

## What This Demonstrates

This bug is representative of the kind of engineering that makes agent software
harder than standard chat apps:

- long-running async work;
- partial failure;
- multiple producers;
- detached clients;
- event replay;
- final-state reconciliation;
- large tool payloads.

AgentDesk2 treats these as product architecture problems, not just UI edge cases.

