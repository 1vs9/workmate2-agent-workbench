import { describe, expect, it } from "vitest";

import type { Task } from "../api/tasks";
import {
  isAgentRunning,
  isTaskRunActive,
  resolveTaskRunStatus,
} from "./taskRunStatus";

describe("taskRunStatus", () => {
  it("reads camelCase runStatus from API", () => {
    const task = { id: "t1", title: "x", runStatus: "running" } satisfies Task;
    expect(resolveTaskRunStatus(task)).toBe("running");
    expect(isTaskRunActive(task)).toBe(true);
  });

  it("falls back to snake_case run_status", () => {
    const task = { id: "t1", title: "x", run_status: "running" } satisfies Task;
    expect(isTaskRunActive(task)).toBe(true);
  });

  it("combines local stream connection with backend status", () => {
    const idle = { id: "t1", title: "x", runStatus: "idle" } satisfies Task;
    expect(isAgentRunning(idle, false)).toBe(false);
    expect(isAgentRunning(idle, true)).toBe(true);

    const running = { id: "t1", title: "x", runStatus: "running" } satisfies Task;
    expect(isAgentRunning(running, false)).toBe(true);
    expect(isAgentRunning(running, true)).toBe(true);
  });

  it("treats reconnect recovery as still running", () => {
    const idle = { id: "t1", title: "x", runStatus: "idle" } satisfies Task;
    expect(isAgentRunning(idle, false, true)).toBe(true);
  });

  it("treats streaming team worker turns as still running", () => {
    const idle = { id: "t1", title: "x", runStatus: "idle" } satisfies Task;
    const turns = [
      {
        id: "w1",
        role: "assistant" as const,
        name: "研究员",
        avatarKind: "team" as const,
        text: "",
        traceEvents: [],
        streaming: true,
      },
    ];
    expect(isAgentRunning(idle, false, false, turns, null)).toBe(true);
  });
});
