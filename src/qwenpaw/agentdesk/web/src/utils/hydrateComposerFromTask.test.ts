import { beforeEach, describe, expect, it } from "vitest";
import type { Task } from "../api/tasks";
import type { Team } from "../api/teams";
import { useComposerStore } from "../store/composerStore";
import { getDefaultAssignee } from "../types/assignee";
import { clearComposerTaskCache, getComposerTaskCache } from "./composerTaskCache";
import {
  hydrateComposerFromTask,
  readComposerSnapshot,
  resolveTaskAssignee,
} from "./hydrateComposerFromTask";
import { seedComposerTaskCache } from "./seedComposerTaskCache";

describe("resolveTaskAssignee", () => {
  it("prefers team metadata over fallback assignee", () => {
    const teams: Team[] = [
      {
        id: "team-1",
        name: "测试团队",
        tags: [],
        avatar: "",
        desc: "",
        members: [],
        leader: "",
      },
    ];
    const task = {
      id: "t1",
      title: "团队任务",
      mode: "team",
      team_id: "team-1",
    } as Task;

    const resolved = resolveTaskAssignee(task, teams, getDefaultAssignee());
    expect(resolved.type).toBe("team");
    expect(resolved.name).toBe("测试团队");
    expect(resolved.teamId).toBe("team-1");
  });

  it("uses employee_name when present", () => {
    const task = {
      id: "t1",
      title: "派发",
      employee_name: "新闻分析师",
    } as Task;

    const resolved = resolveTaskAssignee(task, [], getDefaultAssignee());
    expect(resolved).toEqual({
      type: "employee",
      name: "新闻分析师",
      agentId: "新闻分析师",
      subtitle: getDefaultAssignee().subtitle,
      avatar: getDefaultAssignee().avatar,
    });
  });
});

describe("hydrateComposerFromTask", () => {
  beforeEach(() => {
    useComposerStore.getState().resetForNewChat([]);
  });

  it("hydrates assignee and skills from task metadata", () => {
    hydrateComposerFromTask(
      {
        id: "t1",
        title: "派发",
        employee_name: "新闻分析师",
        skill_names: ["web_search"],
      } as Task,
      [],
    );

    expect(useComposerStore.getState().assignee.name).toBe("新闻分析师");
    expect(useComposerStore.getState().skillNames).toEqual(["web_search"]);
  });

  it("does not wipe pre-seeded skills when task has no metadata yet", () => {
    useComposerStore.getState().resetForNewChat(["employee-creator"]);

    hydrateComposerFromTask(
      {
        id: "t1",
        title: "添加员工",
      } as Task,
      [],
    );

    expect(useComposerStore.getState().skillNames).toEqual(["employee-creator"]);
    expect(useComposerStore.getState().assignee.type).toBe("default");
  });
});

describe("composer task cache", () => {
  beforeEach(() => {
    clearComposerTaskCache();
    useComposerStore.getState().resetForNewChat([]);
  });

  it("restores per-task composer snapshots on switch", () => {
    useComposerStore.getState().resetForNewChat([], {
      type: "employee",
      name: "新闻分析师",
      agentId: "新闻分析师",
    });
    seedComposerTaskCache("task-a");

    useComposerStore.getState().resetForNewChat(["employee-creator"]);
    seedComposerTaskCache("task-b");

    const restoredA = getComposerTaskCache("task-a");
    const restoredB = getComposerTaskCache("task-b");

    expect(restoredA?.assignee.name).toBe("新闻分析师");
    expect(restoredA?.skillNames).toEqual([]);
    expect(restoredB?.skillNames).toEqual(["employee-creator"]);
    expect(readComposerSnapshot().skillNames).toEqual(["employee-creator"]);
  });
});
