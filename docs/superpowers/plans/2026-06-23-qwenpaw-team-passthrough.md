# Team Chat Pure QwenPaw Passthrough Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make team chat a pure passthrough of one native QwenPaw leader run — leader delegates synchronously, QwenPaw drives the whole round (delegation + synthesis + completion) in a single run, and AgentDesk only attaches, presents per-session events on the frontend, and persists.

**Architecture:** Pin the team leader to the **synchronous** `chat_with_agent` delegation primitive instead of fire-and-forget `submit_to_agent`. Because `chat_with_agent` blocks the leader's agent loop until each worker replies (and already publishes the worker's live SSE to `worker_stream_bus` keyed by the member session), the leader run never terminates early: QwenPaw itself produces leader text → worker calls → worker replies → leader synthesis → run end. AgentDesk's team path collapses to exactly the single-chat passthrough shape (`tracker.attach_or_start` → translate → present → persist → `done` when the run goes idle), plus a worker-bus drain that routes worker events into member tabs. All AgentDesk-side orchestration (coordinator follow-up loop, async pending bookkeeping, `check_agent_task` polling, synthesis injection, timeline projection) is deleted.

**Tech Stack:** Python (FastAPI backend, pytest), TypeScript (React/Vite frontend, vitest).

---

## Key Design Decision (read first)

The single decision that removes all the bugs: **the team leader delegates via synchronous `chat_with_agent`, not async `submit_to_agent`.**

- `chat_with_agent` (`agent_management.py:788`) calls `collect_final_agent_chat_response(..., publish_key)` which blocks until the worker finishes and returns the reply into the leader's tool result. The leader loop resumes with the worker's answer in context and synthesizes natively. Worker SSE is published live to `worker_stream_bus` under the member session key, so member tabs still stream in real time.
- `submit_to_agent` (`agent_management.py:890`) returns `[TASK_ID]` immediately; the leader run can end before the worker finishes, which is why AgentDesk previously needed coordinator rounds, `check_agent_task` polling, and a synthesis-injection turn.

**Trade-off:** workers run serially within a single leader model step (the leader blocks on each `chat_with_agent`). If the leader emits multiple tool calls in one step, QwenPaw may run them concurrently; otherwise delegation is sequential. Sequential-but-correct is the intended behavior here (correctness over parallelism). This is acceptable for the deep-research team use case.

---

## Target architecture

```
POST /api/chat/stream (team task)
  └─ _stream_team_chat
       ├─ member_watch branch  ─────────────► _stream_member_native_session
       │     (frontend member tab)             attach member session, translate, present
       │
       └─ leader branch ──► _stream_team_leader_run (ONE native run)
             tracker.attach_or_start(leader chat)         # like single chat
             translate leader SSE → leader/主笔 tab + persist
             subscribe worker_stream_bus[member sessions] # live worker fan-out
             drain worker events → tag by member → member tab + persist
             chat_with_agent blocks → worker streams live → leader resumes → synthesis
             run goes idle → finalize → reply_end → done
```

Reconnect mirrors single chat: if the leader tracker run is still RUNNING, `attach` and replay the buffer; otherwise emit the stored `done` snapshot. No async recovery, no poll.

---

## File Structure

- Modify: `src/qwenpaw/agentdesk/team_leader_agents.py` — pin leader to `chat_with_agent`; rewrite delegation prompt.
- Modify: `src/qwenpaw/agentdesk/team_chat.py` — collapse to single passthrough run; delete orchestration; thin the bridge.
- Modify: `src/qwenpaw/agents/tools/agent_management.py` — keep deterministic member-session routing for `chat_with_agent` (already present via `resolve_agent_session_id` / `worker_stream_publish_key`); ensure it triggers on the sync path.
- Modify: `tests/agentdesk/test_team_chat.py` — drop async-submit/coordinator tests; add sync-delegation passthrough + completion-on-idle tests.
- Verify: `src/qwenpaw/agentdesk/web/src/pages/TaskChat/index.tsx` — member tab parallel watchers (already implemented) still present member sessions.
- Verify: `tests/agentdesk/test_task_store_persistence.py`, frontend `TaskChat/index.test.tsx`, `chatStreamReducer.test.ts`.

---

### Task 1: Pin the team leader to synchronous delegation

**Files:**
- Modify: `src/qwenpaw/agentdesk/team_leader_agents.py:48-56` (required tools), `:320-335` (delegation prompt)
- Test: `tests/agentdesk/test_team_chat.py`

- [ ] **Step 1: Update required-tools constant**

```python
# Team leaders delegate with the SYNCHRONOUS chat_with_agent primitive so the
# QwenPaw leader run blocks on each worker reply and synthesizes natively in a
# single run (pure passthrough). Async submit_to_agent is intentionally NOT
# required, because fire-and-forget delegation ends the leader run early.
_LEADER_REQUIRED_TOOLS = ("chat_with_agent", "list_agents")
```

- [ ] **Step 2: Rewrite the delegation section of the leader profile prompt**

Replace the `submit_to_agent` / "系统后台自动轮询" / "不要使用 chat_with_agent" guidance with:

```markdown
- 派工时调用 `chat_with_agent` 同步咨询成员，`to_agent` **只能**传上方成员的 agent id（推荐）或成员名称（如「研究员」）；不得派工给团队外智能体。
- `chat_with_agent` 会**等待该成员完成并把其回复返回给你**，你据此继续推理；需要多位成员时依次调用（或在同一步发起多次调用）。
- 估算成员所需时间并通过 `timeout` 适当放大（深度任务建议 600 秒以上）。
- 收齐成员回复后，由你直接产出面向用户的最终综述，无需再调用任何工具。
- **不要**使用 `submit_to_agent` / `check_agent_task`（后台异步会让本轮提前结束）。
```

- [ ] **Step 3: Update/extend leader-profile tests**

```python
def test_team_leader_profile_uses_sync_delegation():
    profile = build_team_leader_profile(team_name="深度调研团队", members=["规划者", "研究员", "主笔"])
    assert "chat_with_agent" in profile["required_tools"]
    assert "submit_to_agent" not in profile["required_tools"]
    assert "submit_to_agent" not in profile["system_prompt"]
```

- [ ] **Step 4: Run targeted tests**

Run: `cd D:/proj/workbuddy && PYTHONPATH=src python -m pytest tests/agentdesk/test_team_chat.py -q -k "leader_profile or sync_delegation"`
Expected: PASS.

---

### Task 2: Collapse team stream to a single passthrough run

**Files:**
- Modify: `src/qwenpaw/agentdesk/team_chat.py` — `_run_coordinated_team_round`, `_stream_agent_turn`
- Test: `tests/agentdesk/test_team_chat.py`

- [ ] **Step 1: Write failing test — round ends when the leader run goes idle, no synthesis injection**

```python
@pytest.mark.asyncio
async def test_team_round_completes_on_leader_run_idle(monkeypatch):
    # leader stream yields text + one chat_with_agent worker_start/worker_done,
    # then ends; assert the round emits done WITHOUT a second leader turn.
    calls = []
    async def fake_stream_agent_turn(**kw):
        calls.append(kw.get("agent_message"))
        kw["turn_result"]["final_text"] = "最终综述"
        if False:
            yield ""  # make it an async generator
    monkeypatch.setattr(team_chat, "_stream_agent_turn", fake_stream_agent_turn)
    lines = [l async for l in team_chat._run_coordinated_team_round(...minimal args...)]
    assert len(calls) == 1  # exactly one leader run, no follow-up synthesis turn
    assert any('"type": "done"' in l for l in lines)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src python -m pytest tests/agentdesk/test_team_chat.py -q -k "completes_on_leader_run_idle"`
Expected: FAIL (currently calls `_finish_team_round_after_leader`).

- [ ] **Step 3: Simplify `_run_coordinated_team_round` to one leader turn + completion**

```python
async def _run_coordinated_team_round(*, payload, request, sequencer, team_name,
                                      leader_sender, leader_agent_id, user_text,
                                      leader_message_id, members):
    """One native leader run: delegation + synthesis happen inside QwenPaw."""
    bridge = _NativeTeamEventBridge(members=members, leader_sender=leader_sender)
    leader_turn: dict[str, Any] = {"final_text": "", "fatal": False}
    round_worker_message_ids: dict[str, str] = {}
    leader_message = f"{build_chat_response_language_hint(user_text)}{user_text}"
    async for line in _stream_agent_turn(
        payload=payload, request=request, agent_id=leader_agent_id,
        sender=leader_sender, agent_message=leader_message, sequencer=sequencer,
        session_suffix=_TEAM_LEADER_SESSION_SUFFIX, emit_stream_start=True,
        stream_message_id=leader_message_id, turn_result=leader_turn,
        event_mapper=bridge.map_event, delegation_bridge=bridge,
        worker_message_ids=round_worker_message_ids, roster_members=members,
    ):
        yield line
    async for line in _yield_team_turn_completion(
        payload=payload, sequencer=sequencer, team_name=team_name,
        leader_sender=leader_sender, leader_message_id=leader_message_id,
        leader_turn=leader_turn, bridge=bridge,
        worker_message_ids=round_worker_message_ids,
    ):
        yield line
```

- [ ] **Step 4: Remove the async-pending wait block from `_stream_agent_turn`**

Delete the `if delegation_bridge is not None and delegation_bridge.pending_async_replies(): ...` completion-wait block (the `_ASYNC_WORKER_WAIT_S` deadline loop, `_recover_finished_async_workers` calls, and `abandon_pending_async_worker` timeout emission). Synchronous delegation leaves no pending async replies, so the leader stream naturally ends when QwenPaw's run ends. Keep the `_drain_worker_events()` calls in the main `while` loop and in `finally` (worker live fan-out + tail finalize).

- [ ] **Step 5: Run targeted tests**

Run: `PYTHONPATH=src python -m pytest tests/agentdesk/test_team_chat.py -q -k "completes_on_leader_run_idle or worker_reply or worker_bubble"`
Expected: PASS.

---

### Task 3: Simplify team reconnect to single-chat semantics

**Files:**
- Modify: `src/qwenpaw/agentdesk/team_chat.py` — `_stream_team_chat` reconnect branch, `_run_coordinated_team_reconnect`
- Test: `tests/agentdesk/test_team_chat.py`

- [ ] **Step 1: Write failing test — reconnect with idle leader emits stored done; running leader replays attach**

```python
@pytest.mark.asyncio
async def test_team_reconnect_idle_emits_done(monkeypatch):
    # runStatus != running and leader tracker idle -> single done snapshot, no recovery
    ...
@pytest.mark.asyncio
async def test_team_reconnect_running_replays_attach(monkeypatch):
    # leader tracker RUNNING -> _stream_agent_turn attach replay (emit_stream_start=False)
    ...
```

- [ ] **Step 2: Run tests to verify failure**

Run: `PYTHONPATH=src python -m pytest tests/agentdesk/test_team_chat.py -q -k "team_reconnect"`
Expected: FAIL.

- [ ] **Step 3: Rewrite reconnect branch of `_stream_team_chat`**

```python
if payload.reconnect:
    leader_info = await asyncio.to_thread(sync_team_leader_agent, team)
    leader_agent_id = leader_info["agent_id"]
    leader_sender = leader_info.get("leader_name") or team_leader_display_name(team_name)
    resolved = await _resolve_team_leader_chat(payload=payload, request=request,
                                               leader_agent_id=leader_agent_id)
    if resolved is None:
        yield sse_line(sequencer.wrap(await _build_done_event(payload.task_id)))
        return
    workspace, chat_id = resolved
    if await workspace.task_tracker.get_status(chat_id) != _RUN_STATUS_RUNNING:
        yield sse_line(sequencer.wrap(await _build_done_event(payload.task_id)))
        return
    stream_message_id = await task_store.current_assistant_message_id(payload.task_id)
    bridge = _NativeTeamEventBridge(members=members, leader_sender=leader_sender)
    leader_turn = {"final_text": "", "fatal": False}
    async for line in _stream_agent_turn(
        payload=payload, request=request, agent_id=leader_agent_id,
        sender=leader_sender, agent_message="", sequencer=sequencer,
        session_suffix=_TEAM_LEADER_SESSION_SUFFIX, emit_stream_start=False,
        stream_message_id=stream_message_id, turn_result=leader_turn,
        event_mapper=bridge.map_event, delegation_bridge=bridge, roster_members=members,
    ):
        yield line
    async for line in _yield_team_turn_completion(
        payload=payload, sequencer=sequencer, team_name=team_name,
        leader_sender=leader_sender, leader_message_id=stream_message_id,
        leader_turn=leader_turn, bridge=bridge, worker_message_ids={},
    ):
        yield line
    return
```

Delete `_run_coordinated_team_reconnect`, `_yield_reconnect_worker_wait`, the `seeded_bridge` / `pending_async_replies` reconnect logic.

- [ ] **Step 4: Run targeted tests**

Run: `PYTHONPATH=src python -m pytest tests/agentdesk/test_team_chat.py -q -k "team_reconnect"`
Expected: PASS.

---

### Task 4: Delete dead orchestration code and thin the bridge

**Files:**
- Modify: `src/qwenpaw/agentdesk/team_chat.py`
- Test: `tests/agentdesk/test_team_chat.py`

- [ ] **Step 1: Delete now-unused functions**

Remove: `_finish_team_round_after_leader`, `_run_coordinated_team_reconnect`, `_yield_reconnect_worker_wait`, `_recover_one_async_worker`, `_recover_finished_async_workers`, `_worker_reply_digest_for_followup`, `_build_leader_followup_message`, `_await_member_workers_quiescent` (if unused), and the `TeamTimelineWriter`-only helpers (`_timeline_sse_from_entry`, `_timeline_sse_lines_for_event`) plus every `timeline_writer` parameter/branch (always `None` in prod).

- [ ] **Step 2: Thin `_NativeTeamEventBridge` to sync-delegation UI mapping only**

Keep: `__init__`, `_resolve_actor`, `_member_lookup`, `map_event` for `chat_with_agent` `tool_call_start` → `worker_start` and `tool_result_end` → `worker_done`, `worker_results_seen`, `timed_out_workers` (returns `[]`).
Remove: all async-submit state (`_async_delegations_by_call`, `_async_call_by_task`, `_async_completed_task_ids`, `pending_async_replies`, `complete_async_worker`, `abandon_pending_async_worker`, `seed_async_tasks_from_events`, `_register_async_delegation`, `_clear_async_worker_pending`, `_pending_state`) and the `check_agent_task` / `submit_to_agent` branches in `map_event`.

- [ ] **Step 3: Update `_NATIVE_DELEGATION_TOOLS`**

```python
_NATIVE_DELEGATION_TOOLS = frozenset({"chat_with_agent"})
```

- [ ] **Step 4: Remove orphaned imports/constants**

Drop `_ASYNC_WORKER_WAIT_S`, `_MEMBER_WATCH_TIMEOUT_S` extension if unused, timeline imports, `lookup_agent_id` if unused, and `_recover_*` references. Run a grep for each deleted symbol to confirm zero remaining references.

- [ ] **Step 5: Run the whole team-chat test file**

Run: `PYTHONPATH=src python -m pytest tests/agentdesk/test_team_chat.py -q`
Expected: PASS (after removing tests that exercised deleted async/coordinator code).

---

### Task 5: Verify member-tab passthrough end to end (frontend)

**Files:**
- Verify: `src/qwenpaw/agentdesk/web/src/pages/TaskChat/index.tsx:1010-1070` (parallel member watchers)
- Verify: `src/qwenpaw/agentdesk/web/src/pages/TaskChat/index.test.tsx`

- [ ] **Step 1: Confirm member watchers open `chatStream` with `teamMember` per roster member and feed `handleStreamEvent`.** No code change expected; if a member tab still uses bus-only watch, ensure `_stream_member_native_session` (native attach) is the primary path.

- [ ] **Step 2: Run frontend tests**

Run: `cd src/qwenpaw/agentdesk/web && npm test -- --run src/pages/TaskChat/index.test.tsx src/utils/chatStreamReducer.test.ts`
Expected: PASS.

---

### Task 6: Full backend regression

**Files:** Verify only.

- [ ] **Step 1: Run required backend suites**

Run: `cd D:/proj/workbuddy && PYTHONPATH=src python -m pytest tests/agentdesk/test_team_chat.py tests/agentdesk/test_task_store_persistence.py tests/agentdesk/test_chat_task_id_guard.py -q`
Expected: PASS.

- [ ] **Step 2: Confirm no stray references to deleted symbols**

Run: `rg -n "_finish_team_round_after_leader|_TeamRoundCoordinator|_yield_async_worker_poll|_yield_reconnect_worker_wait|pending_async_replies|check_agent_task" src/qwenpaw/agentdesk/team_chat.py`
Expected: no matches (or only an explanatory comment).

---

### Task 7: Live E2E — deep research team

**Files:** Verify only.

- [ ] **Step 1: Start server with updated code**

Run: `AGENTDESK_ENABLED=1 AGENTDESK_SKIP_FRONTEND_BUILD=1 PYTHONPATH=src python -m uvicorn qwenpaw.app._app:app --host 127.0.0.1 --port 8088`
Wait for readiness on `/health` (HTTP 200).

- [ ] **Step 2: Run the E2E harness**

Run: `PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 python scripts/e2e_team_deep_research.py`
Expected PASS criteria: task reaches `idle`; ≥2 member tabs have streamed content; leader/主笔 tab has a final synthesis (>80 chars); each member tab streamed like single chat.

- [ ] **Step 3: Record result** in this plan and report to user. Do NOT commit unless the user asks.

---

## Self-Review notes

- Spec coverage: pure passthrough (Task 2/3), member tabs as real sessions (Task 5 + existing `_stream_member_native_session`), remove hot-path polling/coordinator (Task 2/4) — all covered.
- The serial-delegation trade-off is called out in the Key Design Decision and is intentional.
- Deterministic member sessions already land via `resolve_agent_session_id` / `worker_stream_publish_key`; Task 1 keeps them effective on the sync `chat_with_agent` path (same `resolve_team_delegation_root_session` + `worker_stream_publish_key` calls already exist in `chat_with_agent`).
