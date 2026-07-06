import { describe, expect, it } from "vitest";
import {
  classifyHubSkill,
  filterHubResults,
  type HubCategory,
} from "./skillCatalog";

describe("classifyHubSkill", () => {
  it("classifies content creation skills", () => {
    expect(
      classifyHubSkill({
        name: "Word Docx Editor",
        description: "Edit documents",
      }),
    ).toBe("内容创作");
  });

  it("classifies developer skills", () => {
    expect(
      classifyHubSkill({
        name: "GitHub PR Review",
        description: "Review pull requests",
      }),
    ).toBe("开发工具");
  });

  it("classifies AI skills", () => {
    expect(
      classifyHubSkill({
        name: "Claude Agent",
        description: "LLM-powered assistant",
      }),
    ).toBe("AI 智能");
  });

  it("returns null when no keyword matches", () => {
    expect(
      classifyHubSkill({
        name: "Mystery Skill",
        description: "Does something unique",
      }),
    ).toBeNull();
  });
});

describe("filterHubResults", () => {
  const samples = [
    { name: "Word Docx", description: "docs", slug: "word-docx" },
    { name: "Git Helper", description: "git", slug: "git-helper" },
    { name: "Mystery", description: "unknown", slug: "mystery" },
  ];

  it("returns all results for 全部", () => {
    expect(filterHubResults(samples, "全部")).toHaveLength(3);
  });

  it("filters by classified category", () => {
    expect(filterHubResults(samples, "内容创作")).toEqual([samples[0]]);
    expect(filterHubResults(samples, "开发工具")).toEqual([samples[1]]);
  });

  it("hides unclassified skills from specific category tabs", () => {
    expect(filterHubResults(samples, "AI 智能")).toEqual([]);
    expect(filterHubResults(samples, "数据分析")).toEqual([]);
  });

  it("accepts HubCategory union", () => {
    const category: HubCategory = "数据分析";
    expect(filterHubResults(samples, category)).toEqual([]);
  });
});
