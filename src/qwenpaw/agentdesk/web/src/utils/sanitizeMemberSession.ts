import type { Team } from "../api/teams";
import type { ChatTurn } from "./chatStreamReducer";
import { isTeamLeaderSender } from "./resolveTeamSpeakerProfile";

function normalizeKey(value: string): string {
  return value.trim().toLowerCase();
}

/** Leader synthesis that lists multiple roster members — not a member reply. */
export function looksLikeLeaderTeamSummary(
  text: string,
  team: Team | null,
): boolean {
  const trimmed = text.trim();
  if (!trimmed || !team?.members?.length) return false;
  let hits = 0;
  for (const name of team.members) {
    if (name.trim() && trimmed.includes(name.trim())) hits += 1;
  }
  return hits >= 2;
}

export function collectLeaderPlainTexts(leaderTurns: ChatTurn[]): string[] {
  return leaderTurns
    .filter((turn) => turn.role === "assistant")
    .map((turn) => turn.text.trim())
    .filter(Boolean);
}

function stripDelegationPrefix(text: string, delegationTexts: string[]): string {
  let result = text.trim();
  for (const brief of delegationTexts) {
    const d = brief.trim();
    if (!d) continue;
    if (result === d) return "";
    if (result.startsWith(d)) {
      result = result.slice(d.length).trim();
    }
  }
  return result;
}

function echoesLeaderPlainText(text: string, leaderTexts: string[]): boolean {
  const trimmed = text.trim();
  if (!trimmed) return false;
  for (const leaderText of leaderTexts) {
    if (!leaderText) continue;
    if (trimmed === leaderText) return true;
    // Use word-overlap ratio instead of raw substring to avoid
    // false positives on legitimate re-statements ("分析季度收入" vs "请分析季度收入趋势").
    const shorter = trimmed.length <= leaderText.length ? trimmed : leaderText;
    const longer = trimmed.length > leaderText.length ? trimmed : leaderText;
    const shortWords = new Set(shorter.toLowerCase().split(/\s+/).filter(Boolean));
    const longWords = longer.toLowerCase().split(/\s+/).filter(Boolean);
    if (shortWords.size < 4) continue; // too short for reliable overlap check
    let overlap = 0;
    for (const w of longWords) {
      if (shortWords.has(w)) overlap += 1;
    }
    // If >= 80% of the shorter text's words appear in the longer one, it's an echo.
    if (overlap / shortWords.size >= 0.8) return true;
  }
  return false;
}

export function sanitizeMemberTurnForSession(
  turn: ChatTurn,
  memberName: string,
  delegationTexts: string[],
  leaderTurns: ChatTurn[],
  team: Team | null,
): ChatTurn | null {
  void memberName;
  let text = stripDelegationPrefix(turn.text, delegationTexts);
  const leaderTexts = collectLeaderPlainTexts(leaderTurns);

  if (looksLikeLeaderTeamSummary(text, team)) return null;
  if (echoesLeaderPlainText(text, leaderTexts)) return null;

  const hasReply = Boolean(text.trim() || turn.streaming || turn.error?.trim());
  if (!hasReply) return null;

  return {
    ...turn,
    text,
    traceEvents: [],
  };
}

export function isLeaderAssistantTurn(name: string, team: Team | null): boolean {
  const trimmed = name.trim();
  if (!trimmed) return true;
  return isTeamLeaderSender(trimmed, team);
}

export function dedupeAssistantTurnsByText(turns: ChatTurn[]): ChatTurn[] {
  const seen = new Set<string>();
  return turns.filter((turn) => {
    if (turn.role !== "assistant") return true;
    const key = normalizeKey(turn.text).slice(0, 240);
    if (key.length < 16) return true;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/** Drop orphan leader fragments (e.g. a lone 「成员」) when a fuller leader turn exists. */
export function pruneOrphanLeaderSnippets(turns: ChatTurn[]): ChatTurn[] {
  const substantive = turns.filter(
    (turn) => turn.role === "assistant" && turn.text.trim().length > 24,
  );
  if (!substantive.length) return turns;
  return turns.filter((turn) => {
    if (turn.role !== "assistant") return true;
    const text = turn.text.trim();
    if (!text) return true;
    if (text.length > 8) return true;
    if (turn.streaming || turn.traceEvents.length > 0) return true;
    return false;
  });
}

export function dedupeMemberTurnsByReplyText(turns: ChatTurn[]): ChatTurn[] {
  const seen = new Set<string>();
  return turns.filter((turn) => {
    const key = normalizeKey(turn.text).slice(0, 240);
    if (!key) return true;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
