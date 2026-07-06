import type { Employee } from "../api/plaza";
import type { Team } from "../api/teams";
import type { ChatTurn } from "./chatStreamReducer";
import {
  extractDelegationFromTrace,
  resolveMemberRosterName,
} from "./extractMemberDelegations";
import { isLeaderAssistantTurn } from "./sanitizeMemberSession";

export type MemberThreadItem =
  | { kind: "leader"; id: string; text: string }
  | { kind: "member"; turn: ChatTurn };

function normalizeKey(value: string): string {
  return value.trim().toLowerCase();
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

function legacyMemberSessionSuffix(memberName: string): string {
  const safe = memberName.trim().replace(/[^a-zA-Z0-9:_-]/g, "_").slice(0, 48);
  return `member-${safe || "unknown"}`;
}

/**
 * Build the chronological leader↔member conversation for one roster member.
 *
 * We walk ``turns`` in their natural (time) order so multi-round threads read
 * like a normal chat: for every round the leader's delegation bubble (left)
 * appears right before that round's member reply (right). Attribution is by
 * sender / resolved roster name only — the backend persists each worker reply
 * under its own name and tags every delegation trace with ``member_name``.
 */
export function buildMemberConversationThread(
  turns: ChatTurn[],
  memberName: string,
  team: Team | null,
  employees: Employee[],
): MemberThreadItem[] {
  const memberKey = normalizeKey(memberName);
  const memberSuffix = memberSessionSuffix(memberName);
  const memberLegacySuffix = legacyMemberSessionSuffix(memberName);
  const items: MemberThreadItem[] = [];
  const seenDelegationIds = new Set<string>();
  const seenReplyKeys = new Set<string>();

  for (const turn of turns) {
    if (turn.role !== "assistant") continue;

    if (isLeaderAssistantTurn(turn.name, team)) {
      // Emit this leader turn's delegations addressed to this member, in the
      // order their trace events were recorded.
      for (const evt of turn.traceEvents) {
        const parsed = extractDelegationFromTrace(evt, team, employees);
        if (!parsed) continue;
        if (normalizeKey(parsed.memberName) !== memberKey) continue;
        const id =
          parsed.toolCallId?.trim() ||
          `${memberKey}:${normalizeKey(parsed.text)}`;
        if (seenDelegationIds.has(id)) continue;
        seenDelegationIds.add(id);
        items.push({ kind: "leader", id, text: parsed.text });
      }
      continue;
    }

    // A member turn: keep it only if it belongs to this member and carries
    // content (real text, an active stream, or an error). Trust the sender even
    // when the reply names other teammates.
    const turnSuffix = teamSessionSuffix(turn);
    const rosterName =
      turnSuffix === memberSuffix || turnSuffix === memberLegacySuffix
        ? memberName
        : resolveMemberRosterName(turn.name, team, employees);
    if (!rosterName || normalizeKey(rosterName) !== memberKey) continue;
    const hasReply = Boolean(
      turn.text.trim() ||
        turn.streaming ||
        turn.error?.trim() ||
        turn.traceEvents.length > 0,
    );
    if (!hasReply) continue;

    // Collapse exact duplicate reply text (defensive against double persistence)
    // but never drop streaming placeholders, which have no text yet.
    const replyKey = normalizeKey(turn.text).slice(0, 240);
    if (replyKey) {
      if (seenReplyKeys.has(replyKey)) continue;
      seenReplyKeys.add(replyKey);
    }
    items.push({ kind: "member", turn });
  }

  return items;
}

export function getMemberTurnsFromPartition(
  memberTurnsByName: Map<string, ChatTurn[]>,
  memberName: string,
): ChatTurn[] {
  const key = normalizeKey(memberName);
  for (const [name, turns] of memberTurnsByName.entries()) {
    if (normalizeKey(name) === key) return turns;
  }
  return [];
}
