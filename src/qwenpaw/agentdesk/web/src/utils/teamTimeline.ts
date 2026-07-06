import type { StreamEvent } from "../api/chatStream";

export type TeamTimelineKind =
  | "user_message"
  | "leader_text"
  | "delegation"
  | "worker_text"
  | "worker_trace"
  | "phase"
  | "round_boundary";

export interface TeamTimelineEntry {
  kind: TeamTimelineKind;
  actor: string;
  seq: number;
  ts: number;
  round_id?: string;
  target?: string;
  text?: string;
  phase?: string;
  label?: string;
  message_id?: string;
  delegation_id?: string;
  trace?: StreamEvent;
  delta?: boolean;
  type?: string;
}

export type MemberTimelineItem =
  | { kind: "leader"; id: string; text: string; entry: TeamTimelineEntry }
  | { kind: "member"; id: string; text: string; entry: TeamTimelineEntry }
  | { kind: "phase"; id: string; label: string; entry: TeamTimelineEntry };

export type LeaderConversationItem =
  | { kind: "user"; id: string; text: string; entry: TeamTimelineEntry }
  | { kind: "leader_text"; id: string; text: string; entry: TeamTimelineEntry }
  | { kind: "delegation"; id: string; text: string; target: string; entry: TeamTimelineEntry }
  | { kind: "phase"; id: string; label: string; target?: string; entry: TeamTimelineEntry };

function normalizeKey(value: string): string {
  return value.trim().toLowerCase();
}

/** Chronological order: ``ts`` first (writers reset ``seq`` each round). */
export function compareTimelineEntries(
  a: TeamTimelineEntry,
  b: TeamTimelineEntry,
): number {
  const tsA = Number(a.ts) || 0;
  const tsB = Number(b.ts) || 0;
  if (tsA !== tsB) return tsA - tsB;
  return Number(a.seq) - Number(b.seq);
}

const PROGRESS_HEADER_RE = /(本轮进度|当前进度|团队进度|协调进度|进度[：:])/;

/** Merge streamed chunks; cumulative rewrites replace instead of append. */
export function mergeStreamTextDelta(existing: string, incoming: string): string {
  if (!incoming) return existing;
  if (!existing) return incoming;
  if (incoming.startsWith(existing) && incoming.length > existing.length) return incoming;
  if (existing.startsWith(incoming) && existing.length > incoming.length) {
    const suffix = existing.slice(incoming.length);
    if (suffix === incoming || (incoming && suffix.startsWith(incoming))) {
      return `${existing}${incoming}`;
    }
    return existing;
  }
  if (PROGRESS_HEADER_RE.test(existing) && PROGRESS_HEADER_RE.test(incoming)) {
    return incoming.length >= existing.length ? incoming : existing;
  }
  if (incoming === existing && incoming.length > 1) return existing;
  return `${existing}${incoming}`;
}

function entryId(entry: TeamTimelineEntry): string {
  const delegation = entry.delegation_id?.trim();
  if (delegation) return `${entry.kind}:${delegation}`;
  return `${entry.kind}:${entry.seq}`;
}

/**
 * Merge a timeline SSE payload into the ordered entry list (by ``seq``).
 */
export function reduceTeamTimeline(
  entries: TeamTimelineEntry[],
  raw: StreamEvent,
): TeamTimelineEntry[] {
  const kind = String(raw.kind ?? "").trim();
  if (!kind) return entries;

  const seq = Number(raw.seq);
  if (!Number.isFinite(seq)) return entries;

  const entry: TeamTimelineEntry = {
    kind: kind as TeamTimelineKind,
    actor: String(raw.actor ?? "").trim(),
    seq,
    ts: Number(raw.ts ?? Date.now()),
    round_id: raw.round_id ? String(raw.round_id) : undefined,
    target: raw.target ? String(raw.target) : undefined,
    text: raw.text ? String(raw.text) : undefined,
    phase: raw.phase ? String(raw.phase) : undefined,
    label: raw.label ? String(raw.label) : undefined,
    message_id: raw.message_id ? String(raw.message_id) : undefined,
    delegation_id: raw.delegation_id ? String(raw.delegation_id) : undefined,
    trace: raw.trace as StreamEvent | undefined,
    delta: raw.delta === true,
    type: "timeline_entry",
  };

  const existingIdx = entries.findIndex((e) => e.seq === seq);
  if (existingIdx >= 0) {
    const next = [...entries];
    const prev = next[existingIdx];
    if (entry.delta && entry.text && prev.text) {
      entry.text = mergeStreamTextDelta(prev.text, entry.text);
      entry.delta = false;
    }
    next[existingIdx] = entry;
    return next.sort(compareTimelineEntries);
  }

  if (entry.delta && entry.text) {
    const sameActor = entries.filter(
      (e) =>
        e.kind === entry.kind &&
        normalizeKey(e.actor) === normalizeKey(entry.actor) &&
        (entry.target
          ? normalizeKey(e.target ?? "") === normalizeKey(entry.target)
          : true),
    );
    const tail = sameActor[sameActor.length - 1];
    if (tail?.delta && tail.text) {
      const next = [...entries];
      const idx = next.findIndex((e) => e.seq === tail.seq);
      if (idx >= 0) {
        next[idx] = {
          ...tail,
          text: mergeStreamTextDelta(tail.text ?? "", entry.text ?? ""),
          ts: entry.ts,
        };
        return next;
      }
    }
  }

  if (
    entry.kind === "phase" &&
    entry.phase === "round_progress"
  ) {
    const tail = entries[entries.length - 1];
    if (tail?.kind === "phase" && tail.phase === "round_progress") {
      return [
        ...entries.slice(0, -1),
        {
          ...tail,
          label: mergeStreamTextDelta(
            tail.label ?? tail.text ?? "",
            entry.label ?? entry.text ?? "",
          ),
          text: mergeStreamTextDelta(tail.text ?? "", entry.text ?? ""),
          ts: entry.ts,
        },
      ];
    }
  }

  if (
    entry.kind === "phase" &&
    entry.phase === "worker_status" &&
    entry.target
  ) {
    const tail = entries[entries.length - 1];
    if (
      tail?.kind === "phase" &&
      tail.phase === "worker_status" &&
      normalizeKey(tail.target ?? "") === normalizeKey(entry.target ?? "")
    ) {
      return [
        ...entries.slice(0, -1),
        {
          ...tail,
          label: entry.label ?? entry.text ?? tail.label,
          text: entry.text ?? tail.text,
          ts: entry.ts,
        },
      ];
    }
  }

  return [...entries, entry].sort(compareTimelineEntries);
}

/**
 * Chronological member-thread items derived from the canonical timeline.
 */
export function buildMemberTimelineView(
  entries: TeamTimelineEntry[],
  memberName: string,
): MemberTimelineItem[] {
  const memberKey = normalizeKey(memberName);
  const items: MemberTimelineItem[] = [];
  const leaderTextBySeq = new Map<number, string>();
  const ordered = [...entries].sort(compareTimelineEntries);

  for (const entry of ordered) {
    if (entry.kind === "leader_text" && entry.text) {
      leaderTextBySeq.set(entry.seq, entry.text);
    }
  }

  for (const entry of ordered) {
    if (entry.kind === "delegation") {
      const target = normalizeKey(entry.target ?? "");
      if (!target || target !== memberKey) continue;
      const text = entry.text?.trim() ?? "";
      if (!text) continue;
      items.push({
        kind: "leader",
        id: entryId(entry),
        text,
        entry,
      });
      continue;
    }

    if (entry.kind === "worker_text") {
      if (normalizeKey(entry.actor) !== memberKey) continue;
      const text = entry.text?.trim() ?? "";
      if (!text) continue;
      items.push({
        kind: "member",
        id: entryId(entry),
        text,
        entry,
      });
      continue;
    }

    if (entry.kind === "phase" && entry.target) {
      if (normalizeKey(entry.target) !== memberKey) continue;
      const label = entry.label?.trim() || entry.phase?.trim() || "进行中";
      items.push({
        kind: "phase",
        id: entryId(entry),
        label,
        entry,
      });
    }
  }

  return items;
}

/**
 * Leader main view: ordered timeline entries with merged leader text segments.
 */
export function buildLeaderTimelineView(
  entries: TeamTimelineEntry[],
): TeamTimelineEntry[] {
  const out: TeamTimelineEntry[] = [];
  let leaderBuffer = "";
  let leaderSeq: number | null = null;
  const ordered = [...entries].sort(compareTimelineEntries);

  const flushLeader = () => {
    if (!leaderBuffer.trim() || leaderSeq === null) return;
    out.push({
      kind: "leader_text",
      actor: ordered.find((e) => e.seq === leaderSeq)?.actor ?? "",
      seq: leaderSeq,
      ts: ordered.find((e) => e.seq === leaderSeq)?.ts ?? Date.now(),
      text: leaderBuffer,
    });
    leaderBuffer = "";
    leaderSeq = null;
  };

  for (const entry of ordered) {
    if (entry.kind === "leader_text") {
      if (entry.delta) {
        leaderBuffer = mergeStreamTextDelta(leaderBuffer, entry.text ?? "");
        leaderSeq = entry.seq;
        continue;
      }
      flushLeader();
      if (entry.text?.trim()) out.push({ ...entry, delta: false });
      continue;
    }
    flushLeader();
    if (entry.kind === "round_boundary") {
      continue;
    }
    out.push(entry);
  }
  flushLeader();
  return out;
}

const TERMINAL_ROUND_PHASES = new Set(["done"]);
const OPERATIONAL_ROUND_PHASES = new Set([
  "planning",
  "waiting_workers",
  "synthesizing",
  "worker_timeout",
  "round_progress",
]);

function shouldIncludePhaseInLeaderView(
  entry: TeamTimelineEntry,
  latestOperationalPhase: TeamTimelineEntry | null,
  roundComplete: boolean,
): boolean {
  const phase = entry.phase?.trim() ?? "";
  if (!phase || entry.kind !== "phase") return false;
  if (TERMINAL_ROUND_PHASES.has(phase)) {
    return roundComplete;
  }
  if (OPERATIONAL_ROUND_PHASES.has(phase)) {
    return !roundComplete && latestOperationalPhase?.seq === entry.seq;
  }
  // Target-specific worker lifecycle phases stay on member tabs.
  if (entry.target) return false;
  return !roundComplete;
}

/**
 * Leader main session: user + leader narration + delegations + phase only.
 * Worker replies and traces belong on member tabs, not here.
 */
export function buildLeaderConversationView(
  entries: TeamTimelineEntry[],
): LeaderConversationItem[] {
  const merged = buildLeaderTimelineView(entries);
  const roundComplete = merged.some(
    (entry) => entry.kind === "phase" && entry.phase === "done",
  );
  const latestOperationalPhase = [...merged]
    .reverse()
    .find(
      (entry) =>
        entry.kind === "phase" &&
        entry.phase &&
        OPERATIONAL_ROUND_PHASES.has(entry.phase),
    ) ?? null;
  const items: LeaderConversationItem[] = [];

  for (const entry of merged) {
    const id = entryId(entry);
    if (entry.kind === "user_message") {
      const text = entry.text?.trim() ?? "";
      if (!text) continue;
      items.push({ kind: "user", id, text, entry });
      continue;
    }
    if (entry.kind === "leader_text") {
      const text = entry.text?.trim() ?? "";
      if (!text) continue;
      items.push({ kind: "leader_text", id, text, entry });
      continue;
    }
    if (entry.kind === "delegation") {
      const text = entry.text?.trim() ?? "";
      const target = entry.target?.trim() ?? "";
      if (!text || !target) continue;
      items.push({ kind: "delegation", id, text, target, entry });
      continue;
    }
    if (entry.kind === "worker_text" || entry.kind === "worker_trace") {
      continue;
    }
    if (entry.kind === "phase") {
      if (!shouldIncludePhaseInLeaderView(entry, latestOperationalPhase, roundComplete)) {
        continue;
      }
      const label =
        entry.label?.trim() ||
        entry.text?.trim() ||
        entry.phase?.trim() ||
        "进行中";
      items.push({
        kind: "phase",
        id,
        label,
        target: entry.target,
        entry,
      });
    }
  }

  return items;
}

const LEADER_STATUS_NARRATION_RE =
  /^[\u4e00-\u9fffA-Za-z0-9·_-]+?(正在|已经|还在|终于|已).+$/;
const STATUS_HINTS = ["正在", "还在", "进行中", "搜索", "分析", "汇总", "等待"];
const ROSTER_TOKENS = ["研究员", "写手", "规划者", "审查官", "主笔", "分析师"];
const PROGRESS_MARKERS = ["已派工", "收到任务", "开始检索", "地毯式", "成稿"];
const SUBSTANTIVE_MARKERS = [
  "综览",
  "总结",
  "报告",
  "全文",
  "全流程回顾",
  "最终成果",
  "事件清单",
  "一周大事件",
  "结构化长文",
];

function isSubstantiveLeaderAnswer(text: string): boolean {
  const stripped = text.trim();
  if (!stripped) return false;
  if (stripped.length >= 400) return true;
  if (/^#{1,3}\s/m.test(stripped)) return true;
  if (
    stripped.length >= 220 &&
    SUBSTANTIVE_MARKERS.some((marker) => stripped.includes(marker))
  ) {
    return true;
  }
  if (stripped.includes("全流程回顾") && stripped.length >= 100) return true;
  return false;
}

/** True when leader ``text_delta`` is orchestration status, not user-facing answer. */
export function isLeaderOrchestrationNarration(text: string): boolean {
  const stripped = text.trim();
  if (!stripped) return false;
  if (isSubstantiveLeaderAnswer(stripped)) return false;
  if (PROGRESS_HEADER_RE.test(stripped)) return true;
  const atMentions = stripped.match(/@[\u4e00-\u9fffA-Za-z0-9·_-]+/g);
  const rosterHits = ROSTER_TOKENS.filter((token) => stripped.includes(token)).length;
  if ((atMentions?.length ?? 0) >= 1 && rosterHits >= 2) return true;
  if (rosterHits >= 2 && PROGRESS_MARKERS.some((marker) => stripped.includes(marker))) {
    return true;
  }
  if (LEADER_STATUS_NARRATION_RE.test(stripped)) return true;
  if (
    stripped.length <= 160 &&
    STATUS_HINTS.some((hint) => stripped.includes(hint)) &&
    ROSTER_TOKENS.some((token) => stripped.includes(token))
  ) {
    return true;
  }
  return false;
}

export function parseTeamTimelineFromTask(
  task: Record<string, unknown> | null | undefined,
): TeamTimelineEntry[] {
  const raw = task?.teamTimeline ?? task?.team_timeline;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item) => item && typeof item === "object")
    .map((item) => item as TeamTimelineEntry)
    .sort(compareTimelineEntries);
}
