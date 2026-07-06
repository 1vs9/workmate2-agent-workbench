import { describe, expect, it } from "vitest";
import { buildChatPayload } from "./buildChatPayload";
import { getDefaultAssignee } from "../types/assignee";
import {
  isSkillCreateMessage,
  isSkillFindMessage,
  SKILL_CREATE_DRAFT,
  SKILL_CREATOR_SKILL,
  SKILL_FIND_DRAFT,
} from "./skillCreate";

describe("isSkillFindMessage", () => {
  it("matches the find draft template", () => {
    expect(isSkillFindMessage(SKILL_FIND_DRAFT)).toBe(true);
  });

  it("matches find requests even when capability contains 创建", () => {
    expect(
      isSkillFindMessage("请帮我查找并自动安装能「创建readme」的skill"),
    ).toBe(true);
  });
});

describe("isSkillCreateMessage", () => {
  it("matches the create draft template", () => {
    expect(isSkillCreateMessage(SKILL_CREATE_DRAFT)).toBe(true);
  });

  it("does not treat find requests as create", () => {
    expect(
      isSkillCreateMessage("请帮我查找并自动安装能「创建readme」的skill"),
    ).toBe(false);
  });

  it("still matches explicit create requests", () => {
    expect(
      isSkillCreateMessage("请帮我创建一个可以实现「股市分析」的skill"),
    ).toBe(true);
  });

  it("does not treat summary follow-ups as create", () => {
    expect(isSkillCreateMessage("把上述功能总结成一段描述")).toBe(false);
  });

  it("does not treat feature lists mentioning skill creation as create", () => {
    expect(
      isSkillCreateMessage(
        "功能列表：\n1. 单任务自主规划\n2. 支持创建自定义skill\n3. 多轮对话",
      ),
    ).toBe(false);
  });
});

describe("buildChatPayload", () => {
  it("routes employee assignees as single-agent turns", () => {
    const payload = buildChatPayload({
      taskId: "task-1",
      message: "hello",
      assignee: {
        type: "employee",
        name: "数据整理师",
        agentId: "emp_data",
      },
      skillNames: [],
      planMode: false,
    });

    expect(payload.mode).toBe("single");
    expect(payload.employee_name).toBe("数据整理师");
    expect(payload.team_id).toBeUndefined();
    expect(payload.team_name).toBeUndefined();
  });

  it("routes team assignees with stable team metadata", () => {
    const payload = buildChatPayload({
      taskId: "task-1",
      message: "hello team",
      assignee: {
        type: "team",
        name: "开户协同小队",
        teamId: "team-1",
      },
      teams: [
        {
          id: "team-1",
          name: "开户协同小队",
          tags: [],
          avatar: "",
          desc: "",
          members: [],
          leader: "",
        },
      ],
      skillNames: [],
      planMode: true,
    });

    expect(payload.mode).toBe("team");
    expect(payload.chat_mode).toBe("chat");
    expect(payload.team_id).toBe("team-1");
    expect(payload.team_name).toBe("开户协同小队");
    expect(payload.employee_name).toBeUndefined();
  });

  it("drops make-skill binding on non-create turns", () => {
    const payload = buildChatPayload({
      taskId: "task-1",
      message: "把上述功能总结成一段描述",
      assignee: getDefaultAssignee(),
      skillNames: [SKILL_CREATOR_SKILL, "web_search"],
      planMode: false,
    });

    expect(payload.intent).toBeUndefined();
    expect(payload.wizard_action).toBeUndefined();
    expect(payload.skill_names).toEqual(["web_search"]);
  });

  it("keeps make-skill on explicit skill create turns", () => {
    const payload = buildChatPayload({
      taskId: "task-1",
      message: "请帮我创建一个可以实现「股市分析」的skill",
      assignee: getDefaultAssignee(),
      skillNames: [SKILL_CREATOR_SKILL],
      planMode: false,
    });

    expect(payload.intent).toBe("skill_create");
    expect(payload.wizard_action).toBe("start");
    expect(payload.skill_names).toEqual([SKILL_CREATOR_SKILL]);
  });

  it("does not start the skill wizard inside a team session", () => {
    const payload = buildChatPayload({
      taskId: "task-1",
      message: "请帮我创建一个可以实现「股市分析」的skill",
      assignee: {
        type: "team",
        name: "研究小队",
        teamId: "team-1",
      },
      skillNames: [SKILL_CREATOR_SKILL],
      planMode: false,
    });

    expect(payload.mode).toBe("team");
    expect(payload.intent).toBeUndefined();
    expect(payload.wizard_action).toBeUndefined();
    expect(payload.skill_names).toEqual([SKILL_CREATOR_SKILL]);
  });
});
