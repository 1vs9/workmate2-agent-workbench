import { describe, expect, it } from "vitest";
import type { TaskMessage } from "../api/tasks";
import {
  aggregateTraceEvents,
  countTraceSteps,
} from "./aggregateTraceEvents";
import {
  createChatStreamState,
  hydrateChatStreamState,
  normalizeStreamEvent,
  reduceChatStreamEvent,
  type ChatStreamEvent,
} from "./chatStreamReducer";

function apply(state: ReturnType<typeof createChatStreamState>, event: ChatStreamEvent) {
  return reduceChatStreamEvent(state, event);
}

function assistantTurns(state: ReturnType<typeof createChatStreamState>) {
  return state.turns.filter((turn) => turn.role === "assistant");
}

function liveTraceTotal(state: ReturnType<typeof createChatStreamState>): number {
  const assistant = state.turns.find((turn) => turn.role === "assistant");
  if (!assistant) return 0;
  const { toolCalls, processMessages } = countTraceSteps(
    aggregateTraceEvents(assistant.traceEvents),
  );
  return toolCalls + processMessages;
}

describe("chatStreamReducer", () => {
  it("streams single-agent text incrementally into one live turn", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "WorkBuddy" });
    state = apply(state, { type: "text_delta", delta: "你" });
    state = apply(state, { type: "text_delta", delta: "好" });
    expect(state.turns).toHaveLength(1);
    expect(state.turns[0]).toMatchObject({
      role: "assistant",
      name: "WorkBuddy",
      text: "你好",
      streaming: true,
    });
  });

  it("renders a non-default single-agent sender's reply (deltas appended + finalized)", () => {
    // Regression: an employee/position agent (sender != default brand) must
    // still stream its reply into one visible, non-empty assistant turn whose
    // streaming flag clears on done — exactly like the default agent.
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "Readme编写大师" });
    state = apply(state, {
      type: "text_delta",
      sender: "Readme编写大师",
      content: "你好呀！",
    });
    state = apply(state, {
      type: "text_delta",
      sender: "Readme编写大师",
      content: "我是 Readme编写大师",
    });
    state = apply(state, { type: "done" });
    expect(state.turns).toHaveLength(1);
    expect(state.turns[0]).toMatchObject({
      role: "assistant",
      name: "Readme编写大师",
      text: "你好呀！我是 Readme编写大师",
      streaming: false,
    });
  });

  it("keeps team actors in a single reducer model", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "Leader" });
    state = apply(state, { type: "text_delta", actor_id: "leader", sender: "Leader", delta: "plan" });
    state = apply(state, { type: "worker_start", actor_id: "alice", worker: "Alice" });
    state = apply(state, { type: "text_delta", actor_id: "alice", worker: "Alice", delta: "work" });
    state = apply(state, { type: "worker_done", actor_id: "alice", worker: "Alice" });
    expect(state.turns.map((turn) => turn.name)).toEqual(["Leader", "Alice"]);
    expect(state.turns[0].streaming).toBe(true);
    expect(state.turns[1]).toMatchObject({ text: "work", streaming: false });
  });

  it("surfaces team_phase as leader observability info", () => {
    let state = createChatStreamState();
    state = apply(state, {
      type: "stream_start",
      sender: "深度调研团队·leader",
      message_id: "leader-msg",
    });
    state = apply(state, {
      type: "team_phase",
      phase: "round_progress",
      label: "规划者正在拆解任务…",
      sender: "深度调研团队·leader",
    });
    const leader = state.turns.find((turn) => turn.id === "leader-msg");
    expect(leader?.traceEvents.some((evt) => evt.type === "info")).toBe(true);
  });

  it("routes leader follow-up text to the leader turn after parallel worker_start", () => {
    let state = createChatStreamState();
    state = apply(state, {
      type: "stream_start",
      sender: "深度调研团队·leader",
      message_id: "leader-msg",
    });
    state = apply(state, {
      type: "text_delta",
      sender: "深度调研团队·leader",
      delta: "开始派工",
    });
    state = apply(state, { type: "worker_start", actor_id: "主笔", worker: "主笔" });
    state = apply(state, { type: "worker_start", actor_id: "研究员", worker: "研究员" });
    state = apply(state, {
      type: "worker_start",
      actor_id: "审查官",
      worker: "审查官",
    });
    state = apply(state, {
      type: "text_delta",
      sender: "深度调研团队·leader",
      delta: "已派出任务，让我看看各位成员的回复",
    });

    const leader = state.turns.find((turn) => turn.id === "leader-msg");
    const critic = state.turns.find((turn) => turn.name === "审查官");
    expect(leader?.text).toContain("已派出任务");
    expect(critic?.text ?? "").not.toContain("已派出任务");
  });

  it("keeps parallel workers streaming when another worker_start arrives", () => {
    let state = createChatStreamState();
    state = apply(state, {
      type: "stream_start",
      sender: "深度调研团队·leader",
      message_id: "leader-msg",
    });
    state = apply(state, { type: "worker_start", actor_id: "主笔", worker: "主笔" });
    state = apply(state, {
      type: "text_delta",
      actor_id: "主笔",
      worker: "主笔",
      delta: "主笔输出",
    });
    state = apply(state, { type: "worker_start", actor_id: "研究员", worker: "研究员" });
    const writer = state.turns.find((turn) => turn.name === "主笔");
    const researcher = state.turns.find((turn) => turn.name === "研究员");
    expect(writer?.streaming).toBe(true);
    expect(writer?.text).toContain("主笔输出");
    expect(researcher?.streaming).toBe(true);
  });

  it("stores timeline_entry events in teamTimeline state", () => {
    let state = createChatStreamState();
    state = apply(state, {
      type: "timeline_entry",
      kind: "delegation",
      actor: "leader",
      seq: 1,
      ts: 1000,
      target: "主笔",
      text: "请调研",
    });
    expect(state.teamTimeline).toHaveLength(1);
    expect(state.teamTimeline?.[0]?.kind).toBe("delegation");
    expect(state.teamTimeline?.[0]?.target).toBe("主笔");
  });

  it("routes delegation tool_call_end traces to the leader turn while worker is active", () => {
    let state = createChatStreamState();
    state = apply(state, {
      type: "stream_start",
      sender: "深度调研团队·leader",
      message_id: "leader-msg",
    });
    state = apply(state, { type: "worker_start", actor_id: "主笔", worker: "主笔" });
    state = apply(state, {
      type: "tool_call_end",
      sender: "深度调研团队·leader",
      tool_name: "submit_to_agent",
      member_name: "主笔",
      tool_call_id: "call-1",
    });
    const leader = state.turns.find((turn) => turn.id === "leader-msg");
    expect(leader?.traceEvents.some((evt) => evt.tool_name === "submit_to_agent")).toBe(
      true,
    );
  });

  it("fans in worker tool traces to the leader observability panel", () => {
    let state = createChatStreamState();
    state = apply(state, {
      type: "stream_start",
      sender: "深度调研团队·leader",
      message_id: "leader-msg",
    });
    state = apply(state, { type: "worker_start", actor_id: "研究员", worker: "研究员" });
    state = apply(state, {
      type: "tool_call_start",
      actor_id: "研究员",
      sender: "研究员",
      tool_name: "web_search",
      tool_call_id: "search-1",
    });
    const leader = state.turns.find((turn) => turn.id === "leader-msg");
    expect(leader?.traceEvents.some((evt) => evt.type === "info")).toBe(true);
    expect(
      leader?.traceEvents.some(
        (evt) =>
          evt.type === "tool_call_start" &&
          String(evt.tool_call_id ?? "").includes("fanin:研究员"),
      ),
    ).toBe(true);
    const researcher = state.turns.find((turn) => turn.name === "研究员");
    expect(researcher?.traceEvents.some((evt) => evt.tool_call_id === "search-1")).toBe(
      true,
    );
  });

  it("renders a worker's final reply (delta-less message) under its own bubble", () => {
    // Regression: a worker that streams only a trailing full `message` (no
    // incremental text_delta) must still have its NORMAL reply rendered under
    // its own bubble — attributed to the worker, never leaked into the leader.
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "Leader" });
    state = apply(state, { type: "text_delta", actor_id: "leader", sender: "Leader", delta: "我来安排" });
    state = apply(state, { type: "worker_start", actor_id: "alice", worker: "Alice" });
    state = apply(state, { type: "tool_call_start", actor_id: "alice", sender: "Alice", tool_name: "read_file", tool_call_id: "c1" });
    state = apply(state, {
      type: "message",
      actor_id: "alice",
      sender: "Alice",
      source_member: "Alice",
      content: "我是 Alice，子任务已完成。",
    });
    state = apply(state, { type: "worker_done", actor_id: "alice", worker: "Alice" });

    expect(state.turns).toHaveLength(2);
    const [leader, alice] = state.turns;
    expect(leader).toMatchObject({ name: "Leader", text: "我来安排" });
    // The worker's final reply renders once, attributed to the worker bubble,
    // alongside (not replacing) its trace, and the leader text is untouched.
    expect(alice).toMatchObject({
      name: "Alice",
      avatarKind: "team",
      text: "我是 Alice，子任务已完成。",
      streaming: false,
    });
    expect(alice.traceEvents.map((evt) => evt.type)).toContain("tool_call_start");
  });

  it("records reply_start and skills_active as trace events", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start" });
    const replyStart = normalizeStreamEvent({
      type: "trace",
      step: "reply_start",
      label: "开始处理",
    });
    expect(replyStart).not.toBeNull();
    state = apply(state, replyStart!);
    state = apply(state, {
      type: "skills_active",
      label: "已加载技能: demo",
      skills: ["demo"],
    });
    expect(state.turns[0].traceEvents.map((evt) => evt.type)).toEqual([
      "reply_start",
      "skills_active",
    ]);
  });

  it("keeps streaming assistant turn before first text_delta", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "AgentDesk企伴" });
    expect(state.turns).toHaveLength(1);
    expect(state.turns[0]).toMatchObject({
      streaming: true,
      text: "",
    });
  });

  it("tracks thinking promote and retract in trace events only", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start" });
    state = apply(state, { type: "thinking_start" });
    state = apply(state, { type: "thinking_delta", detail: "draft" });
    state = apply(state, { type: "thinking_retract" });
    expect(state.turns[0].traceEvents.map((evt) => evt.type)).toEqual([
      "thinking_start",
      "thinking_delta",
      "thinking_retract",
    ]);
    expect(state.turns[0].text).toBe("");
  });

  it("surfaces error turns when content is empty", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "WorkBuddy" });
    state = apply(state, { type: "error", content: "boom", fatal: true });
    expect(state.turns).toHaveLength(1);
    expect(state.turns[0]).toMatchObject({
      error: "boom",
      text: "boom",
      streaming: false,
    });
  });

  it("marks stream as done and closes streaming flags", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start" });
    state = apply(state, { type: "text_delta", delta: "partial" });
    state = apply(state, { type: "done" });
    expect(state.streamActive).toBe(false);
    expect(state.turns[0].streaming).toBe(false);
  });

  it("clears ghost streaming flags when run is not active", () => {
    const state = hydrateChatStreamState(createChatStreamState(), {
      messages: [
        { role: "user", id: "u1", content: "hello" },
        {
          role: "assistant",
          id: "a1",
          content: "partial reply",
          sender: "新闻分析师",
          streaming: true,
        },
      ],
      events: [],
      runActive: false,
    });
    expect(state.streamActive).toBe(false);
    expect(state.turns[1]).toMatchObject({
      text: "partial reply",
      streaming: false,
    });
  });

  it("clears empty streaming shells on idle hydrate after page refresh", () => {
    const state = hydrateChatStreamState(createChatStreamState(), {
      messages: [
        { role: "user", id: "u1", content: "分析一下日本和瑞典" },
        {
          role: "assistant",
          id: "a1",
          content: "",
          sender: "AgentDesk企伴",
          streaming: true,
        },
      ],
      events: [
        {
          type: "skills_active",
          label: "已加载技能: browser_visible",
          message_id: "a1",
        },
      ],
      runActive: false,
    });
    const assistant = state.turns.find((turn) => turn.role === "assistant");
    expect(assistant?.streaming).toBe(false);
    expect(assistant?.traceEvents.length).toBeGreaterThan(0);
  });

  it("hydrates persisted messages and keeps same reference when unchanged", () => {
    const messages: TaskMessage[] = [
      { role: "user", id: "u1", content: "hello" },
      { role: "assistant", id: "a1", content: "world", sender: "WorkBuddy" },
    ];
    const state = hydrateChatStreamState(createChatStreamState(), {
      messages,
      events: [],
      runActive: false,
    });
    const next = hydrateChatStreamState(state, {
      messages: [
        { role: "user", id: "u1", content: "hello", updatedAt: 1 },
        { role: "assistant", id: "a1", content: "world", sender: "WorkBuddy", updatedAt: 2 },
      ],
      events: [],
      runActive: false,
    });
    expect(next).toBe(state);
  });

  it("preserves live turn while run is active and server is stale", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start" });
    state = apply(state, { type: "text_delta", delta: "draft" });
    const next = hydrateChatStreamState(state, {
      messages: [{ role: "user", id: "u1", content: "hello" }],
      events: [],
      runActive: true,
    });
    expect(next.turns.find((turn) => turn.role === "assistant")?.text).toBe("draft");
  });

  it("keeps longer cached assistant text when idle server snapshot is stale", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "研究员" });
    state = apply(state, {
      type: "text_delta",
      sender: "研究员",
      delta: "想要更快检索，有几个实用思路：",
    });
    state = apply(state, {
      type: "text_delta",
      sender: "研究员",
      delta: "1. 用搜索 API\n2. 减少浏览器打开次数",
    });
    state = apply(state, { type: "done" });

    const next = hydrateChatStreamState(state, {
      messages: [
        { role: "user", id: "u1", content: "如何更快检索" },
        {
          role: "assistant",
          id: "a1",
          sender: "研究员",
          content: "想要更快检索，有几个实用思路：🚀",
          streaming: false,
        },
      ],
      events: [],
      runActive: false,
    });

    expect(next.turns.find((turn) => turn.role === "assistant")?.text).toContain(
      "1. 用搜索 API",
    );
  });

  it("normalizes legacy trace envelopes into closed reducer events", () => {
    const event = normalizeStreamEvent({
      type: "trace",
      step: "tool_result_end",
      tool_name: "search",
      tool_call_id: "c1",
      detail: "ok",
      state: "success",
    });
    expect(event).toMatchObject({
      type: "tool_result_end",
      tool_name: "search",
      tool_call_id: "c1",
      detail: "ok",
    });
  });

  it("replays leader greeting stream sequence into a visible team turn", () => {
    let state = createChatStreamState();
    const sequence: ChatStreamEvent[] = [
      {
        type: "team_phase",
        phase: "planning",
        source_member: "开户协同小队·leader",
      },
      {
        type: "stream_start",
        sender: "开户协同小队·leader",
        source_member: "开户协同小队·leader",
      },
      { type: "trace", step: "reply_start" },
      {
        type: "text_delta",
        sender: "开户协同小队·leader",
        source_member: "开户协同小队·leader",
        content: "你好",
      },
      {
        type: "text_delta",
        sender: "开户协同小队·leader",
        source_member: "开户协同小队·leader",
        content: "! 我是 Leader",
      },
      { type: "done" },
    ];
    for (const evt of sequence) {
      const normalized = normalizeStreamEvent(evt);
      if (!normalized) continue;
      state = apply(state, normalized);
    }
    expect(state.turns).toHaveLength(1);
    expect(state.turns[0]).toMatchObject({
      role: "assistant",
      name: "开户协同小队·leader",
      text: "你好! 我是 Leader",
      streaming: false,
    });
  });

  it("falls back to text-like unknown events instead of dropping output", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "Leader" });
    state = apply(state, {
      type: "assistant_chunk",
      sender: "Leader",
      text: "fallback text",
    } as ChatStreamEvent);
    state = apply(state, { type: "done" });
    expect(state.turns[0]).toMatchObject({
      text: "fallback text",
      streaming: false,
    });
  });

  it("shows a visible placeholder when stream ends without assistant output", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "Leader" });
    state = apply(state, { type: "done" });
    expect(state.turns).toHaveLength(1);
    expect(state.turns[0].text).toContain("本轮未收到可渲染回复");
    expect(state.turns[0].error).toContain("本轮未收到可渲染回复");
  });

  it("resolves the default agent to one stable identity across name variants", () => {
    // The default agent must collapse to a single row even when the persisted
    // history labels it with the legacy "WorkBuddy" alias while the live stream
    // uses the canonical "AgentDesk企伴" — same agent, one turn.
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "AgentDesk企伴" });
    state = apply(state, {
      type: "text_delta",
      sender: "AgentDesk企伴",
      delta: "你好",
    });
    state = apply(state, { type: "thinking_start", sender: "AgentDesk企伴" });

    const next = hydrateChatStreamState(state, {
      messages: [
        { role: "user", id: "u1", content: "hi" },
        {
          role: "assistant",
          id: "a1",
          content: "你好",
          sender: "WorkBuddy",
          streaming: true,
        },
      ],
      events: [],
      runActive: true,
    });

    expect(assistantTurns(next)).toHaveLength(1);
    expect(assistantTurns(next)[0].name).toBe("AgentDesk企伴");
    // The live trace survives the merge (not wiped by the stale persisted row).
    expect(assistantTurns(next)[0].traceEvents.length).toBeGreaterThan(0);
  });

  it("re-attaches to the existing streaming turn on remount instead of duplicating", () => {
    // Navigate-away → return: hydration restores a still-streaming assistant
    // message, then the reconnect replays the stream. It must merge into the one
    // hydrated turn (no second "正在回复…" row), keep a single identity, and not
    // lose the already-accumulated trace.
    let state = createChatStreamState();
    state = hydrateChatStreamState(state, {
      messages: [
        { role: "user", id: "u1", content: "hi" },
        {
          role: "assistant",
          id: "a1",
          content: "你好",
          sender: "AgentDesk企伴",
          streaming: true,
          traceEvents: [{ type: "thinking_start" }],
        },
      ],
      events: [],
      runActive: true,
    });
    expect(assistantTurns(state)).toHaveLength(1);

    // Reconnect replays from the buffer start.
    state = apply(state, { type: "stream_start", sender: "AgentDesk企伴" });
    state = apply(state, {
      type: "text_delta",
      sender: "AgentDesk企伴",
      delta: "，我在",
    });
    state = apply(state, { type: "thinking_start" });

    const assistants = assistantTurns(state);
    expect(assistants).toHaveLength(1);
    expect(assistants[0].name).toBe("AgentDesk企伴");
    expect(assistants[0].text).toBe("你好，我在");
    expect(assistants[0].traceEvents.length).toBeGreaterThanOrEqual(2);
  });

  it("clears live assistant text on content_reset so auto-continue does not duplicate replies", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "AgentDesk企伴" });
    state = apply(state, {
      type: "text_delta",
      sender: "AgentDesk企伴",
      delta: "你好，我是 AgentDesk 企伴。",
    });
    state = apply(state, { type: "thinking_start" });
    state = apply(state, {
      type: "info",
      label: "继续执行…",
      detail: "模型正在下一轮推理",
    });
    state = apply(state, { type: "content_reset" });
    state = apply(state, {
      type: "text_delta",
      sender: "AgentDesk企伴",
      delta: "你好，我是 AgentDesk 企伴，你的本地 AI 助手。",
    });

    const assistants = assistantTurns(state);
    expect(assistants).toHaveLength(1);
    expect(assistants[0].text).toBe("你好，我是 AgentDesk 企伴，你的本地 AI 助手。");
    expect(assistants[0].traceEvents.length).toBeGreaterThan(0);
  });

  it("promotes thinking-only reply into assistant bubble via text_delta", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "AgentDesk企伴" });
    state = apply(state, { type: "thinking_start" });
    state = apply(state, {
      type: "thinking_delta",
      detail: "你好！我是 AgentDesk企伴",
    });
    state = apply(state, {
      type: "thinking_end",
      detail: "你好！我是 AgentDesk企伴，你的企业智能工作助手。",
    });
    state = apply(state, {
      type: "text_delta",
      sender: "AgentDesk企伴",
      content: "你好！我是 AgentDesk企伴，你的企业智能工作助手。",
    });
    state = apply(state, { type: "done" });

    const assistants = assistantTurns(state);
    expect(assistants).toHaveLength(1);
    expect(assistants[0].text).toBe("你好！我是 AgentDesk企伴，你的企业智能工作助手。");
    expect(assistants[0].traceEvents.map((evt) => evt.type)).toEqual([
      "thinking_start",
      "thinking_delta",
      "thinking_end",
    ]);
  });

  it("keeps live trace counts monotonic and never empties them mid-stream", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "AgentDesk企伴" });

    const sequence: ChatStreamEvent[] = [
      { type: "thinking_start" },
      { type: "thinking_delta", detail: "想" },
      { type: "thinking_end", detail: "想好了" },
      { type: "tool_call_start", tool_call_id: "c1", tool_name: "read_file" },
      {
        type: "tool_result_end",
        tool_call_id: "c1",
        tool_name: "read_file",
        detail: "ok",
        state: "success",
      },
      { type: "info", label: "提示" },
      { type: "text_delta", delta: "结果" },
    ];

    const traceLengths: number[] = [];
    const counterTotals: number[] = [];
    for (const evt of sequence) {
      state = apply(state, evt);
      const assistant = state.turns.find((turn) => turn.role === "assistant");
      traceLengths.push(assistant?.traceEvents.length ?? 0);
      counterTotals.push(liveTraceTotal(state));
    }

    for (let i = 1; i < traceLengths.length; i += 1) {
      expect(traceLengths[i]).toBeGreaterThanOrEqual(traceLengths[i - 1]);
      expect(counterTotals[i]).toBeGreaterThanOrEqual(counterTotals[i - 1]);
    }
    // Trace is never emptied once it has started.
    expect(Math.min(...traceLengths)).toBeGreaterThan(0);
    expect(counterTotals[counterTotals.length - 1]).toBeGreaterThan(0);
  });

  it("merges (union) live trace on mid-stream hydration rather than replacing it", () => {
    // The 2s run-status poll re-hydrates with a still-streaming server message
    // whose persisted trace lags behind the live one. The merge must keep the
    // richer live trace so counters never drop mid-stream.
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "AgentDesk企伴" });
    state = apply(state, { type: "thinking_start" });
    state = apply(state, {
      type: "tool_call_start",
      tool_call_id: "c1",
      tool_name: "read_file",
    });
    state = apply(state, {
      type: "tool_result_end",
      tool_call_id: "c1",
      tool_name: "read_file",
      detail: "ok",
      state: "success",
    });

    const before = liveTraceTotal(state);
    const beforeLen = assistantTurns(state)[0].traceEvents.length;

    const next = hydrateChatStreamState(state, {
      messages: [
        { role: "user", id: "u1", content: "hi" },
        {
          role: "assistant",
          id: "a1",
          content: "",
          sender: "AgentDesk企伴",
          streaming: true,
        },
      ],
      events: [],
      runActive: true,
    });

    expect(assistantTurns(next)).toHaveLength(1);
    expect(assistantTurns(next)[0].traceEvents.length).toBeGreaterThanOrEqual(
      beforeLen,
    );
    expect(liveTraceTotal(next)).toBeGreaterThanOrEqual(before);
  });

  it("replaces (not concatenates) the live turn when a final message diverges from streamed deltas", () => {
    // Regression: a final `message` whose formatting differs from the streamed
    // deltas must REPLACE the turn text, never produce `deltas\n\nmessage`.
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "AgentDesk企伴" });
    state = apply(state, {
      type: "text_delta",
      sender: "AgentDesk企伴",
      delta: "你好，我在",
    });
    state = apply(state, {
      type: "message",
      sender: "AgentDesk企伴",
      content: "你好，我在。有什么可以帮你？",
    });

    const assistants = assistantTurns(state);
    expect(assistants).toHaveLength(1);
    expect(assistants[0].text).toBe("你好，我在。有什么可以帮你？");
    expect(assistants[0].text).not.toContain("\n\n");
    expect(assistants[0].streaming).toBe(false);
  });

  it("keeps the streamed superset when the final message is a truncated prefix", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "AgentDesk企伴" });
    state = apply(state, {
      type: "text_delta",
      sender: "AgentDesk企伴",
      delta: "完整的流式回复内容很长",
    });
    state = apply(state, {
      type: "message",
      sender: "AgentDesk企伴",
      content: "完整的流式回复",
    });

    expect(assistantTurns(state)[0].text).toBe("完整的流式回复内容很长");
  });

  it("does not duplicate the user message when hydrating from server snapshot", () => {
    // The optimistic local user turn and the server-persisted user message must
    // collapse into a single user turn (no duplicate bubble) after hydration.
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "AgentDesk企伴" });
    state = apply(state, {
      type: "text_delta",
      sender: "AgentDesk企伴",
      delta: "回复中",
    });

    const next = hydrateChatStreamState(state, {
      messages: [
        { role: "user", id: "u1", content: "你好" },
        {
          role: "assistant",
          id: "a1",
          sender: "AgentDesk企伴",
          content: "回复中",
          streaming: false,
        },
      ] as TaskMessage[],
      events: [],
      runActive: false,
    });

    const userTurns = next.turns.filter((turn) => turn.role === "user");
    expect(userTurns).toHaveLength(1);
    expect(userTurns[0].text).toBe("你好");
  });

  it("opens a new assistant bubble after a finalized reply on the next stream_start", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "AgentDesk企伴" });
    state = apply(state, {
      type: "text_delta",
      sender: "AgentDesk企伴",
      delta: "请您直接给出上述信息。",
    });
    state = apply(state, { type: "done" });

    expect(assistantTurns(state)).toHaveLength(1);
    expect(assistantTurns(state)[0].text).toBe("请您直接给出上述信息。");
    expect(assistantTurns(state)[0].streaming).toBe(false);

    state = apply(state, { type: "stream_start", sender: "AgentDesk企伴" });
    state = apply(state, {
      type: "text_delta",
      sender: "AgentDesk企伴",
      delta: "明白了！您要创建 AI 新闻采集专家。",
    });

    expect(assistantTurns(state)).toHaveLength(2);
    expect(assistantTurns(state)[0].text).toBe("请您直接给出上述信息。");
    expect(assistantTurns(state)[1].text).toBe("明白了！您要创建 AI 新闻采集专家。");
  });

  it("prefers richer persisted text on auto-continue conflict during active run", () => {
    let state = createChatStreamState();
    state = apply(state, { type: "stream_start", sender: "新闻分析师" });
    state = apply(state, {
      type: "text_delta",
      sender: "新闻分析师",
      delta: "现在启动浏览器...",
    });

    const next = hydrateChatStreamState(state, {
      messages: [
        { role: "user", id: "u1", content: "分析新闻" },
        {
          role: "assistant",
          id: "a1",
          sender: "新闻分析师",
          content:
            "根据 Google News 检索结果，今日 AI 领域有三条重要动态……",
          streaming: true,
        },
      ],
      events: [],
      runActive: true,
    });

    expect(assistantTurns(next)[0].text).toContain("Google News");
  });

  it("keys the live turn by message_id when stream_start carries one", () => {
    let state = createChatStreamState();
    state = apply(state, {
      type: "stream_start",
      sender: "AgentDesk企伴",
      message_id: "draft-abc",
    });
    state = apply(state, {
      type: "text_delta",
      message_id: "draft-abc",
      delta: "hello",
    });

    expect(state.turns).toHaveLength(1);
    expect(state.turns[0].id).toBe("draft-abc");
    expect(state.turns[0].text).toBe("hello");
  });

  it("routes trace-only events to employee stream_start turn in single mode", () => {
    // Regression: employee stream_start carries message_id but thinking/reply_end
    // events omit sender — they must not spawn empty AgentDesk企伴 shells.
    let state = createChatStreamState();
    state = apply(state, {
      type: "stream_start",
      sender: "AI新闻采集专家",
      message_id: "employee-draft-1",
    });
    state = apply(state, {
      type: "text_delta",
      sender: "AI新闻采集专家",
      delta: "今日要闻摘要如下。",
    });
    state = apply(state, { type: "thinking_start" });
    state = apply(state, {
      type: "tool_call_start",
      tool_call_id: "c1",
      tool_name: "search",
    });
    state = apply(state, {
      type: "reply_end",
      sender: "AI新闻采集专家",
      message_id: "employee-draft-1",
    });
    expect(assistantTurns(state)[0].streaming).toBe(false);
    state = apply(state, { type: "done" });

    expect(assistantTurns(state)).toHaveLength(1);
    expect(assistantTurns(state)[0]).toMatchObject({
      id: "employee-draft-1",
      name: "AI新闻采集专家",
      text: "今日要闻摘要如下。",
      streaming: false,
    });
    expect(assistantTurns(state)[0].traceEvents.length).toBeGreaterThan(0);
  });

  it("routes trace-only events to the stream_start message_id turn in team mode", () => {
    // Regression: leader stream_start carries message_id but thinking/reply_end
    // events omit sender — they must not spawn empty AgentDesk企伴 shells.
    let state = createChatStreamState();
    state = apply(state, {
      type: "stream_start",
      sender: "深度调研团队·leader",
      message_id: "leader-draft-1",
    });
    state = apply(state, {
      type: "text_delta",
      sender: "深度调研团队·leader",
      delta: "你好！",
    });
    state = apply(state, { type: "thinking_start" });
    state = apply(state, {
      type: "tool_call_start",
      tool_call_id: "c1",
      tool_name: "search",
    });
    state = apply(state, {
      type: "reply_end",
      sender: "深度调研团队·leader",
      message_id: "leader-draft-1",
    });
    state = apply(state, { type: "done" });

    expect(assistantTurns(state)).toHaveLength(1);
    expect(assistantTurns(state)[0]).toMatchObject({
      id: "leader-draft-1",
      name: "深度调研团队·leader",
      text: "你好！",
      streaming: false,
    });
    expect(assistantTurns(state)[0].traceEvents.length).toBeGreaterThan(0);
  });

  it("prunes trace-only AgentDesk brand shells when another assistant has content", () => {
    let state = createChatStreamState();
    state = {
      ...state,
      turns: [
        {
          id: "leader-draft-1",
          role: "assistant",
          name: "深度调研团队·leader",
          avatarKind: "employee",
          text: "你好！",
          traceEvents: [{ type: "thinking_start" }],
          streaming: false,
        },
        {
          id: "live:assistant:assistant",
          role: "assistant",
          name: "AgentDesk企伴",
          avatarKind: "assistant",
          text: "",
          traceEvents: [{ type: "reply_end" }, { type: "thinking_start" }],
          streaming: false,
        },
      ],
    };
    state = apply(state, { type: "done" });
    expect(assistantTurns(state)).toHaveLength(1);
    expect(assistantTurns(state)[0].name).toBe("深度调研团队·leader");
  });

  it("worker_done closes a hydrated worker turn keyed by message_id", () => {
    let state = hydrateChatStreamState(createChatStreamState(), {
      messages: [
        {
          role: "assistant",
          id: "worker-msg-1",
          sender: "研究员",
          content: "",
          streaming: true,
        },
      ],
      events: [],
      runActive: true,
    });
    state = apply(state, {
      type: "worker_done",
      worker: "研究员",
      actor_id: "研究员",
    });
    const worker = state.turns.find((turn) => turn.id === "worker-msg-1");
    expect(worker?.streaming).toBe(false);
  });

  it("routes unattributed text_delta to the leader while a worker is active", () => {
    let state = createChatStreamState();
    state = apply(state, {
      type: "stream_start",
      sender: "深度调研团队·leader",
      message_id: "leader-msg",
    });
    state = apply(state, { type: "worker_start", actor_id: "研究员", worker: "研究员" });
    state = apply(state, {
      type: "text_delta",
      delta: "Leader 汇总中",
    });
    const leader = state.turns.find((turn) => turn.id === "leader-msg");
    const worker = state.turns.find((turn) => turn.name === "研究员");
    expect(leader?.text).toContain("Leader 汇总中");
    expect(worker?.text ?? "").not.toContain("Leader 汇总中");
  });

  it("worker_start with message_id keys the turn to the persisted bubble", () => {
    let state = createChatStreamState();
    state = apply(state, {
      type: "stream_start",
      sender: "深度调研团队·leader",
      message_id: "leader-msg",
    });
    state = apply(state, {
      type: "worker_start",
      actor_id: "研究员",
      worker: "研究员",
      message_id: "worker-msg-1",
    });
    expect(state.turns.filter((turn) => turn.name === "研究员")).toHaveLength(1);
    expect(state.turns.find((turn) => turn.name === "研究员")?.id).toBe(
      "worker-msg-1",
    );
    state = apply(state, {
      type: "text_delta",
      actor_id: "研究员",
      worker: "研究员",
      message_id: "worker-msg-1",
      delta: "调研结果",
    });
    expect(state.turns.find((turn) => turn.id === "worker-msg-1")?.text).toBe(
      "调研结果",
    );
  });
});
