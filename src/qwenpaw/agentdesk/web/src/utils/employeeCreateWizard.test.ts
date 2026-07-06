import { describe, expect, it, vi } from "vitest";

import { executeEmployeeCreateWizard } from "./employeeCreateWizard";

vi.mock("../api/plaza", () => ({
  plazaApi: {
    createPlazaCard: vi.fn(),
    joinPlaza: vi.fn(),
  },
}));

vi.mock("../api/avatars", () => ({
  avatarsApi: {
    generate: vi.fn(),
  },
}));

import { plazaApi } from "../api/plaza";
import { avatarsApi } from "../api/avatars";

describe("executeEmployeeCreateWizard", () => {
  it("creates plaza card and trusts join-mounted skills", async () => {
    const createMock = vi.mocked(plazaApi.createPlazaCard);
    const joinMock = vi.mocked(plazaApi.joinPlaza);
    const avatarMock = vi.mocked(avatarsApi.generate);

    avatarMock.mockResolvedValue({
      url: "/api/avatars/abc123def4567890.svg",
      seed: "abc123def4567890",
    });
    createMock.mockResolvedValue({
      name: "销售助理",
      desc: "",
      tags: [],
    });
    joinMock.mockResolvedValue({
      name: "销售助理",
      desc: "",
      tools: [],
      skills: ["news", "file_reader"],
      mounted_skills: ["news", "file_reader"],
      mcp: [],
    });

    const result = await executeEmployeeCreateWizard({
      name: "销售助理",
      specialty: "客户跟进",
      background: "3 年销售",
      skillNames: ["news", "file_reader"],
    });

    expect(avatarMock).toHaveBeenCalledWith({
      name: "销售助理",
      description: "专长：客户跟进。经验背景：3 年销售",
      role: "employee",
    });
    expect(createMock).toHaveBeenCalledWith({
      name: "销售助理",
      desc: "专长：客户跟进。经验背景：3 年销售",
      avatar: "/api/avatars/abc123def4567890.svg",
      tags: ["AgentDesk", "客户跟进"],
      skills: ["news", "file_reader"],
    });
    expect(joinMock).toHaveBeenCalledWith("销售助理");
    expect(result.mountedSkills).toEqual(["news", "file_reader"]);
    expect(result.avatar).toBe("/api/avatars/abc123def4567890.svg");
  });
});
