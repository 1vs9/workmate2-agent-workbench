import { describe, expect, it } from "vitest";
import type { Employee } from "../api/plaza";
import type { Team } from "../api/teams";
import {
  isTeamLeaderSender,
  resolveTeamRepresentativeProfile,
  resolveTeamSpeakerProfile,
  teamLeaderDisplayName,
} from "./resolveTeamSpeakerProfile";

const team: Team = {
  id: "team-1",
  name: "开户协同小队",
  tags: [],
  desc: "协同开户",
  avatar: "https://example.com/team.png",
  members: ["Alice", "Bob"],
  leader: "Alice",
};

const employees: Employee[] = [
  {
    name: "Alice",
    avatar: "https://example.com/alice.png",
    desc: "队长员工",
    tools: [],
    skills: [],
    mcp: [],
  },
  {
    name: "Bob",
    avatar: "https://example.com/bob.png",
    desc: "执行成员",
    tools: [],
    skills: [],
    mcp: [],
  },
];

describe("resolveTeamSpeakerProfile", () => {
  it("maps leader sender to roster leader employee avatar", () => {
    const sender = teamLeaderDisplayName(team.name);
    expect(sender).toBe("开户协同小队·leader");
    expect(isTeamLeaderSender(sender, team)).toBe(true);
    expect(resolveTeamSpeakerProfile(sender, team, employees)).toMatchObject({
      name: sender,
      avatar: "https://example.com/alice.png",
      role: "employee",
      portraitName: "Alice",
      portraitDescription: "队长员工",
    });
  });

  it("maps worker sender to employee avatar", () => {
    expect(resolveTeamSpeakerProfile("Bob", team, employees)).toMatchObject({
      name: "Bob",
      avatar: "https://example.com/bob.png",
      role: "employee",
    });
  });

  it("falls back to team avatar for unknown speaker", () => {
    expect(resolveTeamSpeakerProfile("Unknown", team, employees)).toMatchObject({
      name: "Unknown",
      avatar: team.avatar,
      role: "team",
    });
  });
});

describe("resolveTeamRepresentativeProfile", () => {
  it("uses roster leader employee avatar for composer-style team display", () => {
    expect(resolveTeamRepresentativeProfile(team, employees)).toMatchObject({
      avatar: "https://example.com/alice.png",
      role: "employee",
    });
  });

  it("drops emoji placeholders so AgentAvatar can generate portraits", () => {
    const emojiTeam: Team = {
      ...team,
      avatar: "🧠",
      leader: "Unknown Leader",
    };
    const profile = resolveTeamSpeakerProfile(
      teamLeaderDisplayName(emojiTeam.name),
      emojiTeam,
      [],
    );
    expect(profile.avatar).toBeUndefined();
    expect(profile.role).toBe("team");
    expect(profile.portraitName).toBe(emojiTeam.name);
    expect(profile.portraitDescription).toBe(emojiTeam.desc);
  });
});
