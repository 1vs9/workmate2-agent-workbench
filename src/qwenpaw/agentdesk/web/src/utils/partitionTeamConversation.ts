import type { Employee } from "../api/plaza";
import type { Team } from "../api/teams";
import { isAgentDeskBrandName } from "../types/assignee";
import type { ChatTurn } from "./chatStreamReducer";
import { resolveMemberRosterName } from "./extractMemberDelegations";
import {
  dedupeAssistantTurnsByText,
  isLeaderAssistantTurn,
  pruneOrphanLeaderSnippets,
} from "./sanitizeMemberSession";
import { normalizeTeamWorkers } from "./teamForm";

export type MemberSessionStatus = "idle" | "working" | "done";

export interface TeamConversationPartition {
  leaderTurns: ChatTurn[];
  memberTurnsByName: Map<string, ChatTurn[]>;
  memberNames: string[];
}

function teamSessionSuffix(turn: ChatTurn): string {
  const source = (turn.sourceMessage ?? {}) as Record<string, unknown>;
  const raw = String(source.sessionId ?? source.session_id ?? "").trim();
  if (!raw) return "";
  const marker = raw.indexOf(":team:");
  if (marker < 0) return "";
  return raw.slice(marker + ":team:".length);
}

function memberSessionSuffix(memberName: string): string {
  const safe = memberName.trim().replace(/[^a-zA-Z0-9:_-]/g, "_").slice(0, 48);
  return `member:${safe || "unknown"}`;
}

function isMemberSessionSuffix(value: string): boolean {
  return value.startsWith("member:") || value.startsWith("member-");
}

export function partitionTeamConversation(
  turns: ChatTurn[],
  team: Team | null,
  employees: Employee[] = [],
): TeamConversationPartition {
  const roster = team
    ? normalizeTeamWorkers(team.leader, team.members).filter(
        (name) => !isLeaderAssistantTurn(name, team),
      )
    : [];
  const leaderTurns: ChatTurn[] = [];
  const memberTurnsByName = new Map<string, ChatTurn[]>();

  for (const turn of turns) {
    if (turn.role === "user") {
      leaderTurns.push(turn);
      continue;
    }
    if (turn.role !== "assistant") continue;

    const suffix = teamSessionSuffix(turn);
    if (suffix === "leader-native") {
      leaderTurns.push(turn);
      continue;
    }
    if (isMemberSessionSuffix(suffix)) {
      const rosterName =
        roster.find((name) => memberSessionSuffix(name) === suffix) ||
        roster.find(
          (name) => `member-${name.trim().replace(/[^a-zA-Z0-9:_-]/g, "_").slice(0, 48) || "unknown"}` === suffix,
        ) ||
        resolveMemberRosterName(turn.name?.trim() || "", team, employees) ||
        turn.name?.trim() ||
        "";
      if (rosterName && !isLeaderAssistantTurn(rosterName, team)) {
        const existing = memberTurnsByName.get(rosterName) ?? [];
        existing.push({ ...turn, name: rosterName });
        memberTurnsByName.set(rosterName, existing);
        continue;
      }
      if (rosterName && isLeaderAssistantTurn(rosterName, team)) {
        leaderTurns.push(turn);
        continue;
      }
    }

    // Attribution is by sender only. The backend now persists each worker's
    // reply under its own roster name, so a member's self-introduction that
    // happens to mention teammates must NOT be reclassified as leader content.
    const name = turn.name?.trim() || "";
    if (!name || isLeaderAssistantTurn(name, team) || isAgentDeskBrandName(name)) {
      leaderTurns.push(turn);
      continue;
    }

    const rosterName = resolveMemberRosterName(name, team, employees) ?? name;
    if (isLeaderAssistantTurn(rosterName, team) || isLeaderAssistantTurn(name, team)) {
      leaderTurns.push(turn);
      continue;
    }
    const existing = memberTurnsByName.get(rosterName) ?? [];
    existing.push({ ...turn, name: rosterName });
    memberTurnsByName.set(rosterName, existing);
  }

  const seen = new Set(roster.map((memberName) => memberName.toLowerCase()));
  const extras = [...memberTurnsByName.keys()].filter(
    (memberName) =>
      !seen.has(memberName.toLowerCase()) &&
      !isLeaderAssistantTurn(memberName, team),
  );

  return {
    leaderTurns: pruneOrphanLeaderSnippets(
      dedupeAssistantTurnsByText(leaderTurns),
    ),
    memberTurnsByName,
    memberNames: [...roster, ...extras],
  };
}

/** Drop member turns that exactly repeat the leader delegation brief. */
export function dedupeMemberTurnsAgainstDelegation(
  memberTurns: ChatTurn[],
  delegationText?: string,
): ChatTurn[] {
  const brief = delegationText?.trim();
  if (!brief) return memberTurns;
  return memberTurns.filter((turn) => {
    const text = turn.text.trim();
    if (!text) return true;
    return text !== brief;
  });
}

export function memberSessionStatus(turns: ChatTurn[] | undefined): MemberSessionStatus {
  if (!turns?.length) return "idle";
  if (turns.some((turn) => turn.streaming)) return "working";
  if (turns.some((turn) => turn.text.trim() || turn.traceEvents.length > 0)) {
    return "done";
  }
  return "idle";
}
