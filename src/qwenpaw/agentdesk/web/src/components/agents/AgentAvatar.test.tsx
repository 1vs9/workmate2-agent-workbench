import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AgentAvatar from "./AgentAvatar";

const generateMock = vi.fn();

vi.mock("../../api/avatars", () => ({
  avatarsApi: {
    generate: (...args: unknown[]) => generateMock(...args),
  },
}));

describe("AgentAvatar", () => {
  beforeEach(() => {
    generateMock.mockReset();
    generateMock.mockResolvedValue({
      url: "/api/avatars/abc123def4567890.svg",
      seed: "abc123def4567890",
    });
  });

  it("renders stored portrait URL without initials placeholder", () => {
    render(
      <AgentAvatar
        name="开户协同小队·leader"
        avatar="/api/avatars/deadbeeffeedcafe.svg"
      />,
    );

    expect(screen.queryByText("开户")).toBeNull();
    const img = document.querySelector(".wm-agent-avatar__img") as HTMLImageElement | null;
    expect(img).toBeTruthy();
    expect(img?.getAttribute("src")).toBe("/api/avatars/deadbeeffeedcafe.svg");
    expect(generateMock).not.toHaveBeenCalled();
  });

  it("generates portrait via API when no avatar URL is provided", async () => {
    render(<AgentAvatar name="Alice" description="队长" role="employee" />);

    await waitFor(() => {
      expect(generateMock).toHaveBeenCalledWith({
        name: "Alice",
        description: "队长",
        role: "employee",
      });
    });

    const img = document.querySelector(".wm-agent-avatar__img") as HTMLImageElement | null;
    expect(img?.getAttribute("src")).toBe("/api/avatars/abc123def4567890.svg");
    expect(screen.queryByText("Al")).toBeNull();
  });

  it("uses portraitName for generation when avatar is emoji placeholder", async () => {
    render(
      <AgentAvatar
        name="开户协同小队·leader"
        portraitName="Alice"
        portraitDescription="队长员工"
        avatar="🤖"
        role="employee"
      />,
    );

    await waitFor(() => {
      expect(generateMock).toHaveBeenCalledWith({
        name: "Alice",
        description: "队长员工",
        role: "employee",
      });
    });
    expect(screen.queryByText("开户")).toBeNull();
  });
});
