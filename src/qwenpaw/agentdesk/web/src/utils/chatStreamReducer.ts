import type { StreamEvent } from "../api/chatStream";
import type { TaskEvent, TaskMessage } from "../api/tasks";
import { AGENTDESK_BRAND_NAME, isAgentDeskBrandName } from "../types/assignee";
import { reduceTeamTimeline, type TeamTimelineEntry } from "./teamTimeline";

type ChatTurnRole = "user" | "assistant";
type AvatarKind = "user" | "assistant" | "employee" | "team" | "system";

export interface ChatTurn {
  id: string;
  role: ChatTurnRole;
  name: string;
  avatarKind: AvatarKind;
  text: string;
  traceEvents: StreamEvent[];
  streaming: boolean;
  error?: string;
  sourceMessage?: TaskMessage;
}

export interface ChatStreamState {
  turns: ChatTurn[];
  streamActive: boolean;
  activeActorId?: string;
  /** Server draft id from the latest ``stream_start`` (team leader / agent). */
  activeTurnId?: string;
  /** Leader draft id preserved while a delegated worker turn is active. */
  leaderTurnId?: string;
  /** Canonical team timeline entries from ``timeline_entry`` SSE events. */
  teamTimeline?: TeamTimelineEntry[];
}

export type ChatStreamEvent = StreamEvent & { type: string };

// Single canonical display identity for the default AgentDesk agent. The backend
// persists/streams the default agent under `AgentDesk企伴` (see default_agent.py
// DEFAULT_DISPLAY_NAME); using the same constant as the fallback keeps the agent
// from splitting into two rows (e.g. "AgentDesk企伴" vs the old "WorkBuddy").
const ASSISTANT_NAME = AGENTDESK_BRAND_NAME;
const LIVE_TRACE_CAP = 500;
const TRACE_STEPS = new Set([
  "reply_start",
  "reply_end",
  "skills_active",
  "info",
  "thinking_start",
  "thinking_delta",
  "thinking_end",
  "thinking_retract",
  "tool_call_start",
  "tool_call_end",
  "tool_result_start",
  "tool_result_delta",
  "tool_result_end",
]);
const EMPTY_REPLY_PLACEHOLDER = "本轮未收到可渲染回复，请重试。";

function messageText(msg: TaskMessage): string {
  const content = msg.content;
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") return part;
        if (part && typeof part === "object" && "text" in part) {
          return String((part as { text?: unknown }).text ?? "");
        }
        return "";
      })
      .join("");
  }
  return "";
}

function assistantTurnId(actorId: string): string {
  return `live:assistant:${actorId || "assistant"}`;
}

/** Prefer the server-assigned message id; fall back to the per-actor live slot. */
function resolveTurnId(
  event: ChatStreamEvent,
  actorId: string,
  activeTurnId?: string,
  activeActorId?: string,
): string {
  const messageId = String(event.message_id ?? "").trim();
  if (messageId) return messageId;
  const eventActorId = resolveActorId(event);
  if (
    activeTurnId &&
    (!eventActorId || !activeActorId || eventActorId === activeActorId)
  ) {
    return activeTurnId;
  }
  return assistantTurnId(actorId);
}

/**
 * When a round finishes the live turn keeps the generic `live:assistant:*` id
 * until hydration retargets it. Before the next `stream_start`, retire that id
 * so the new reply opens a fresh bubble instead of appending to the old one.
 */
function retireFinalizedLiveTurn(turns: ChatTurn[], liveId: string): ChatTurn[] {
  const idx = turns.findIndex((turn) => turn.id === liveId);
  if (idx < 0) return turns;
  const turn = turns[idx];
  if (turn.streaming || !turn.id.startsWith("live:assistant:")) return turns;
  const stableId =
    (turn.sourceMessage?.id && String(turn.sourceMessage.id)) ||
    `msg:assistant:${idx}`;
  if (stableId === turn.id) return turns;
  const next = [...turns];
  next[idx] = { ...turn, id: stableId };
  return next;
}

function resolveActorId(evt: Record<string, unknown>): string {
  return String(
    evt.actor_id || evt.source_member || evt.worker || "",
  )
    .trim()
    .toLowerCase();
}

/** Display name carried by an event, if any (never the normalized actor key). */
function eventSenderName(evt: Record<string, unknown>): string {
  return String(evt.sender || evt.worker || evt.source_member || "").trim();
}

function resolveActorName(evt: Record<string, unknown>): string {
  return eventSenderName(evt) || ASSISTANT_NAME;
}

/**
 * Name to write when updating an existing turn. Many in-stream events (text
 * deltas, trace steps) omit attribution; in that case we must KEEP the turn's
 * established name instead of overwriting it with the brand fallback or a
 * lowercased actor key — otherwise the same speaker flickers between names.
 */
function nameForUpdate(evt: Record<string, unknown>, current: string): string {
  return eventSenderName(evt) || current || ASSISTANT_NAME;
}

function avatarFor(name: string): AvatarKind {
  if (name === "系统" || name.toLowerCase() === "system") return "system";
  return name === ASSISTANT_NAME ? "assistant" : "employee";
}

function appendTurn(turns: ChatTurn[], nextTurn: ChatTurn): ChatTurn[] {
  return [...turns, nextTurn];
}

function appendTraceEvent(turn: ChatTurn, traceEvent: StreamEvent): ChatTurn {
  const nextTraceEvents = [
    ...turn.traceEvents.slice(-(LIVE_TRACE_CAP - 1)),
    traceEvent,
  ];
  return {
    ...turn,
    streaming: true,
    traceEvents: nextTraceEvents,
  };
}

function fanInWorkerTraceForLeader(
  event: ChatStreamEvent,
  leaderTurnId: string,
  workerLabel: string,
): StreamEvent {
  const type = String(event.type || "");
  const callId = String(event.tool_call_id ?? "").trim();
  const scopedCallId = callId
    ? `fanin:${workerLabel}:${callId}`
    : `fanin:${workerLabel}:${type}`;
  const fanIn: StreamEvent = {
    ...event,
    message_id: leaderTurnId,
    member_name: workerLabel,
  };
  if (
    type === "tool_call_start" ||
    type === "tool_call_end" ||
    type === "tool_result_start" ||
    type === "tool_result_delta" ||
    type === "tool_result_end"
  ) {
    fanIn.tool_call_id = scopedCallId;
    const toolName = String(event.tool_name ?? "").trim();
    const rawLabel = String(event.label ?? "").trim();
    if (toolName || rawLabel) {
      const toolPart = rawLabel || (toolName ? `调用 ${toolName}` : "");
      fanIn.label = `${workerLabel} · ${toolPart}`;
    }
  }
  if (type === "info") {
    const label = String(event.label ?? event.content ?? "").trim();
    fanIn.label = label.startsWith(workerLabel)
      ? label
      : `${workerLabel} · ${label}`;
    delete (fanIn as { content?: unknown }).content;
  }
  return fanIn;
}

function updateTurnById(
  turns: ChatTurn[],
  id: string,
  updater: (turn: ChatTurn) => ChatTurn,
): ChatTurn[] {
  const idx = turns.findIndex((turn) => turn.id === id);
  if (idx < 0) return turns;
  const current = turns[idx];
  const updated = updater(current);
  if (updated === current) return turns;
  if (
    updated.text === current.text &&
    updated.streaming === current.streaming &&
    updated.error === current.error &&
    updated.traceEvents === current.traceEvents &&
    updated.name === current.name &&
    updated.avatarKind === current.avatarKind &&
    updated.sourceMessage === current.sourceMessage
  ) {
    return turns;
  }
  const next = [...turns];
  next[idx] = updated;
  return next;
}

function isDelegationTraceEvent(event: ChatStreamEvent): boolean {
  const type = String(event.type || "");
  if (!TRACE_STEPS.has(type)) return false;
  const toolName = String(event.tool_name || "");
  if (toolName === "submit_to_agent" || toolName === "chat_with_agent") return true;
  return Boolean(String(event.member_name || "").trim());
}

function ensureAssistantTurn(state: ChatStreamState, event: ChatStreamEvent): [ChatStreamState, string] {
  const actorId = resolveActorId(event);
  const messageId = String(event.message_id ?? "").trim();
  const senderName = eventSenderName(event);

  // Unattributed text/trace during a team turn must stay on the leader draft.
  // Otherwise activeActorId (often a worker after worker_start) steals leader
  // narration into the wrong member bubble.
  if (!messageId && !actorId && !senderName && state.leaderTurnId) {
    const leaderTurn = state.turns.find((turn) => turn.id === state.leaderTurnId);
    if (leaderTurn) {
      return [state, state.leaderTurnId];
    }
  }

  const resolvedActorId = actorId || state.activeActorId || "assistant";
  let id = resolveTurnId(
    event,
    resolvedActorId,
    state.activeTurnId,
    state.activeActorId,
  );

  // Delegation tool traces belong on the leader bubble even while a worker
  // turn is the active streaming target (worker_start switches activeTurnId).
  if (!messageId && state.leaderTurnId && isDelegationTraceEvent(event)) {
    id = state.leaderTurnId;
  } else if (!messageId && state.leaderTurnId && senderName) {
    const leaderTurn = state.turns.find((turn) => turn.id === state.leaderTurnId);
    if (leaderTurn && sameSpeaker(leaderTurn.name, senderName)) {
      id = state.leaderTurnId;
    }
  }

  if (!messageId) {
    const streamingPeer = state.turns.find(
      (turn) =>
        turn.role === "assistant" &&
        turn.streaming &&
        (turn.id === id ||
          (turn.id === state.activeTurnId &&
            sameSpeaker(turn.name, senderName)) ||
          sameSpeaker(turn.name, senderName)),
    );
    if (streamingPeer) {
      id = streamingPeer.id;
    }
  }
  const existing = state.turns.find((turn) => turn.id === id);
  if (existing) {
    const sessionId = String(
      (event as { sessionId?: string }).sessionId ?? "",
    ).trim();
    if (sessionId && !existing.sourceMessage?.sessionId) {
      const nextTurns = updateTurnById(state.turns, id, (turn) => ({
        ...turn,
        sourceMessage: { ...(turn.sourceMessage ?? {}), sessionId },
      }));
      return [{ ...state, turns: nextTurns }, id];
    }
    return [state, id];
  }
  const name = resolveActorName(event) || ASSISTANT_NAME;
  const sessionId = String(
    (event as { sessionId?: string }).sessionId ?? "",
  ).trim();
  return [
    {
      ...state,
      activeActorId: resolvedActorId,
      turns: appendTurn(state.turns, {
        id,
        role: "assistant",
        name,
        avatarKind: avatarFor(name),
        text: "",
        traceEvents: [],
        streaming: true,
        ...(sessionId ? { sourceMessage: { sessionId } } : {}),
      }),
    },
    id,
  ];
}

function closeStreaming(turns: ChatTurn[]): ChatTurn[] {
  let changed = false;
  const next = turns.map((turn) => {
    if (!turn.streaming) return turn;
    changed = true;
    return { ...turn, streaming: false };
  });
  return changed ? next : turns;
}

function hasVisibleAssistantTurn(turns: ChatTurn[]): boolean {
  return turns.some(
    (turn) =>
      turn.role === "assistant" &&
      (Boolean(turn.text.trim()) ||
        Boolean(turn.error?.trim()) ||
        turn.traceEvents.length > 0 ||
        turn.streaming),
  );
}

function pruneOrphanBrandShells(turns: ChatTurn[]): ChatTurn[] {
  const hasNamedContentTurn = turns.some(
    (turn) =>
      turn.role === "assistant" &&
      !isAgentDeskBrandName(turn.name) &&
      (Boolean(turn.text.trim()) || Boolean(turn.error?.trim())),
  );
  if (!hasNamedContentTurn) return turns;
  const next = turns.filter((turn) => {
    if (turn.role !== "assistant") return true;
    if (!isAgentDeskBrandName(turn.name)) return true;
    if (turn.streaming || turn.text.trim() || turn.error?.trim()) return true;
    // Empty default-brand shell while a named agent already has reply text.
    return false;
  });
  return next.length === turns.length ? turns : next;
}

function appendEmptyAssistantPlaceholder(state: ChatStreamState): ChatStreamState {
  if (hasVisibleAssistantTurn(state.turns)) return state;
  const lastAssistant = [...state.turns]
    .reverse()
    .find((turn) => turn.role === "assistant");
  const turnId = lastAssistant?.id;
  const withTurn =
    turnId !== undefined
      ? state
      : ensureAssistantTurn(state, { type: "done", actor_id: "assistant" })[0];
  const fallbackTurnId =
    turnId ??
    [...withTurn.turns]
      .reverse()
      .find((turn) => turn.role === "assistant")?.id;
  if (!fallbackTurnId) return withTurn;
  const nextTurns = updateTurnById(withTurn.turns, fallbackTurnId, (turn) => ({
    ...turn,
    text: turn.text.trim() ? turn.text : EMPTY_REPLY_PLACEHOLDER,
    error: turn.error || EMPTY_REPLY_PLACEHOLDER,
    streaming: false,
  }));
  if (nextTurns === withTurn.turns) return withTurn;
  return { ...withTurn, turns: nextTurns };
}

function looseAssistantText(event: ChatStreamEvent): string {
  const direct = event.delta ?? event.content ?? event.text ?? event.message;
  if (typeof direct === "string") return direct;
  if (typeof direct === "number") return String(direct);
  return "";
}

function mergeText(base: string, chunk: string): string {
  if (!chunk) return base;
  if (!base) return chunk;
  if (chunk.startsWith(base)) return chunk;
  if (base.endsWith(chunk)) return base;
  return `${base}${chunk}`;
}

export function createChatStreamState(): ChatStreamState {
  return {
    turns: [],
    streamActive: false,
  };
}

export function reduceChatStreamEvent(
  state: ChatStreamState,
  event: ChatStreamEvent,
): ChatStreamState {
  const type = String(event.type || "");
  if (!type) return state;

  if (type === "stream_start") {
    let normalizedStart: ChatStreamEvent =
      event.sender && !event.actor_id && !event.source_member && !event.worker
        ? ({ ...event, actor_id: String(event.sender) } as ChatStreamEvent)
        : event;
    const actorId =
      resolveActorId(normalizedStart) || state.activeActorId || "assistant";
    let messageId = String(normalizedStart.message_id ?? "").trim();
    let turns = state.turns;
    if (!messageId) {
      const senderName = resolveActorName(normalizedStart);
      const streamingPeer = turns.find(
        (turn) =>
          turn.role === "assistant" &&
          turn.streaming &&
          sameSpeaker(turn.name, senderName),
      );
      if (streamingPeer) {
        normalizedStart = { ...normalizedStart, message_id: streamingPeer.id };
        messageId = streamingPeer.id;
      } else {
        turns = retireFinalizedLiveTurn(turns, assistantTurnId(actorId));
      }
    }
    const [withTurn, turnId] = ensureAssistantTurn(
      { ...state, turns, streamActive: true },
      normalizedStart,
    );
    const nextTurns = updateTurnById(withTurn.turns, turnId, (turn) =>
      turn.streaming ? turn : { ...turn, streaming: true },
    );
    const nextState =
      nextTurns === withTurn.turns
        ? withTurn
        : { ...withTurn, turns: nextTurns };
    return {
      ...nextState,
      activeTurnId: turnId,
      leaderTurnId: turnId,
    };
  }

  if (type === "worker_start") {
    const actorId = resolveActorId(event);
    const incomingName = resolveActorName(event);
    const messageId = String(event.message_id ?? "").trim();
    let turns = state.turns.map((turn) => {
      // Keep the leader draft streaming while workers run; closing it made the
      // leader bubble vanish during long chat_with_agent waits.
      if (state.leaderTurnId && turn.id === state.leaderTurnId) {
        return turn;
      }
      if (!turn.streaming) return turn;
      // Retire only a prior streaming bubble for the same worker; parallel
      // workers must stay streaming independently.
      if (!sameSpeaker(turn.name, incomingName)) return turn;
      return { ...turn, streaming: false };
    });
    if (messageId) {
      turns = turns.filter(
        (turn) =>
          !(
            turn.role === "assistant" &&
            turn.id.startsWith("live:assistant:") &&
            sameSpeaker(turn.name, incomingName) &&
            turn.id !== messageId
          ),
      );
    }
    const [withTurn, turnId] = ensureAssistantTurn(
      {
        ...state,
        activeActorId: actorId,
        activeTurnId: messageId || undefined,
        turns,
      },
      event,
    );
    const nextTurns = updateTurnById(withTurn.turns, turnId, (turn) => ({
      ...turn,
      name: nameForUpdate(event, turn.name),
      avatarKind: "team",
      streaming: true,
    }));
    let mergedTurns = nextTurns;
    if (state.leaderTurnId) {
      const workerLabel = nameForUpdate(event, resolveActorName(event));
      mergedTurns = updateTurnById(mergedTurns, state.leaderTurnId, (turn) =>
        appendTraceEvent(turn, {
          type: "info",
          label: `${workerLabel} 开始执行`,
          message_id: state.leaderTurnId,
        }),
      );
    }
    const next =
      mergedTurns === withTurn.turns ? withTurn : { ...withTurn, turns: mergedTurns };
    return { ...next, activeTurnId: turnId };
  }

  if (type === "worker_done") {
    const actorId = resolveActorId(event);
    const senderName = resolveActorName(event);
    const messageId = String(event.message_id ?? "").trim();
    const liveId = assistantTurnId(actorId);
    const existing = state.turns.find(
      (turn) =>
        turn.role === "assistant" &&
        (turn.id === messageId ||
          turn.id === liveId ||
          turn.id === state.activeTurnId ||
          sameSpeaker(turn.name, senderName)),
    );
    const turnId = existing?.id ?? liveId;
    const nextTurns = existing
      ? updateTurnById(state.turns, turnId, (turn) =>
          turn.streaming ? { ...turn, streaming: false } : turn,
        )
      : state.turns;
    if (nextTurns === state.turns && state.activeActorId !== actorId) return state;
    return {
      ...state,
      turns: nextTurns,
      activeActorId: state.activeActorId === actorId ? undefined : state.activeActorId,
      activeTurnId: state.leaderTurnId ?? state.activeTurnId,
    };
  }

  if (type === "team_phase") {
    const label = String(event.label ?? event.phase ?? "").trim();
    if (!label || !state.leaderTurnId) return state;
    const infoEvt = {
      type: "info",
      label,
      message_id: state.leaderTurnId,
      sender: event.sender,
    } as ChatStreamEvent;
    return reduceChatStreamEvent(state, infoEvt);
  }

  if (type === "timeline_entry") {
    const entries = reduceTeamTimeline(state.teamTimeline ?? [], event);
    if (entries === state.teamTimeline) return state;
    return { ...state, teamTimeline: entries };
  }

  if (type === "done") {
    const closedTurns = closeStreaming(state.turns);
    const prunedTurns = pruneOrphanBrandShells(closedTurns);
    const nextState =
      !state.streamActive && prunedTurns === state.turns
        ? state
        : {
            ...state,
            streamActive: false,
            turns: prunedTurns,
            activeActorId: undefined,
            activeTurnId: undefined,
            leaderTurnId: undefined,
          };
    return appendEmptyAssistantPlaceholder(nextState);
  }

  if (type === "error") {
    const [withTurn, turnId] = ensureAssistantTurn(state, event);
    const text = String(event.content ?? event.message ?? "").trim();
    const isFatal = event.fatal !== false;
    const nextTurns = updateTurnById(withTurn.turns, turnId, (turn) => {
      const currentText = turn.text.trim();
      const mergedText =
        text && !currentText
          ? text
          : text && currentText && !currentText.includes(text)
            ? `${currentText}\n\n${text}`
            : turn.text;
      if (mergedText === turn.text && !turn.streaming && !isFatal) return turn;
      return {
        ...turn,
        text: mergedText,
        error: isFatal ? text || turn.error : turn.error,
        streaming: false,
      };
    });
    return nextTurns === withTurn.turns ? withTurn : { ...withTurn, turns: nextTurns };
  }

  if (type === "content_reset") {
    const [withTurn, turnId] = ensureAssistantTurn(state, event);
    const nextTurns = updateTurnById(withTurn.turns, turnId, (turn) => {
      if (!turn.text) return turn;
      return { ...turn, text: "", streaming: true };
    });
    return nextTurns === withTurn.turns ? withTurn : { ...withTurn, turns: nextTurns };
  }

  if (type === "text_delta") {
    const [withTurn, turnId] = ensureAssistantTurn(state, event);
    const delta = String(event.delta ?? event.content ?? "");
    if (!delta) return withTurn;
    const nextTurns = updateTurnById(withTurn.turns, turnId, (turn) => ({
      ...turn,
      name: nameForUpdate(event, turn.name),
      text: mergeText(turn.text, delta),
      streaming: true,
    }));
    return nextTurns === withTurn.turns ? withTurn : { ...withTurn, turns: nextTurns };
  }

  if (type === "message") {
    const [withTurn, turnId] = ensureAssistantTurn(state, event);
    const content = String(event.content ?? "").trim();
    if (!content) return withTurn;
    const nextTurns = updateTurnById(withTurn.turns, turnId, (turn) => {
      const cur = turn.text.trim();
      // Replace-first: the final `message` is the authoritative content for the
      // turn, so we never concatenate `cur + content` -- that double-prints when
      // the final text only differs from the streamed deltas by formatting.
      // Phase boundaries (auto-continue) are handled by `content_reset`, which
      // clears the turn text first, so replacement is always correct here. The
      // only time we keep `cur` is when it is already a superset of `content`
      // (streamed deltas richer than a truncated final message).
      const merged = cur && cur.startsWith(content) ? cur : content;
      if (merged === turn.text && !turn.streaming) return turn;
      return {
        ...turn,
        name: nameForUpdate(event, turn.name),
        text: merged,
        streaming: false,
      };
    });
    return nextTurns === withTurn.turns ? withTurn : { ...withTurn, turns: nextTurns };
  }

  if (TRACE_STEPS.has(type)) {
    const [withTurn, turnId] = ensureAssistantTurn(state, event);
    const traceEvent = { ...event } as StreamEvent;
    const closeReply = type === "reply_end";
    let nextTurns = updateTurnById(withTurn.turns, turnId, (turn) => {
      const withTrace = appendTraceEvent(
        {
          ...turn,
          name: nameForUpdate(event, turn.name),
        },
        traceEvent,
      );
      return closeReply && withTrace.streaming
        ? { ...withTrace, streaming: false }
        : withTrace;
    });
    if (
      state.leaderTurnId &&
      turnId !== state.leaderTurnId &&
      !isDelegationTraceEvent(event)
    ) {
      const workerTurn = withTurn.turns.find((turn) => turn.id === turnId);
      const workerLabel = nameForUpdate(
        event,
        workerTurn?.name ?? resolveActorName(event),
      );
      nextTurns = updateTurnById(nextTurns, state.leaderTurnId, (turn) =>
        appendTraceEvent(
          turn,
          fanInWorkerTraceForLeader(event, state.leaderTurnId!, workerLabel),
        ),
      );
    }
    return nextTurns === withTurn.turns ? withTurn : { ...withTurn, turns: nextTurns };
  }

  const looseText = looseAssistantText(event).trim();
  if (looseText) {
    const [withTurn, turnId] = ensureAssistantTurn(state, event);
    const nextTurns = updateTurnById(withTurn.turns, turnId, (turn) => ({
      ...turn,
      name: nameForUpdate(event, turn.name),
      text: mergeText(turn.text, looseText),
      streaming: true,
    }));
    return nextTurns === withTurn.turns ? withTurn : { ...withTurn, turns: nextTurns };
  }

  return state;
}

function messagesToTurns(messages: TaskMessage[], events: TaskEvent[]): ChatTurn[] {
  const assistantIndexById = new Map<string, number>();
  const turns = messages
    .map((msg, idx): ChatTurn | null => {
      const role = String(msg.role || "");
      if (role !== "user" && role !== "assistant") return null;
      const text = messageText(msg);
      const traceEvents = Array.isArray(msg.traceEvents) ? (msg.traceEvents as StreamEvent[]) : [];
      const streaming = Boolean(msg.streaming);
      const senderName = String(msg.sender || ASSISTANT_NAME);
      // Each persisted assistant message keeps its server id, including while
      // still streaming, so reconnect/hydration attach to the same bubble the
      // live stream writes into (keyed by ``message_id`` on ``stream_start``).
      const id = String(msg.id ?? `msg:${role}:${idx}`);
      if (role === "assistant") assistantIndexById.set(String(msg.id ?? id), idx);
      return {
        id,
        role: role as ChatTurnRole,
        name: role === "assistant" ? senderName : "You",
        avatarKind: role === "assistant" ? avatarFor(senderName) : "user",
        text,
        traceEvents,
        streaming,
        sourceMessage: msg,
      };
    })
    .filter((item): item is ChatTurn => Boolean(item));

  if (!events.length) return turns;
  const grouped = new Map<number, StreamEvent[]>();
  for (const evt of events) {
    const normalized = normalizeStreamEvent(evt as StreamEvent);
    if (!normalized || !TRACE_STEPS.has(normalized.type)) continue;
    const messageId = String((evt as Record<string, unknown>).message_id ?? "");
    if (!messageId) continue;
    const idx = assistantIndexById.get(messageId);
    if (idx === undefined) continue;
    const list = grouped.get(idx) ?? [];
    list.push(normalized as StreamEvent);
    grouped.set(idx, list);
  }

  if (!grouped.size) return turns;
  let changed = false;
  const next = turns.map((turn, idx) => {
    const appended = grouped.get(idx);
    if (!appended || turn.role !== "assistant") return turn;
    const seen = new Set(
      turn.traceEvents.map((evt) =>
        `${String(evt.type || "")}:${String(evt.tool_call_id || "")}:${String(evt.seq ?? "")}`,
      ),
    );
    const merged = [...turn.traceEvents];
    let added = false;
    for (const evt of appended) {
      const key = `${String(evt.type || "")}:${String(evt.tool_call_id || "")}:${String(evt.seq ?? "")}`;
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(evt);
      added = true;
    }
    if (!added) return turn;
    changed = true;
    return { ...turn, traceEvents: merged };
  });
  return changed ? next : turns;
}

function turnsContentEqual(a: ChatTurn[], b: ChatTurn[]): boolean {
  if (a === b) return true;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    const x = a[i];
    const y = b[i];
    if (
      x.id !== y.id ||
      x.role !== y.role ||
      x.name !== y.name ||
      x.text !== y.text ||
      x.streaming !== y.streaming ||
      x.error !== y.error ||
      x.traceEvents.length !== y.traceEvents.length
    ) {
      return false;
    }
  }
  return true;
}

function sameSpeaker(a: string, b: string): boolean {
  const an = a.trim();
  const bn = b.trim();
  if (an === bn) return true;
  return isAgentDeskBrandName(an) && isAgentDeskBrandName(bn);
}

/** True when one text is a prefix of the other (same evolving stream) or empty. */
function textsOverlap(a: string, b: string): boolean {
  const an = a.trim();
  const bn = b.trim();
  if (!an || !bn) return true;
  if (an === bn || an.startsWith(bn) || bn.startsWith(an)) return true;
  const sharedPrefix = (() => {
    const limit = Math.min(an.length, bn.length);
    let index = 0;
    while (index < limit && an[index] === bn[index]) index += 1;
    return index;
  })();
  return sharedPrefix >= 12;
}

/**
 * Text for a STILL-STREAMING turn. Prefer whichever side is the longer prefix
 * chain; when texts diverge without overlap, keep the live SSE draft unless the
 * server snapshot is substantially ahead (auto-continue phase 2 backfill).
 */
function pickStreamingText(persisted: string, live: string): string {
  const p = persisted.trim();
  const l = live.trim();
  if (!l) return persisted;
  if (!p) return live;
  if (l === p) return live;
  if (l.startsWith(p)) return live;
  if (p.startsWith(l)) return persisted;
  if (p.length > l.length + 20) return persisted;
  return live;
}

/** Text for a finalized turn: keep the richer/longer without shrinking. */
function pickRicherText(persisted: string, live: string): string {
  const p = persisted.trim();
  const l = live.trim();
  if (!l) return persisted;
  if (!p) return live;
  if (l === p) return persisted.length >= live.length ? persisted : live;
  if (l.startsWith(p)) return live;
  if (p.startsWith(l)) return persisted;
  return live.length > persisted.length ? live : persisted;
}

/**
 * Monotonic trace union: never replace a longer accumulated trace with a shorter
 * one. Both the live and persisted traces are append-only prefixes of the same
 * stream, so the longer list is the superset — keeping it makes the live
 * trace/counters non-decreasing across reconnect/hydration merges.
 */
function pickRicherTrace(base: StreamEvent[], incoming: StreamEvent[]): StreamEvent[] {
  return incoming.length > base.length ? incoming : base;
}

/** Prefer a concrete speaker name over the generic brand fallback. */
function preferAttributedName(a: string, b: string): string {
  const an = a.trim();
  if (an && !isAgentDeskBrandName(an)) return a;
  const bn = b.trim();
  if (bn && !isAgentDeskBrandName(bn)) return b;
  return an || bn || ASSISTANT_NAME;
}

function mergeAssistantTurns(
  base: ChatTurn,
  live: ChatTurn,
  stillActive: boolean,
): ChatTurn {
  const text = live.streaming
    ? pickStreamingText(base.text, live.text)
    : pickRicherText(base.text, live.text);
  const traceEvents = pickRicherTrace(base.traceEvents, live.traceEvents);
  // While the turn is still live keep streaming if either side believes so; once
  // the server has finalized (not active) only stay streaming if both agree.
  const streaming = stillActive
    ? live.streaming || base.streaming
    : live.streaming && base.streaming;
  const mergedId =
    !base.id.startsWith("live:assistant:") ? base.id
    : !live.id.startsWith("live:assistant:") ? live.id
    : base.id;
  return {
    ...base,
    id: stillActive && live.streaming ? mergedId : base.id.startsWith("live:assistant:") ? live.id : base.id,
    name: preferAttributedName(live.name, base.name),
    text,
    traceEvents,
    streaming,
    error: live.error || base.error,
    sourceMessage: base.sourceMessage ?? live.sourceMessage,
  };
}

function finalizeIdleTurns(turns: ChatTurn[], runActive: boolean): ChatTurn[] {
  if (runActive) return turns;
  let changed = false;
  const next = turns.map((turn) => {
    if (!turn.streaming) return turn;
    changed = true;
    return { ...turn, streaming: false };
  });
  return changed ? next : turns;
}

export function hydrateChatStreamState(
  state: ChatStreamState,
  params: {
    messages: TaskMessage[];
    events: TaskEvent[];
    runActive: boolean;
  },
): ChatStreamState {
  const persisted = finalizeIdleTurns(
    messagesToTurns(params.messages, params.events),
    params.runActive,
  );
  if (persisted.length === 0 && state.turns.length > 0) {
    return state;
  }

  const stillActive = params.runActive || state.streamActive;
  const liveAssistantTurns = state.turns.filter(
    (turn) =>
      turn.role === "assistant" &&
      (turn.streaming || turn.text.trim() !== "" || turn.traceEvents.length > 0),
  );

  if (liveAssistantTurns.length === 0) {
    if (turnsContentEqual(state.turns, persisted)) return state;
    const streamingTurn = persisted.find(
      (turn) => turn.role === "assistant" && turn.streaming,
    );
    const livePrefix = "live:assistant:";
    const activeActorId =
      streamingTurn && streamingTurn.id.startsWith(livePrefix)
        ? streamingTurn.id.slice(livePrefix.length)
        : state.activeActorId;
    return {
      ...state,
      turns: persisted,
      activeActorId,
      streamActive: params.runActive && (state.streamActive || Boolean(streamingTurn)),
    };
  }

  // Active run or locally cached turns (e.g. user switched away mid-stream): fold
  // each locally-accumulated assistant turn into persisted history monotonically.
  const merged = [...persisted];
  const usedIdx = new Set<number>();

  const findUnused = (predicate: (turn: ChatTurn, i: number) => boolean) =>
    merged.findIndex((turn, i) => !usedIdx.has(i) && predicate(turn, i));
  const lastUnusedAssistant = () => {
    for (let i = merged.length - 1; i >= 0; i -= 1) {
      if (!usedIdx.has(i) && merged[i].role === "assistant") return i;
    }
    return -1;
  };

  for (const live of liveAssistantTurns) {
    let idx = findUnused((turn) => turn.id === live.id);
    if (idx < 0) {
      idx = findUnused(
        (turn) =>
          turn.role === "assistant" &&
          sameSpeaker(turn.name, live.name) &&
          textsOverlap(turn.text, live.text),
      );
    }
    if (idx < 0) {
      idx = findUnused(
        (turn) =>
          turn.role === "assistant" &&
          sameSpeaker(turn.name, live.name) &&
          live.id.startsWith("live:assistant:") &&
          !turn.id.startsWith("live:assistant:") &&
          (turn.streaming || !turn.text.trim()),
      );
    }
    const liveHasContent = live.text.trim() !== "" || live.traceEvents.length > 0;
    if (idx < 0 && live.streaming && liveHasContent) {
      idx = lastUnusedAssistant();
    }
    if (idx < 0) {
      if (
        isAgentDeskBrandName(live.name) &&
        !live.text.trim() &&
        !live.error?.trim() &&
        !live.streaming &&
        merged.some(
          (turn) =>
            turn.role === "assistant" &&
            !isAgentDeskBrandName(turn.name) &&
            (Boolean(turn.text.trim()) || Boolean(turn.error?.trim())),
        )
      ) {
        continue;
      }
      merged.push(live);
      usedIdx.add(merged.length - 1);
      continue;
    }
    usedIdx.add(idx);
    merged[idx] = mergeAssistantTurns(merged[idx], live, stillActive);
  }

  let activeActorId = state.activeActorId;
  const streamingTurn = merged.find(
    (turn) => turn.role === "assistant" && turn.streaming,
  );
  const livePrefix = "live:assistant:";
  if (streamingTurn && streamingTurn.id.startsWith(livePrefix)) {
    activeActorId = streamingTurn.id.slice(livePrefix.length);
  }

  if (turnsContentEqual(state.turns, merged) && activeActorId === state.activeActorId) {
    return state;
  }
  return { ...state, turns: merged, activeActorId };
}

export function normalizeStreamEvent(raw: StreamEvent): ChatStreamEvent | null {
  const type = String(raw.type || "");
  if (!type) return null;
  if (type === "trace") {
    const step = String(raw.step || "");
    if (!step) return null;
    return { ...raw, type: step };
  }
  if (type === "team_phase") {
    return raw as ChatStreamEvent;
  }
  if (type === "approval_required" || type === "heartbeat" || type === "wizard_update") {
    return null;
  }
  return raw as ChatStreamEvent;
}
