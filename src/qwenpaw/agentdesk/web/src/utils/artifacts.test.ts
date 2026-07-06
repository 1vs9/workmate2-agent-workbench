import { describe, expect, it } from "vitest";
import {
  isExplicitWorkspaceRelPath,
  resolveWorkspacePath,
  skillProductArtifact,
} from "./artifacts";

describe("resolveWorkspacePath", () => {
  const files = [
    "skills/football-scores/SKILL.md",
    "skills/team-strength-analyzer/SKILL.md",
    "README.md",
  ];

  it("keeps explicit workspace-relative skill paths", () => {
    expect(
      resolveWorkspacePath("skills/team-strength-analyzer/SKILL.md", files),
    ).toBe("skills/team-strength-analyzer/SKILL.md");
  });

  it("does not remap explicit paths to another skill when multiple SKILL.md exist", () => {
    expect(
      resolveWorkspacePath("skills/football-scores/SKILL.md", files),
    ).toBe("skills/football-scores/SKILL.md");
  });

  it("normalizes legacy pool paths into workspace skills paths", () => {
    expect(
      resolveWorkspacePath(
        "backend/data/skills/team-strength-analyzer/SKILL.md",
        files,
      ),
    ).toBe("skills/team-strength-analyzer/SKILL.md");
  });

  it("resolves bare SKILL.md when only one exists under skills/", () => {
    expect(resolveWorkspacePath("SKILL.md", ["skills/only-one/SKILL.md"])).toBe(
      "skills/only-one/SKILL.md",
    );
  });
});

describe("isExplicitWorkspaceRelPath", () => {
  it("detects multi-segment workspace paths", () => {
    expect(isExplicitWorkspaceRelPath("skills/foo/SKILL.md")).toBe(true);
    expect(isExplicitWorkspaceRelPath("report.md")).toBe(false);
  });
});

describe("skillProductArtifact", () => {
  it("builds workspace-relative skill product paths", () => {
    const item = skillProductArtifact("daily-fortune");
    expect(item.path).toBe("skills/daily-fortune/SKILL.md");
    expect(item.role).toBe("product");
  });
});
