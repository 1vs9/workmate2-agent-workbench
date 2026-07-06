import { describe, expect, it, vi } from "vitest";

import { buildEmployeeAssignee } from "../types/assignee";
import { openDispatchTaskFlow } from "./openDispatchTaskFlow";

vi.mock("../api/tasks", () => ({
  buildTaskTitle: (text: string) => text,
  tasksApi: {
    create: vi.fn(async () => ({ id: "task-1", title: "派发 · 量化策略师" })),
  },
}));

describe("openDispatchTaskFlow", () => {
  it("creates a task and navigates with assignee preset", async () => {
    const assignee = buildEmployeeAssignee({
      name: "量化策略师",
      avatar: "📈",
      desc: "量化分析",
      tags: ["金融"],
    });
    const resetForNewChat = vi.fn();
    const prependTask = vi.fn();
    const setActiveTaskId = vi.fn();
    const navigate = vi.fn();

    await openDispatchTaskFlow({
      assignee,
      resetForNewChat,
      prependTask,
      setActiveTaskId,
      navigate,
    });

    expect(resetForNewChat).toHaveBeenCalledWith([], assignee);
    expect(prependTask).toHaveBeenCalledWith(
      expect.objectContaining({ id: "task-1" }),
    );
    expect(setActiveTaskId).toHaveBeenCalledWith("task-1");
    expect(navigate).toHaveBeenCalledWith("/task/task-1", { replace: true });
  });
});
