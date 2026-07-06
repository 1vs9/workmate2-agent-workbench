import { describe, expect, it, vi } from "vitest";

import {
  EMPLOYEE_CREATE_DRAFT,
  EMPLOYEE_CREATE_MARKER,
  EMPLOYEE_CREATOR_SKILL,
  EMPLOYEE_CREATOR_TAG,
} from "./employeeCreate";
import { openEmployeeCreateFlow } from "./openEmployeeCreateFlow";

vi.mock("../api/skills", () => ({
  skillsApi: {
    importBuiltin: vi.fn(async () => undefined),
    mountSkill: vi.fn(async () => undefined),
  },
}));

vi.mock("../api/tasks", () => ({
  buildTaskTitle: (text: string) => text,
  tasksApi: {
    create: vi.fn(async () => ({ id: "task-emp-1", title: "添加员工" })),
  },
}));

describe("openEmployeeCreateFlow", () => {
  it("creates a task with employee-creator skill and prefilled composer draft", async () => {
    const { skillsApi } = await import("../api/skills");
    const resetForNewChat = vi.fn();
    const prependTask = vi.fn();
    const setActiveTaskId = vi.fn();
    const navigate = vi.fn();

    await openEmployeeCreateFlow({
      resetForNewChat,
      prependTask,
      setActiveTaskId,
      navigate,
    });

    expect(skillsApi.importBuiltin).toHaveBeenCalledWith([EMPLOYEE_CREATOR_SKILL]);
    expect(skillsApi.mountSkill).toHaveBeenCalledWith(EMPLOYEE_CREATOR_SKILL, {
      scope: "agent",
    });
    expect(resetForNewChat).toHaveBeenCalledWith([EMPLOYEE_CREATOR_SKILL]);
    expect(prependTask).toHaveBeenCalledWith(
      expect.objectContaining({ id: "task-emp-1" }),
    );
    expect(setActiveTaskId).toHaveBeenCalledWith("task-emp-1");
    expect(navigate).toHaveBeenCalledWith("/task/task-emp-1", {
      replace: true,
      state: {
        composerDraft: EMPLOYEE_CREATE_DRAFT,
        selectDraftMarker: EMPLOYEE_CREATE_MARKER,
        skillTag: EMPLOYEE_CREATOR_TAG,
      },
    });
  });
});
