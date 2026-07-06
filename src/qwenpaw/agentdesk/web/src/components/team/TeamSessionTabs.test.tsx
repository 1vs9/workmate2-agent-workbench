import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Team } from "../../api/teams";
import type { Employee } from "../../api/plaza";
import TeamSessionTabs from "./TeamSessionTabs";

vi.mock("../../api/avatars", () => ({
  avatarsApi: {
    generate: vi.fn().mockResolvedValue({
      url: "/api/avatars/session-tab.svg",
      seed: "session-tab",
    }),
  },
}));

const team: Team = {
  id: "team-invest",
  name: "投资分析团队",
  tags: [],
  desc: "协作分析投资机会",
  avatar: "",
  members: ["风险管理师", "量化投资分析师", "技术面分析师"],
  leader: "PM",
};

const employees: Employee[] = [
  {
    name: "PM",
    avatar: "/api/avatars/pm.svg",
    desc: "Leader",
    tools: [],
    skills: [],
    mcp: [],
  },
  ...team.members.map((name) => ({
    name,
    avatar: `/api/avatars/${encodeURIComponent(name)}.svg`,
    desc: name,
    tools: [],
    skills: [],
    mcp: [],
  })),
];

describe("TeamSessionTabs", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders docked sessions inside a continuous scroll track without an outer border", () => {
    const { container } = render(
      <TeamSessionTabs
        team={team}
        memberNames={team.members}
        memberTurnsByName={new Map()}
        employees={employees}
        activeSession="leader"
        onSelectSession={() => {}}
        docked
      />,
    );

    const tablist = screen.getByRole("tablist", { name: "团队会话参与者" });
    expect(tablist.className).toContain("rounded-full");
    expect(tablist.className).not.toContain("border ");

    const track = container.querySelector("[data-team-session-track]");
    expect(track).toBeTruthy();
    expect(track?.className).toContain("scrollbar-hide");
    expect(track?.className).toContain("overflow-x-auto");
  });

  it("maps vertical wheel movement over the docked list to horizontal scrolling", () => {
    const { container } = render(
      <TeamSessionTabs
        team={team}
        memberNames={team.members}
        memberTurnsByName={new Map()}
        employees={employees}
        activeSession="leader"
        onSelectSession={() => {}}
        docked
      />,
    );

    const track = container.querySelector("[data-team-session-track]") as HTMLDivElement;
    Object.defineProperty(track, "clientWidth", { configurable: true, value: 120 });
    Object.defineProperty(track, "scrollWidth", { configurable: true, value: 480 });

    fireEvent.wheel(track, { deltaY: 64 });

    expect(track.scrollLeft).toBe(64);
  });

  it("registers a non-passive native wheel listener to block vertical page scroll", () => {
    const addEventListener = vi.spyOn(HTMLElement.prototype, "addEventListener");

    render(
      <TeamSessionTabs
        team={team}
        memberNames={team.members}
        memberTurnsByName={new Map()}
        employees={employees}
        activeSession="leader"
        onSelectSession={() => {}}
        docked
      />,
    );

    expect(addEventListener).toHaveBeenCalledWith(
      "wheel",
      expect.any(Function),
      expect.objectContaining({ passive: false }),
    );
  });
});
