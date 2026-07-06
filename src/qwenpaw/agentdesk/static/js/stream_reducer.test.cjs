const assert = require("node:assert/strict");
const {
  applyStreamEvent,
  applyTeamStreamEvent,
  createStreamTurnState,
  createTeamStreamState,
} = require("./stream_reducer.js");

const state = createStreamTurnState();

let result = applyStreamEvent(
  state,
  { type: "team_phase", task_id: "task-1", round_id: "round-1", seq: 0, source_member: "Leader" },
  { taskId: "task-1" },
);
assert.equal(result.applied, true);
assert.equal(result.turn.lastSeq, 0);
assert.equal(result.turn.activeSpeaker, "Leader");

result = applyStreamEvent(
  state,
  { type: "text_delta", task_id: "task-1", round_id: "round-1", seq: 0, content: "duplicate" },
  { taskId: "task-1" },
);
assert.equal(result.applied, false);
assert.equal(result.stale, true);

result = applyStreamEvent(
  state,
  {
    type: "plan_update",
    task_id: "task-1",
    round_id: "round-1",
    seq: 1,
    plan_status: "team_executing",
    plan: { tasks: [{ id: "a", state: "in_progress" }] },
  },
  { taskId: "task-1" },
);
assert.equal(result.applied, true);
assert.equal(result.turn.planSnapshot.status, "team_executing");
assert.equal(result.turn.planSnapshot.tasks.length, 1);

result = applyStreamEvent(
  state,
  { type: "done", task_id: "task-1", round_id: "round-1", seq: 2, is_terminal: true },
  { taskId: "task-1" },
);
assert.equal(result.applied, true);
assert.equal(result.turn.terminal, true);
assert.equal(result.turn.terminalType, "done");

const teamState = createTeamStreamState();
let teamResult = applyTeamStreamEvent(
  teamState,
  { type: "worker_start", worker: "成员A", actor_id: "成员A", delegation_id: "d1" },
  { taskId: "task-1" },
);
assert.equal(teamResult.activeActorId, "成员A");
assert.equal(teamState.actors.get("成员A").streaming, true);

teamResult = applyTeamStreamEvent(
  teamState,
  { type: "text_delta", actor_id: "成员A", role: "worker", content: "你好" },
  { taskId: "task-1" },
);
assert.equal(teamState.actors.get("成员A").content, "你好");

teamResult = applyTeamStreamEvent(
  teamState,
  { type: "worker_done", worker: "成员A", actor_id: "成员A", delegation_id: "d1" },
  { taskId: "task-1" },
);
assert.equal(teamResult.activeActorId, "");
assert.equal(teamState.actors.get("成员A").streaming, false);

const { sanitizeTeamTurnMessages, stripLeaderOrchestrationPrefix } = require("./stream_reducer.js");
const cleaned = stripLeaderOrchestrationPrefix(
  "好的，港股分析师已介绍完毕，接下来邀请下一位成员。好的，接下来请下一位成员。## 汇总",
);
assert.ok(cleaned.startsWith("## 汇总"));
const sanitized = sanitizeTeamTurnMessages([
  { role: "user", content: "hi", sender: "你" },
  { role: "assistant", sender: "Leader (Leader)", content: "好的，下一位。" },
  { role: "assistant", sender: "成员A", content: "我是A" },
  {
    role: "assistant",
    sender: "Leader (Leader)",
    content: "好的，全部完成。## 表格",
  },
]);
assert.equal(
  sanitized.filter((m) => m.role === "assistant" && m.sender.includes("Leader")).length,
  1,
);
assert.ok(sanitized[sanitized.length - 1].content.startsWith("## 表格"));

console.log("stream_reducer tests passed");
