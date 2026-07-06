# AgentDesk QwenPaw Passthrough Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align AgentDesk single/team chat runtime with deterministic QwenPaw session passthrough semantics and remove team hot-path polling overhead.

**Architecture:** Keep native stream translation and TaskChat reducer path as the single UI stream model. Enforce deterministic member session ids at the inter-agent tool layer and simplify team completion flow to native worker stream lifecycle instead of AgentDesk polling loops.

**Tech Stack:** Python (FastAPI backend), TypeScript (React/Vite frontend), pytest, vitest.

---

## File Structure

- Modify: `src/qwenpaw/agents/tools/agent_management.py`
- Modify: `src/qwenpaw/agentdesk/team_chat.py`
- Modify: `src/qwenpaw/agentdesk/team_leader_agents.py`
- Modify: `src/qwenpaw/agentdesk/web/src/utils/partitionTeamConversation.ts`
- Modify: `src/qwenpaw/agentdesk/web/src/utils/memberConversationThread.ts`
- Modify: `tests/agentdesk/test_team_chat.py`
- Modify: `tests/agentdesk/test_task_store_persistence.py`
- Modify: `src/qwenpaw/agentdesk/web/src/utils/chatStreamReducer.test.ts` (only if needed by behavior shift)
- Modify: `src/qwenpaw/agentdesk/web/src/pages/TaskChat/index.test.tsx` (only if needed by behavior shift)

### Task 1: Deterministic team member session IDs in tool layer

**Files:**
- Modify: `src/qwenpaw/agents/tools/agent_management.py`
- Test: `tests/agentdesk/test_team_chat.py` (new/updated focused tests)

- [ ] **Step 1: Write failing tests for deterministic team-member session resolution**

```python
def test_submit_session_resolves_to_team_member_session_when_leader_root_present():
    # arrange caller as team leader + root_session_id + worker target
    # assert resolved session id == "{root}:team:member:{safeName}"
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agentdesk/test_team_chat.py -q -k "member_session_id or leader_root_session"`  
Expected: FAIL on missing deterministic resolution.

- [ ] **Step 3: Implement minimal resolver changes**

```python
def resolve_agent_session_id(...):
    if session_id:
        return session_id
    team_member = _resolve_team_member_for_leader_call(...)
    if team_member and root_session_id:
        return _team_member_session_id(root_session_id, team_member)
    return generate_unique_session_id(...)
```

- [ ] **Step 4: Run targeted tests**

Run: `python -m pytest tests/agentdesk/test_team_chat.py -q -k "member_session_id or leader_root_session"`  
Expected: PASS.

### Task 2: Remove hot-path async polling from team stream completion

**Files:**
- Modify: `src/qwenpaw/agentdesk/team_chat.py`
- Test: `tests/agentdesk/test_team_chat.py`

- [ ] **Step 1: Write failing tests for no polling in active stream completion path**

```python
@pytest.mark.asyncio
async def test_stream_agent_turn_does_not_poll_check_agent_task_on_hot_path(...):
    # assert get_agent_chat_task_status not called while worker stream completion handled
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/agentdesk/test_team_chat.py -q -k "does_not_poll_check_agent_task_on_hot_path"`  
Expected: FAIL (poll path still invoked).

- [ ] **Step 3: Implement minimal stream-side waiting using worker stream completion**

```python
while delegation_bridge.pending_async_replies() and time.monotonic() < deadline:
    for worker_line in await _drain_worker_events():
        yield worker_line
    if no_new_worker_event:
        await asyncio.sleep(0.1)
```

- [ ] **Step 4: Keep reconnect fallback behavior**

```python
# reconnect recovery may still use compatibility path for older runs
```

- [ ] **Step 5: Run targeted tests**

Run: `python -m pytest tests/agentdesk/test_team_chat.py -q -k "async_poll_noop or reconnect_poll_completes or worker_reply"`  
Expected: PASS.

### Task 3: Canonical member session suffix convergence (`member:`)

**Files:**
- Modify: `src/qwenpaw/agentdesk/team_chat.py`
- Modify: `src/qwenpaw/agentdesk/web/src/utils/partitionTeamConversation.ts`
- Modify: `src/qwenpaw/agentdesk/web/src/utils/memberConversationThread.ts`
- Test: `tests/agentdesk/test_team_chat.py`, `tests/agentdesk/test_task_store_persistence.py`

- [ ] **Step 1: Write failing tests for new canonical suffix and legacy compatibility**

```python
def test_team_member_session_id_stable():
    assert _team_member_session_id("task-1", "Alice") == "task-1:team:member:Alice"
```

```ts
expect(partitionTeamConversation(...legacyMemberDash...)).to...
expect(partitionTeamConversation(...newMemberColon...)).to...
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest tests/agentdesk/test_team_chat.py tests/agentdesk/test_task_store_persistence.py -q -k "member_session_id"`  
Expected: FAIL on suffix mismatch.

- [ ] **Step 3: Implement suffix update + dual-read compatibility**

```ts
if (suffix.startsWith("member-") || suffix.startsWith("member:")) { ... }
```

- [ ] **Step 4: Run targeted tests**

Run: `python -m pytest tests/agentdesk/test_team_chat.py tests/agentdesk/test_task_store_persistence.py -q -k "member_session_id"`  
Expected: PASS.

### Task 4: Team leader guidance consistency (tool docs/profile prompt)

**Files:**
- Modify: `src/qwenpaw/agentdesk/team_leader_agents.py`

- [ ] **Step 1: Add explicit session-id routing instruction for team submissions**

```markdown
- 提交 submit_to_agent 时会自动绑定团队成员会话；如显式填写 session_id，必须与成员会话一致。
```

- [ ] **Step 2: Validate no prompt-format regressions**

Run: `python -m pytest tests/agentdesk/test_team_chat.py -q -k "routes_team_mode"`  
Expected: PASS.

### Task 5: Full regression verification

**Files:**
- Verify only

- [ ] **Step 1: Run backend suite required by user**

Run: `python -m pytest tests/agentdesk/test_team_chat.py tests/agentdesk/test_task_store_persistence.py tests/agentdesk/test_chat_task_id_guard.py tests/agentdesk/test_team_timeline.py -q`  
Expected: PASS.

- [ ] **Step 2: Run frontend suite required by user**

Run: `cd src/qwenpaw/agentdesk/web && npm test -- --run src/pages/TaskChat/index.test.tsx src/utils/chatStreamReducer.test.ts`  
Expected: PASS.

- [ ] **Step 3: Collect diff and validation evidence**

Run: `git status --short`  
Expected: only intended files changed (no `static_next/assets/*` committed).

