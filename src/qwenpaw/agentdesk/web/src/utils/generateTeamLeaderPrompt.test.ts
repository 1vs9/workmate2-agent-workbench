import { describe, expect, it } from "vitest";

import { generateTeamLeaderPrompt } from "./generateTeamLeaderPrompt";

describe("generateTeamLeaderPrompt", () => {
  it("requires team name", () => {
    expect(
      generateTeamLeaderPrompt({
        teamName: "  ",
        members: [{ name: "分析师" }],
      }),
    ).toEqual({ ok: false, reason: "missing_name" });
  });

  it("requires at least one member", () => {
    expect(
      generateTeamLeaderPrompt({
        teamName: "增长团队",
        members: [],
      }),
    ).toEqual({ ok: false, reason: "missing_members" });
  });

  it("generates orchestrator-only prompt with team name and members", () => {
    const result = generateTeamLeaderPrompt({
      teamName: "增长团队",
      members: [
        { name: "投放专家", desc: "负责广告投放与预算优化" },
        { name: "内容编辑", desc: "负责文案与素材产出" },
      ],
    });

    expect(result.ok).toBe(true);
    if (!result.ok) return;

    expect(result.prompt).toContain("增长团队");
    expect(result.prompt).toContain("调度、规划、派工与汇总");
    expect(result.prompt).toContain("不亲自执行具体任务");
    expect(result.prompt).toContain("**投放专家**");
    expect(result.prompt).toContain("负责广告投放与预算优化");
    expect(result.prompt).toContain("**内容编辑**");
    expect(result.prompt).toContain("@成员名");
    expect(result.prompt).toContain("不替代执行者");
  });

  it("falls back when member has no description", () => {
    const result = generateTeamLeaderPrompt({
      teamName: "研发组",
      members: [{ name: "后端工程师" }],
    });

    expect(result.ok).toBe(true);
    if (!result.ok) return;

    expect(result.prompt).toContain("**后端工程师**：按岗位完成 Leader 派工任务");
  });

  it("summarizes long member descriptions", () => {
    const longDesc = `${"很长的职责说明".repeat(20)}。第二句不应出现。`;
    const result = generateTeamLeaderPrompt({
      teamName: "运营组",
      members: [{ name: "运营", desc: longDesc }],
    });

    expect(result.ok).toBe(true);
    if (!result.ok) return;

    expect(result.prompt).toContain("…");
    expect(result.prompt).not.toContain("第二句不应出现");
  });
});
