import { describe, expect, it } from "vitest";

import {
  buildPortraitAvatarUrl,
  buildPortraitAvatarUrlSync,
  generateAvatarFromName,
  generateTeamAvatarFromName,
  portraitAvatarUrl,
} from "./generateAvatarFromName";
import { isAvatarImageUrl, isEmojiAvatar } from "./agentAvatar";

describe("buildPortraitAvatarUrlSync", () => {
  it("returns immediate API path without waiting for crypto", () => {
    const url = buildPortraitAvatarUrlSync("销售助理", "客户跟进", "employee");
    expect(url).toMatch(/^\/api\/avatars\/[a-f0-9]{16}\.svg$/);
  });
});

describe("generateAvatarFromName", () => {
  it("returns stable portrait URL for the same name and description", async () => {
    const first = await generateAvatarFromName("销售助理", "客户跟进专家");
    const second = await generateAvatarFromName("销售助理", "客户跟进专家");
    expect(first).toBe(second);
    expect(first).toMatch(/^\/api\/avatars\/[a-f0-9]{16}\.svg$/);
  });

  it("returns fallback portrait URL for empty name", async () => {
    const url = await generateAvatarFromName("", "");
    expect(url).toMatch(/^\/api\/avatars\/[a-f0-9]{16}\.svg$/);
  });

  it("differs when description changes", async () => {
    const a = await generateAvatarFromName("销售助理", "客户跟进");
    const b = await generateAvatarFromName("销售助理", "舆情分析");
    expect(a).not.toBe(b);
  });
});

describe("generateTeamAvatarFromName", () => {
  it("returns stable team portrait URL for the same name", async () => {
    expect(await generateTeamAvatarFromName("增长团队", "增长协作")).toBe(
      await generateTeamAvatarFromName("增长团队", "增长协作"),
    );
  });

  it("uses team role seed distinct from employee", async () => {
    const employee = await buildPortraitAvatarUrl("增长团队", "协作", "employee");
    const team = await buildPortraitAvatarUrl("增长团队", "协作", "team");
    expect(employee).not.toBe(team);
  });
});

describe("portraitAvatarUrl", () => {
  it("builds API path from seed", () => {
    expect(portraitAvatarUrl("abc123def4567890")).toBe(
      "/api/avatars/abc123def4567890.svg",
    );
  });
});

describe("isEmojiAvatar", () => {
  it("detects legacy emoji placeholders", () => {
    expect(isEmojiAvatar("🤖")).toBe(true);
    expect(isEmojiAvatar("🧠")).toBe(true);
    expect(isEmojiAvatar("/api/avatars/abc.svg")).toBe(false);
    expect(isAvatarImageUrl("/api/avatars/abc.svg")).toBe(true);
    expect(isAvatarImageUrl("🤖")).toBe(false);
  });
});
