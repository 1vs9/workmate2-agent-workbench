import { describe, expect, it } from "vitest";
import {
  aggregateTraceEvents,
  summarizeTraceSteps,
} from "./aggregateTraceEvents";

describe("aggregateTraceEvents", () => {
  it("merges thinking deltas into one step", () => {
    const steps = aggregateTraceEvents([
      { type: "trace", step: "thinking_start" },
      { type: "trace", step: "thinking_delta", detail: "Hello " },
      { type: "trace", step: "thinking_delta", detail: "world" },
      { type: "trace", step: "thinking_end", detail: "Hello world" },
    ]);
    expect(steps).toHaveLength(1);
    expect(steps[0]).toMatchObject({
      kind: "thinking",
      content: "Hello world",
      status: "done",
    });
  });

  it("groups tool lifecycle by call id", () => {
    const steps = aggregateTraceEvents([
      { type: "trace", step: "tool_call_start", tool_name: "search", tool_call_id: "c1" },
      { type: "trace", step: "tool_call_end", tool_name: "search", tool_call_id: "c1", detail: '{"q":"test"}' },
      { type: "trace", step: "tool_result_end", tool_name: "search", tool_call_id: "c1", detail: "ok", state: "success" },
    ]);
    expect(steps).toHaveLength(1);
    expect(steps[0]).toMatchObject({
      kind: "tool",
      name: "search",
      args: '{"q":"test"}',
      output: "ok",
      status: "success",
    });
  });

  it("streams tool output deltas into one tool step", () => {
    const steps = aggregateTraceEvents([
      { type: "trace", step: "tool_call_start", tool_name: "execute_shell_command", tool_call_id: "c1" },
      { type: "trace", step: "tool_result_delta", tool_name: "execute_shell_command", tool_call_id: "c1", detail: "line1\n" },
      { type: "trace", step: "tool_result_delta", tool_name: "execute_shell_command", tool_call_id: "c1", detail: "line2\n" },
      { type: "trace", step: "tool_result_end", tool_name: "execute_shell_command", tool_call_id: "c1", detail: "line1\nline2\n", state: "success" },
    ]);
    expect(steps).toHaveLength(1);
    expect(steps[0]).toMatchObject({
      kind: "tool",
      name: "execute_shell_command",
      output: "line1\nline2\n",
      status: "success",
    });
  });

  it("summarizes step counts", () => {
    const steps = aggregateTraceEvents([
      { type: "trace", step: "thinking_start" },
      { type: "trace", step: "tool_call_start", tool_name: "run", tool_call_id: "c1" },
    ]);
    expect(summarizeTraceSteps(steps)).toBe("工具调用 1，过程消息 1");
  });

  it("matches tool_result_end to last open tool without call id", () => {
    const steps = aggregateTraceEvents([
      { type: "trace", step: "tool_call_start", tool_name: "chat_with_agent", tool_call_id: "c1" },
      { type: "trace", step: "tool_call_end", tool_name: "chat_with_agent", tool_call_id: "c1", detail: "{}" },
      { type: "trace", step: "tool_result_end", tool_name: "chat_with_agent", detail: "SIM card info", state: "success" },
    ]);
    expect(steps).toHaveLength(1);
    expect(steps[0]).toMatchObject({
      kind: "tool",
      name: "chat_with_agent",
      output: "SIM card info",
      status: "success",
    });
  });

  it("finalizes open tools when stream ended", () => {
    const steps = aggregateTraceEvents(
      [
        { type: "trace", step: "tool_call_start", tool_name: "chat_with_agent", tool_call_id: "c1" },
        { type: "trace", step: "tool_call_end", tool_name: "chat_with_agent", tool_call_id: "c1" },
      ],
      { finalizeOpenTools: true },
    );
    expect(steps[0]).toMatchObject({ kind: "tool", status: "success" });
  });

  it("finalizes open thinking when stream ended", () => {
    const steps = aggregateTraceEvents(
      [
        { type: "trace", step: "thinking_start" },
        { type: "trace", step: "thinking_delta", detail: "still thinking" },
      ],
      { finalizeOpenThinking: true },
    );
    expect(steps).toHaveLength(1);
    expect(steps[0]).toMatchObject({
      kind: "thinking",
      content: "still thinking",
      status: "done",
    });
  });

  it("removes thinking step on thinking_retract", () => {
    const steps = aggregateTraceEvents([
      { type: "trace", step: "thinking_start" },
      { type: "trace", step: "thinking_delta", detail: "narrative" },
      { type: "trace", step: "thinking_retract" },
      { type: "trace", step: "tool_call_start", tool_name: "search", tool_call_id: "c1" },
    ]);
    expect(steps.some((s) => s.kind === "thinking")).toBe(false);
    expect(steps).toHaveLength(1);
    expect(steps[0].kind).toBe("tool");
  });

  it("collapses consecutive identical info steps with repeatCount", () => {
    const info = {
      type: "info" as const,
      label: "继续执行…",
      detail: "模型正在下一轮推理",
    };
    const steps = aggregateTraceEvents([
      info,
      info,
      info,
      { type: "trace", step: "tool_call_start", tool_name: "check_agent_task", tool_call_id: "c1" },
      info,
      info,
    ]);
    const infoSteps = steps.filter((s) => s.kind === "info");
    expect(infoSteps).toHaveLength(2);
    expect(infoSteps[0]).toMatchObject({
      kind: "info",
      label: "继续执行…",
      detail: "模型正在下一轮推理",
      repeatCount: 3,
    });
    expect(infoSteps[1]).toMatchObject({ repeatCount: 2 });
    expect(steps.filter((s) => s.kind === "tool")).toHaveLength(1);
  });
});
