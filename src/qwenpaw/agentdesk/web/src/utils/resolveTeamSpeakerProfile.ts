import type { Employee } from "../api/plaza";
import type { Team } from "../api/teams";
import { resolveEmployeeDisplayName } from "../types/assignee";
import { isAvatarImageUrl } from "./agentAvatar";

export interface TeamSpeakerProfile {
  name: string;
  avatar?: string;
  description?: string;
  role: "employee" | "team";
  /** Employee/team name used for portrait seed when `avatar` is missing. */
  portraitName?: string;
  portraitDescription?: string;
}

const LEADER_SUFFIX = "·leader";
const LEGACY_LEADER_SUFFIX = "·编排者";

export function teamLeaderDisplayName(teamName: string): string {
  const name = teamName.trim() || "团队";
  return `${name}${LEADER_SUFFIX}`;
}

export function stripTeamSpeakerRoleSuffix(label: string): string {
  return String(label || "")
    .trim()
    .replace(/\s*[\(（](Leader|队长)[\)）]\s*$/i, "")
    .replace(new RegExp(`${LEADER_SUFFIX}$`, "i"), "")
    .replace(new RegExp(`${LEGACY_LEADER_SUFFIX}$`), "")
    .trim();
}

export function isTeamLeaderSender(
  senderLabel: string,
  team?: Team | null,
): boolean {
  const raw = String(senderLabel || "").trim();
  if (!raw) return false;
  if (new RegExp(`${LEADER_SUFFIX}$`, "i").test(raw)) return true;
  if (raw.endsWith(LEGACY_LEADER_SUFFIX)) return true;
  if (/[\(（]Leader[\)）]|队长/i.test(raw)) return true;
  if (team?.name && raw === teamLeaderDisplayName(team.name)) return true;
  const rosterLeader = String(team?.leader ?? "").trim();
  if (rosterLeader && raw === rosterLeader) return true;
  return false;
}

function findEmployeeByName(
  employees: Employee[],
  name: string,
): Employee | undefined {
  const trimmed = name.trim();
  if (!trimmed) return undefined;
  return employees.find((employee) => {
    if (employee.name === trimmed) return true;
    if (employee.agent_id === trimmed || employee.id === trimmed) return true;
    return resolveEmployeeDisplayName(employee) === trimmed;
  });
}

function normalizeSpeakerAvatar(avatar?: string): string | undefined {
  const trimmed = avatar?.trim();
  if (!trimmed || !isAvatarImageUrl(trimmed)) return undefined;
  return trimmed;
}

/** Avatar/name metadata for team assignee UI (composer toolbar, etc.). */
export function resolveTeamRepresentativeProfile(
  team: Team,
  employees: Employee[],
): TeamSpeakerProfile {
  return resolveTeamSpeakerProfile(teamLeaderDisplayName(team.name), team, employees);
}

export function resolveTeamSpeakerProfile(
  senderLabel: string,
  team: Team | null | undefined,
  employees: Employee[],
): TeamSpeakerProfile {
  const raw = String(senderLabel || "").trim() || "成员";

  if (isTeamLeaderSender(raw, team)) {
    const rosterLeader = String(team?.leader ?? "").trim();
    const leaderEmployee = rosterLeader
      ? findEmployeeByName(employees, rosterLeader)
      : undefined;
    const displayName =
      new RegExp(`${LEADER_SUFFIX}$`, "i").test(raw) || raw.endsWith(LEGACY_LEADER_SUFFIX)
        ? raw
        : team?.name
          ? teamLeaderDisplayName(team.name)
          : raw;

    if (leaderEmployee) {
      return {
        name: displayName,
        avatar: normalizeSpeakerAvatar(leaderEmployee.avatar),
        description: leaderEmployee.desc,
        role: "employee",
        portraitName: leaderEmployee.name,
        portraitDescription: leaderEmployee.desc,
      };
    }

    return {
      name: displayName,
      avatar: normalizeSpeakerAvatar(team?.avatar),
      description: team?.desc,
      role: "team",
      portraitName: team?.name,
      portraitDescription: team?.desc,
    };
  }

  const employeeName = stripTeamSpeakerRoleSuffix(raw);
  const employee =
    findEmployeeByName(employees, employeeName) ??
    findEmployeeByName(employees, raw);
  if (employee) {
    return {
      name: raw,
      avatar: normalizeSpeakerAvatar(employee.avatar),
      description: employee.desc,
      role: "employee",
      portraitName: employee.name,
      portraitDescription: employee.desc,
    };
  }

  return {
    name: raw,
    avatar: normalizeSpeakerAvatar(team?.avatar),
    description: team?.desc,
    role: "team",
    portraitName: team?.name,
    portraitDescription: team?.desc,
  };
}
