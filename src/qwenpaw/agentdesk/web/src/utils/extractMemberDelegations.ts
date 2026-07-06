import type { StreamEvent } from "../api/chatStream";
import type { Employee } from "../api/plaza";
import type { Team } from "../api/teams";
import type { ChatTurn } from "./chatStreamReducer";
import { stripTeamSpeakerRoleSuffix } from "./resolveTeamSpeakerProfile";

export interface MemberDelegation {
  memberName: string;
  text: string;
  toolCallId?: string;
}

function parseDetail(raw: unknown): Record<string, unknown> {
  if (typeof raw === "object" && raw !== null && !Array.isArray(raw)) {
    return raw as Record<string, unknown>;
  }
  if (typeof raw !== "string") return {};
  const trimmed = raw.trim();
  if (!trimmed) return {};
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    return typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : {};
  } catch {
    return {};
  }
}

function normalizeKey(value: string): string {
  return stripTeamSpeakerRoleSuffix(value).trim().toLowerCase();
}

/** Map agent ids / display labels to canonical roster member names. */
export function buildRosterAliasMap(
  team: Team | null,
  employees: Employee[],
): Map<string, string> {
  const map = new Map<string, string>();
  for (const rosterName of team?.members ?? []) {
    const key = normalizeKey(rosterName);
    if (!key) continue;
    map.set(key, rosterName);
    const employee = employees.find(
      (item) =>
        normalizeKey(item.name) === key ||
        item.agent_id === rosterName,
    );
    if (!employee) continue;
    map.set(normalizeKey(employee.name), rosterName);
    if (employee.agent_id) map.set(normalizeKey(employee.agent_id), rosterName);
    if (employee.id) map.set(normalizeKey(employee.id), rosterName);
  }
  return map;
}

export function resolveMemberRosterName(
  target: string,
  team: Team | null,
  employees: Employee[],
): string | null {
  const trimmed = target.trim();
  if (!trimmed) return null;

  const aliasMap = buildRosterAliasMap(team, employees);
  const aliasHit = aliasMap.get(normalizeKey(trimmed));
  if (aliasHit) return aliasHit;

  const roster = team?.members ?? [];
  for (const name of roster) {
    if (normalizeKey(name) === normalizeKey(trimmed)) return name;
  }

  const employee = employees.find(
    (item) =>
      item.name === trimmed ||
      item.agent_id === trimmed ||
      item.id === trimmed ||
      normalizeKey(item.name) === normalizeKey(trimmed),
  );
  if (employee) {
    for (const name of roster) {
      if (normalizeKey(name) === normalizeKey(employee.name)) return name;
    }
    for (const name of roster) {
      if (
        employee.agent_id &&
        normalizeKey(name) === normalizeKey(employee.agent_id)
      ) {
        return name;
      }
    }
    return employee.name;
  }

  const MIN_SUBSTRING_LEN = 4;
  for (const name of roster) {
    const normalizedName = normalizeKey(name);
    const normalizedTrimmed = normalizeKey(trimmed);
    if (normalizedName.length < MIN_SUBSTRING_LEN || normalizedTrimmed.length < MIN_SUBSTRING_LEN) {
      continue;
    }
    if (
      normalizedTrimmed.includes(normalizedName) ||
      normalizedName.includes(normalizedTrimmed)
    ) {
      return name;
    }
  }

  return trimmed;
}

const DELEGATION_TOOL_NAMES = new Set(["chat_with_agent", "submit_to_agent"]);

export function extractDelegationFromTrace(
  evt: StreamEvent,
  team: Team | null,
  employees: Employee[],
): MemberDelegation | null {
  const toolName = String(evt.tool_name || "");
  if (!DELEGATION_TOOL_NAMES.has(toolName)) return null;
  // Live SSE events carry the step on ``type`` (e.g. "tool_call_end") and have
  // no ``step`` field; persisted/normalized events carry it on ``step``. Accept
  // either so the leader's delegation bubble shows both live and after reload.
  const step = String(evt.step || "");
  const type = String(evt.type || "");
  if (step !== "tool_call_end" && type !== "tool_call_end") return null;

  const detail = parseDetail(evt.detail);
  const args =
    typeof detail.arguments === "object" &&
    detail.arguments !== null &&
    !Array.isArray(detail.arguments)
      ? (detail.arguments as Record<string, unknown>)
      : detail;
  const toAgent = String(args.to_agent ?? args.agent_id ?? "").trim();
  const text = String(args.text ?? "").trim();
  if (!toAgent || !text) return null;

  // The backend tags delegation traces with the resolved roster name
  // (``member_name``); prefer it so we don't rely on agent-id ↔ roster lookups.
  const taggedMember = String(
    (evt as { member_name?: unknown }).member_name ?? "",
  ).trim();
  const memberName =
    (taggedMember && resolveMemberRosterName(taggedMember, team, employees)) ||
    taggedMember ||
    resolveMemberRosterName(toAgent, team, employees);
  if (!memberName) return null;

  return {
    memberName,
    text,
    toolCallId: String(evt.tool_call_id ?? "").trim() || undefined,
  };
}

/** Pull leader delegation prompts from trace events, keyed by member. */
export function extractMemberDelegations(
  leaderTurns: ChatTurn[],
  team: Team | null,
  employees: Employee[],
): MemberDelegation[] {
  const delegations: MemberDelegation[] = [];

  for (const turn of leaderTurns) {
    for (const evt of turn.traceEvents) {
      // Trace events stored on turns are normalized: their ``type`` is the
      // step name (e.g. "tool_call_end"), not the literal "trace". Don't gate
      // on ``type``; ``extractDelegationFromTrace`` already validates the tool
      // name and step, so it safely ignores non-delegation events.
      const parsed = extractDelegationFromTrace(evt, team, employees);
      if (parsed) delegations.push(parsed);
    }
  }

  return delegations;
}

export function latestDelegationForMember(
  delegations: MemberDelegation[],
  memberName: string,
): MemberDelegation | undefined {
  const key = normalizeKey(memberName);
  for (let i = delegations.length - 1; i >= 0; i -= 1) {
    if (normalizeKey(delegations[i].memberName) === key) {
      return delegations[i];
    }
  }
  return undefined;
}

export function parseDelegationFromTraceEvents(
  events: StreamEvent[],
): string | undefined {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const evt = events[i];
    if (!DELEGATION_TOOL_NAMES.has(String(evt.tool_name || ""))) continue;
    const detail = parseDetail(evt.detail);
    const args =
      typeof detail.arguments === "object" &&
      detail.arguments !== null &&
      !Array.isArray(detail.arguments)
        ? (detail.arguments as Record<string, unknown>)
        : detail;
    const text = String(args.text ?? "").trim();
    if (text) return text;
  }
  return undefined;
}
