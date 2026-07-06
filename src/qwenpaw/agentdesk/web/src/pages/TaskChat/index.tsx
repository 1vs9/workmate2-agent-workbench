import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode, type PointerEvent } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { chatApprove, chatStream, chatStreamReconnect, type StreamEvent } from "../../api/chatStream";
import { tasksApi, type Task, type TaskEvent, type TaskMessage } from "../../api/tasks";
import ArtifactContextMenu from "../../components/chat/ArtifactContextMenu";
import InteractiveAssistantMarkdown from "../../components/chat/InteractiveAssistantMarkdown";
import ProcessObservability from "../../components/chat/ProcessObservability";
import TurnArtifacts from "../../components/chat/TurnArtifacts";
import AgentAvatar from "../../components/agents/AgentAvatar";
import { AgentDeskAvatar } from "../../components/branding/AgentDeskIcon";
import ComposerToolbar from "../../components/composer/ComposerToolbar";
import TeamChatTabbedView, {
  isTeamMemberSessionActive,
} from "../../components/team/TeamChatTabbedView";
import TeamSessionTabs, {
  type TeamActiveSession,
} from "../../components/team/TeamSessionTabs";
import { partitionTeamConversation } from "../../utils/partitionTeamConversation";
import ArtifactPanel from "../../components/task/ArtifactPanel";
import { useArtifactInteractions } from "../../hooks/useArtifactInteractions";
import { useAppStore } from "../../store/appStore";
import { useComposerStore } from "../../store/composerStore";
import { useReferenceDataStore } from "../../store/referenceDataStore";
import { useSkillsStore } from "../../store/skillsStore";
import { buildChatPayload } from "../../utils/buildChatPayload";
import { SKILL_CREATOR_SKILL } from "../../utils/skillCreate";
import {
  getComposerTaskCache,
  saveComposerTaskCache,
} from "../../utils/composerTaskCache";
import {
  hydrateComposerFromTask,
  readComposerSnapshot,
  resolveTaskAssignee,
} from "../../utils/hydrateComposerFromTask";
import type { SkillTaskComposerState } from "../../utils/openSkillTaskFlow";
import {
  AGENTDESK_BRAND_NAME,
  isAgentDeskBrandName,
  type Assignee,
} from "../../types/assignee";
import {
  resolveTeamRepresentativeProfile,
  resolveTeamSpeakerProfile,
  teamLeaderDisplayName,
  type TeamSpeakerProfile,
} from "../../utils/resolveTeamSpeakerProfile";
import {
  createChatStreamState,
  hydrateChatStreamState,
  normalizeStreamEvent,
  reduceChatStreamEvent,
} from "../../utils/chatStreamReducer";
import { isFatalStreamError } from "../../utils/streamErrorHandling";
import { isModelConfigurationError } from "../../utils/modelConfigurationError";
import { isAgentRunning, isTaskRunActive } from "../../utils/taskRunStatus";
import {
  getCachedChatState,
  setCachedChatState,
} from "../../utils/taskChatStateCache";
import type { ArtifactItem } from "../../utils/artifacts";
import { mergeArtifactLists, skillProductArtifact } from "../../utils/artifacts";

interface LocationState extends Partial<SkillTaskComposerState> {
  initialMessage?: string;
}

const STREAM_IDLE_TIMEOUT_MS = 300_000;
/** Long team runs (multi-step tools) may exceed 5 min between visible tokens. */
const STREAM_TEAM_IDLE_TIMEOUT_MS = 600_000;
const RUN_STATUS_POLL_MS = 2_000;

function hasLocalStreamingTurns(taskId: string): boolean {
  const cached = getCachedChatState(taskId);
  return Boolean(
    cached?.turns.some(
      (turn) =>
        turn.role === "assistant" &&
        (turn.streaming ||
          (!turn.text.trim() && turn.traceEvents.length > 0)),
    ),
  );
}

function hydrateTaskSnapshot(task: Task | null | undefined): ReturnType<typeof createChatStreamState> | undefined {
  const messages = task?.messages ?? [];
  if (!messages.length) return undefined;
  return hydrateChatStreamState(createChatStreamState(), {
    messages,
    events: [],
    runActive: isTaskRunActive(task),
  });
}

function taskMessagesSnapshotEqual(
  left: TaskMessage[] | undefined,
  right: TaskMessage[] | undefined,
): boolean {
  const a = left ?? [];
  const b = right ?? [];
  if (a.length !== b.length) return false;
  return a.every((msg, idx) => {
    const other = b[idx];
    if (!other) return false;
    return (
      msg.id === other.id &&
      msg.role === other.role &&
      String(msg.content ?? "") === String(other.content ?? "") &&
      Boolean(msg.streaming) === Boolean(other.streaming)
    );
  });
}

const SCROLLBAR_ARROW_SIZE = 18;
const SCROLLBAR_TRACK_INSET = 6;
const SCROLLBAR_MIN_THUMB = 32;
const SCROLLBAR_IDLE_MS = 1000;
const SCROLL_STICK_THRESHOLD = 96;

function getScrollTrackHeight(clientHeight: number): number {
  return Math.max(
    0,
    clientHeight - SCROLLBAR_ARROW_SIZE * 2 - SCROLLBAR_TRACK_INSET * 2,
  );
}

function isNearScrollBottom(el: HTMLDivElement): boolean {
  return (
    el.scrollHeight - el.scrollTop - el.clientHeight <= SCROLL_STICK_THRESHOLD
  );
}

function scrollFromThumbTop(
  el: HTMLDivElement,
  thumbTop: number,
  thumbHeight: number,
): void {
  const trackHeight = getScrollTrackHeight(el.clientHeight);
  const maxThumbTravel = Math.max(0, trackHeight - thumbHeight);
  const ratio = maxThumbTravel > 0 ? thumbTop / maxThumbTravel : 0;
  const maxScroll = el.scrollHeight - el.clientHeight;
  el.scrollTop = ratio * maxScroll;
}

function formatStreamError(raw: string): string {
  const text = raw.trim() || "对话失败，请稍后重试。";
  const lowered = text.toLowerCase();
  if (
    lowered.includes("authentication") ||
    lowered.includes("unauthorized") ||
    text.includes("未配置可用模型") ||
    text.includes("无法激活模型") ||
    text.includes("模型仍未就绪") ||
    lowered.includes("api key")
  ) {
    return "模型 API 认证失败或未配置。请前往「设置」填写 DeepSeek（或其他提供商）的 API Key，或在输入框工具栏切换已配置的模型。";
  }
  if (lowered.includes("no active model")) {
    return "未配置可用模型。请前往「设置」选择并激活一个模型。";
  }
  return text;
}

const ASSISTANT_DISPLAY_NAME = AGENTDESK_BRAND_NAME;

const ASSISTANT_BUBBLE_CLASSES =
  "rounded-2xl border border-gray-200/80 bg-white px-4 py-2.5 text-[14px] leading-relaxed text-gray-800 shadow-sm";

function AssistantTurnRow({
  breathing = false,
  sender,
  speakerAvatar,
  traces = [],
  isStreaming = false,
  bubbleClassName,
  children,
}: {
  breathing?: boolean;
  sender?: string;
  speakerAvatar?: TeamSpeakerProfile;
  traces?: StreamEvent[];
  isStreaming?: boolean;
  bubbleClassName?: string;
  children?: ReactNode;
}) {
  const hasTraces = traces.length > 0;
  const hasBubble = children != null && children !== false;
  const displayName = sender?.trim() || ASSISTANT_DISPLAY_NAME;

  if (!hasTraces && !hasBubble) return null;

  return (
    <div className="flex justify-start gap-2.5">
      {speakerAvatar ? (
        <AgentAvatar
          name={speakerAvatar.name}
          avatar={speakerAvatar.avatar}
          description={speakerAvatar.description}
          portraitName={speakerAvatar.portraitName}
          portraitDescription={speakerAvatar.portraitDescription}
          role={speakerAvatar.role}
          size="sm"
          className={`mt-0.5 shrink-0${breathing ? " wm-avatar-breathe" : ""}`}
        />
      ) : (
        <AgentDeskAvatar breathing={breathing} className="mt-0.5 shrink-0" />
      )}
      <div className="min-w-0 max-w-[85%] flex-1 space-y-2">
        <div className="text-[12px] font-medium text-slate-600">{displayName}</div>
        {hasTraces ? (
          <ProcessObservability
            events={traces}
            isStreaming={isStreaming}
            className="mb-0"
          />
        ) : null}
        {hasBubble ? (
          <div className={[ASSISTANT_BUBBLE_CLASSES, bubbleClassName].filter(Boolean).join(" ")}>
            {children}
          </div>
        ) : null}
      </div>
    </div>
  );
}

export default function TaskChatPage() {
  const { taskId = "" } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const updateTask = useAppStore((s) => s.updateTask);
  const setActiveTaskId = useAppStore((s) => s.setActiveTaskId);
  const activeTaskId = useAppStore((s) => s.activeTaskId);
  const taskSnapshots = useAppStore((s) => s.tasks);
  const updateTaskRef = useRef(updateTask);
  const setActiveTaskIdRef = useRef(setActiveTaskId);
  const activeTaskIdRef = useRef(activeTaskId);
  const taskIdRef = useRef(taskId);
  updateTaskRef.current = updateTask;
  setActiveTaskIdRef.current = setActiveTaskId;
  activeTaskIdRef.current = activeTaskId;
  taskIdRef.current = taskId;
  const assignee = useComposerStore((s) => s.assignee);
  const skillNames = useComposerStore((s) => s.skillNames);
  const planMode = useComposerStore((s) => s.planMode);
  const sidebarTaskSnapshot = useMemo(
    () => taskSnapshots.find((item) => item.id === taskId) ?? null,
    [taskSnapshots, taskId],
  );
  const initialChatSnapshot = useMemo(
    () =>
      getCachedChatState(taskId) ??
      hydrateTaskSnapshot(sidebarTaskSnapshot) ??
      createChatStreamState(),
    [taskId, sidebarTaskSnapshot],
  );

  const [task, setTask] = useState<Task | null>(() => sidebarTaskSnapshot);
  // Teams / employees come from the shared cache (loaded once, refreshed on
  // mutation) so switching tasks no longer re-fetches them on every change.
  const teams = useReferenceDataStore((s) => s.teams);
  const employees = useReferenceDataStore((s) => s.employees);
  const [chatState, setChatState] = useState(() => initialChatSnapshot);
  const [input, setInput] = useState("");
  const [streamConnected, setStreamConnected] = useState(false);
  const [reconnectInFlight, setReconnectInFlight] = useState(false);
  const [taskLoading, setTaskLoading] = useState(
    () => initialChatSnapshot.turns.length === 0,
  );
  const [pendingApproval, setPendingApproval] = useState(false);
  const [skillTag, setSkillTag] = useState<string | null>(null);
  const artifact = useArtifactInteractions(taskId);
  const abortRef = useRef<AbortController | null>(null);
  const streamGenRef = useRef(0);
  const streamOwnerTaskIdRef = useRef<string | null>(null);
  const chatStateRef = useRef(chatState);
  chatStateRef.current = chatState;
  const reconnectInFlightRef = useRef(false);
  const runStatusPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recoveryAttemptedRef = useRef(false);
  const stoppedByUserRef = useRef(false);
  const initialSentRef = useRef(false);
  const composerDraftAppliedRef = useRef<string | null>(null);
  const composerInputRef = useRef<HTMLTextAreaElement>(null);
  const focusComposer = useCallback(() => {
    window.requestAnimationFrame(() => {
      composerInputRef.current?.focus();
    });
  }, []);
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollbarHideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stickToBottomRef = useRef(true);
  const isDraggingThumbRef = useRef(false);
  const dragSnapshotRef = useRef<{
    startY: number;
    startThumbTop: number;
    thumbHeight: number;
    trackHeight: number;
  } | null>(null);
  const reconnectStreamRef = useRef(false);
  const streamConnectedRef = useRef(false);
  const hydrationRequestRef = useRef(0);
  const prevComposerTaskIdRef = useRef<string | null>(null);
  // True once a `done` SSE event has hydrated from its authoritative
  // `done.messages` snapshot, so the stream finalizer can skip a redundant
  // second server hydration (which previously caused duplicated turns).
  const doneHadMessagesRef = useRef(false);
  const [scrollMetrics, setScrollMetrics] = useState({
    hasOverflow: false,
    thumbTop: 0,
    thumbHeight: 0,
  });
  const [scrollbarVisible, setScrollbarVisible] = useState(false);
  const [thumbDragging, setThumbDragging] = useState(false);

  const activeAssignee = useMemo(
    () => resolveTaskAssignee(task, teams, assignee),
    [task, teams, assignee],
  );

  const activeTeam = useMemo(() => {
    if (activeAssignee.type !== "team") return null;
    const teamId = activeAssignee.teamId?.trim();
    const name = activeAssignee.name?.trim();
    if (teamId) {
      const byId = teams.find((item) => item.id === teamId);
      if (byId) return byId;
    }
    if (name) {
      return teams.find((item) => item.name === name) ?? null;
    }
    return null;
  }, [activeAssignee, teams]);

  const teamChatMode = activeAssignee.type === "team";
  const [teamActiveSession, setTeamActiveSession] =
    useState<TeamActiveSession>("leader");
  const teamMemberSessionActive =
    teamChatMode && isTeamMemberSessionActive(teamActiveSession);

  const teamPartition = useMemo(
    () =>
      teamChatMode
        ? partitionTeamConversation(chatState.turns, activeTeam, employees)
        : null,
    [teamChatMode, chatState.turns, activeTeam, employees],
  );

  useEffect(() => {
    setTeamActiveSession("leader");
  }, [taskId, teamChatMode]);

  const resolveSpeakerAvatar = useCallback(
    (sender?: string) => {
      if (!teamChatMode) return undefined;
      const label = sender?.trim();
      if (!label || label === "系统" || isAgentDeskBrandName(label)) {
        return undefined;
      }
      return resolveTeamSpeakerProfile(label, activeTeam, employees);
    },
    [teamChatMode, activeTeam, employees],
  );

  const applyStreamUpdate = useCallback((evt: StreamEvent) => {
    const normalized = normalizeStreamEvent(evt);
    if (!normalized) return;
    setChatState((prev) => reduceChatStreamEvent(prev, normalized));
  }, []);

  const updateScrollMetrics = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;

    const { scrollHeight, clientHeight, scrollTop } = el;
    const hasOverflow = scrollHeight > clientHeight + 1;
    if (!hasOverflow) {
      setScrollMetrics({ hasOverflow: false, thumbTop: 0, thumbHeight: 0 });
      return;
    }

    const trackHeight = Math.max(
      0,
      clientHeight - SCROLLBAR_ARROW_SIZE * 2 - SCROLLBAR_TRACK_INSET * 2,
    );
    const thumbHeight = Math.max(
      SCROLLBAR_MIN_THUMB,
      Math.round((clientHeight / scrollHeight) * trackHeight),
    );
    const maxScroll = scrollHeight - clientHeight;
    const scrollRatio = maxScroll > 0 ? scrollTop / maxScroll : 0;
    const thumbTop = scrollRatio * Math.max(0, trackHeight - thumbHeight);

    setScrollMetrics({ hasOverflow, thumbTop, thumbHeight });
  }, []);

  const revealScrollbar = useCallback(() => {
    setScrollbarVisible(true);
    if (scrollbarHideTimerRef.current) {
      clearTimeout(scrollbarHideTimerRef.current);
    }
    if (isDraggingThumbRef.current) return;
    scrollbarHideTimerRef.current = setTimeout(() => {
      if (!isDraggingThumbRef.current) {
        setScrollbarVisible(false);
      }
    }, SCROLLBAR_IDLE_MS);
  }, []);

  const handleMessagesScroll = useCallback(() => {
    const el = scrollRef.current;
    if (el && !isDraggingThumbRef.current) {
      stickToBottomRef.current = isNearScrollBottom(el);
    }
    updateScrollMetrics();
    revealScrollbar();
  }, [updateScrollMetrics, revealScrollbar]);

  const handleThumbPointerDown = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      const el = scrollRef.current;
      if (!el) return;

      isDraggingThumbRef.current = true;
      setThumbDragging(true);
      stickToBottomRef.current = false;
      dragSnapshotRef.current = {
        startY: e.clientY,
        startThumbTop: scrollMetrics.thumbTop,
        thumbHeight: scrollMetrics.thumbHeight,
        trackHeight: getScrollTrackHeight(el.clientHeight),
      };
      revealScrollbar();
      e.currentTarget.setPointerCapture(e.pointerId);
    },
    [scrollMetrics.thumbTop, scrollMetrics.thumbHeight, revealScrollbar],
  );

  const handleThumbPointerMove = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      if (!isDraggingThumbRef.current || !dragSnapshotRef.current) return;
      const el = scrollRef.current;
      if (!el) return;

      const snap = dragSnapshotRef.current;
      const deltaY = e.clientY - snap.startY;
      const maxThumbTravel = Math.max(0, snap.trackHeight - snap.thumbHeight);
      const nextThumbTop = Math.min(
        maxThumbTravel,
        Math.max(0, snap.startThumbTop + deltaY),
      );
      scrollFromThumbTop(el, nextThumbTop, snap.thumbHeight);
      updateScrollMetrics();
      revealScrollbar();
    },
    [updateScrollMetrics, revealScrollbar],
  );

  const finishThumbDrag = useCallback(
    (target: HTMLDivElement, pointerId: number) => {
      if (!isDraggingThumbRef.current) return;
      isDraggingThumbRef.current = false;
      setThumbDragging(false);
      dragSnapshotRef.current = null;
      const el = scrollRef.current;
      if (el) {
        stickToBottomRef.current = isNearScrollBottom(el);
      }
      try {
        target.releasePointerCapture(pointerId);
      } catch {
        /* ignore */
      }
      revealScrollbar();
    },
    [revealScrollbar],
  );

  const handleThumbPointerUp = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      finishThumbDrag(e.currentTarget, e.pointerId);
    },
    [finishThumbDrag],
  );

  const handleThumbPointerCancel = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      finishThumbDrag(e.currentTarget, e.pointerId);
    },
    [finishThumbDrag],
  );

  const handleTrackPointerDown = useCallback(
    (e: PointerEvent<HTMLDivElement>) => {
      if ((e.target as HTMLElement).classList.contains("wm-chat-scrollbar__thumb")) {
        return;
      }
      const el = scrollRef.current;
      if (!el) return;

      e.preventDefault();
      stickToBottomRef.current = false;
      const track = e.currentTarget;
      const rect = track.getBoundingClientRect();
      const clickY = e.clientY - rect.top;
      const trackHeight = getScrollTrackHeight(el.clientHeight);
      const thumbHeight = Math.max(
        SCROLLBAR_MIN_THUMB,
        Math.round((el.clientHeight / el.scrollHeight) * trackHeight),
      );
      const maxThumbTravel = Math.max(0, trackHeight - thumbHeight);
      const thumbTop = Math.min(
        maxThumbTravel,
        Math.max(0, clickY - thumbHeight / 2),
      );
      scrollFromThumbTop(el, thumbTop, thumbHeight);
      updateScrollMetrics();
      revealScrollbar();
    },
    [updateScrollMetrics, revealScrollbar],
  );

  const scrollMessagesBy = useCallback(
    (direction: -1 | 1) => {
      const el = scrollRef.current;
      if (!el) return;
      const step = Math.max(80, Math.round(el.clientHeight * 0.25));
      el.scrollBy({ top: direction * step, behavior: "smooth" });
      revealScrollbar();
    },
    [revealScrollbar],
  );

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  const stopRunStatusPoll = useCallback(() => {
    if (runStatusPollRef.current) {
      clearInterval(runStatusPollRef.current);
      runStatusPollRef.current = null;
    }
  }, []);

  const refreshTaskFromServer = useCallback(async () => {
    const requestTaskId = taskId;
    if (!requestTaskId) return null;
    const [remote, events] = await Promise.all([
      tasksApi.get(requestTaskId),
      tasksApi.getEvents(requestTaskId).catch(() => []),
    ]);

    // appStore is keyed by task id, so updating it is always safe regardless
    // of which task is currently rendered.
    updateTaskRef.current(remote);

    // Stream flags belong to the currently mounted task only. A late response
    // for a task the user already switched away from must not borrow them.
    const isCurrent = taskIdRef.current === requestTaskId;
    const serverRunActive = isTaskRunActive(remote);
    const liveStreamActive =
      isCurrent &&
      (streamConnectedRef.current || reconnectInFlightRef.current);
    const localDraftActive =
      isCurrent && serverRunActive && hasLocalStreamingTurns(requestTaskId);
    // Server ``running`` alone must not keep empty bubbles streaming after
    // refresh; reconnect will flip streamConnected and re-enable live flags.
    const runActive = serverRunActive && (liveStreamActive || localDraftActive);

    // Cross-talk guard: if the user already navigated to another task, only
    // refresh THIS task's cache (so it is correct when revisited) and never
    // touch the live component state, which now renders a different task.
    if (!isCurrent) {
      const base =
        getCachedChatState(requestTaskId) ?? createChatStreamState();
      const next = hydrateChatStreamState(base, {
        messages: remote.messages ?? [],
        events,
        runActive,
      });
      setCachedChatState(requestTaskId, next);
      return remote;
    }

    setTask((prevTask) =>
      prevTask &&
      String(prevTask.runStatus ?? prevTask.run_status) ===
        String(remote.runStatus ?? remote.run_status) &&
      taskMessagesSnapshotEqual(prevTask.messages, remote.messages) &&
      prevTask.title === remote.title
        ? prevTask
        : remote,
    );
    setChatState((prev) => {
      const next = hydrateChatStreamState(prev, {
        messages: remote.messages ?? [],
        events,
        runActive,
      });
      setCachedChatState(requestTaskId, next);
      return next;
    });
    if (activeTaskIdRef.current !== requestTaskId) {
      setActiveTaskIdRef.current(requestTaskId);
    }
    return remote;
  }, [taskId]);

  const refreshTaskFromServerRef = useRef(refreshTaskFromServer);
  refreshTaskFromServerRef.current = refreshTaskFromServer;

  const startRunStatusPoll = useCallback(() => {
    if (!taskId || runStatusPollRef.current) return;
    runStatusPollRef.current = setInterval(() => {
      void refreshTaskFromServer().then((remote) => {
        if (!remote) {
          stopRunStatusPoll();
          return;
        }
        // Keep polling while this tab still owns a live SSE connection even if
        // runStatus briefly flips idle (scheduled-write race) so poll backfill
        // can hydrate text when the stream stalls during long tool calls.
        if (
          !isTaskRunActive(remote) &&
          !streamConnectedRef.current &&
          !reconnectInFlightRef.current &&
          !hasLocalStreamingTurns(taskId)
        ) {
          stopRunStatusPoll();
        }
      }).catch(() => {
        stopRunStatusPoll();
      });
    }, RUN_STATUS_POLL_MS);
  }, [taskId, refreshTaskFromServer, stopRunStatusPoll]);

  const loadTask = refreshTaskFromServer;

  useEffect(() => {
    if (!taskId || !task) return;
    hydrateComposerFromTask(task, teams);
    saveComposerTaskCache(taskId, readComposerSnapshot());
  }, [
    taskId,
    teams,
    task?.employee_name,
    task?.employeeName,
    task?.team_id,
    task?.teamId,
    task?.team_name,
    task?.teamName,
    task?.mode,
    task?.skill_names,
  ]);

  useEffect(() => {
    // Background hydration. taskLoading is owned by the reset effect (it shows
    // a spinner only when there is no cached transcript), so we never force it
    // back on here -- a cache hit renders instantly while this refresh runs.
    const requestId = ++hydrationRequestRef.current;
    void refreshTaskFromServerRef
      .current()
      .catch((err) => {
        window.alert(err instanceof Error ? err.message : "加载任务失败");
      })
      .finally(() => {
        if (hydrationRequestRef.current !== requestId) return;
        setTaskLoading(false);
      });
    void useReferenceDataStore.getState().ensureLoaded();
  }, [taskId]);

  useEffect(() => {
    streamConnectedRef.current = streamConnected;
  }, [streamConnected]);

  useEffect(() => {
    if (isDraggingThumbRef.current || !stickToBottomRef.current) return;
    scrollToBottom();
  }, [chatState.turns, scrollToBottom]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    updateScrollMetrics();

    const observer = new ResizeObserver(() => {
      updateScrollMetrics();
    });
    observer.observe(el);
    const content = el.firstElementChild;
    if (content) observer.observe(content);

    return () => {
      observer.disconnect();
      if (scrollbarHideTimerRef.current) {
        clearTimeout(scrollbarHideTimerRef.current);
      }
    };
  }, [
    updateScrollMetrics,
    chatState.turns,
    streamConnected,
    pendingApproval,
  ]);

  useEffect(() => {
    const prevTaskId = prevComposerTaskIdRef.current;
    if (prevTaskId && prevTaskId !== taskId) {
      saveComposerTaskCache(prevTaskId, readComposerSnapshot());
    }
    prevComposerTaskIdRef.current = taskId || null;

    const cachedComposer = taskId ? getComposerTaskCache(taskId) : undefined;
    if (cachedComposer) {
      useComposerStore.getState().applyComposerSnapshot(cachedComposer);
    } else {
      useComposerStore.getState().resetForNewChat([]);
    }

    initialSentRef.current = false;
    stoppedByUserRef.current = false;
    recoveryAttemptedRef.current = false;
    reconnectInFlightRef.current = false;
    streamGenRef.current += 1;
    streamOwnerTaskIdRef.current = null;
    stopRunStatusPoll();
    abortRef.current?.abort();
    setTask(sidebarTaskSnapshot);
    // Instant switch: restore cached transcript synchronously and only show a
    // loading state when there is nothing cached to render yet.
    const cachedState = getCachedChatState(taskId);
    const sidebarState = cachedState
      ? undefined
      : hydrateTaskSnapshot(sidebarTaskSnapshot);
    const nextState = cachedState ?? sidebarState ?? createChatStreamState();
    if (sidebarState) {
      setCachedChatState(taskId, sidebarState);
    }
    setChatState(nextState);
    setInput("");
    setStreamConnected(false);
    setReconnectInFlight(false);
    setPendingApproval(false);
    artifact.setPanelOpen(false);
    artifact.resetLiveArtifacts();
    setSkillTag(null);
    setTaskLoading(nextState.turns.length === 0);
    composerDraftAppliedRef.current = null;

    return () => {
      if (taskId) {
        setCachedChatState(taskId, chatStateRef.current);
      }
    };
  }, [taskId, stopRunStatusPoll]);

  useEffect(() => () => stopRunStatusPoll(), [stopRunStatusPoll]);

  const handleStreamEvent = useCallback(
    (evt: StreamEvent, teamMode: boolean, ownerTaskId: string) => {
      if (streamOwnerTaskIdRef.current !== ownerTaskId) return;
      const evtTaskId =
        typeof evt.task_id === "string" ? evt.task_id.trim() : "";
      if (evtTaskId && evtTaskId !== ownerTaskId) return;
      if (taskIdRef.current !== ownerTaskId) return;
      const type = String(evt.type || "");
      if (type === "heartbeat") return;
      if (type === "member_stream_end") return;

      if (type === "wizard_update") {
        const wizard = evt.wizard as Record<string, unknown> | undefined;
        if (
          wizard &&
          wizard.status === "skill_done" &&
          wizard.created_skill &&
          typeof wizard.created_skill === "object"
        ) {
          useSkillsStore.getState().bumpSkillsRevision();
          const created = wizard.created_skill as Record<string, unknown>;
          const skillName = String(created.name || "").trim();
          if (skillName) {
            const item = skillProductArtifact(skillName);
            artifact.pushLiveArtifact({
              type: "artifact",
              ...item,
            });
          }
        }
        return;
      }

      if (type === "stream_start") {
        setTask((prev) =>
          prev ? { ...prev, runStatus: "running", run_status: "running" } : prev,
        );
        artifact.resetLiveArtifacts();
      }

      if (type === "artifact") {
        artifact.pushLiveArtifact(evt as Record<string, unknown>);
        return;
      }

      if (type === "trace") {
        applyStreamUpdate(evt);
        return;
      }

      if (type === "approval_required") {
        setPendingApproval(true);
        return;
      }

      if (type === "done") {
        const serverMessages = evt.messages;
        if (Array.isArray(serverMessages)) {
          const liveArtifactItems = artifact.buildLiveTurnArtifacts("");
          let messagesForHydrate = serverMessages as TaskMessage[];
          if (liveArtifactItems.length) {
            messagesForHydrate = serverMessages.map((msg, idx, arr) => {
              if (idx !== arr.length - 1 || msg?.role !== "assistant") return msg;
              return artifact.attachArtifactsToMessage(
                msg as TaskMessage,
                String(msg.content ?? ""),
                liveArtifactItems,
              );
            }) as TaskMessage[];
          }
          // Treat the done payload as the authoritative final snapshot only
          // when it carries a *finalized, non-empty* assistant reply. A stale
          // payload (empty content or still flagged streaming) must still fall
          // back to loadTask() in runStream's finally so the persisted reply
          // hydrates — otherwise the bubble stays blank.
          const hasFinalAssistant = (serverMessages as TaskMessage[]).some(
            (msg) =>
              msg?.role === "assistant" &&
              !msg.streaming &&
              String(msg.content ?? "").trim().length > 0,
          );
          const stillStreaming = (serverMessages as TaskMessage[]).some(
            (msg) => msg?.role === "assistant" && msg.streaming,
          );
          if (hasFinalAssistant && !stillStreaming) {
            doneHadMessagesRef.current = true;
          }
          // The `done` payload may also carry authoritative trace events.
          const serverEvents = (evt as { events?: unknown }).events;
          setChatState((prev) =>
            hydrateChatStreamState(prev, {
              messages: messagesForHydrate,
              events: Array.isArray(serverEvents)
                ? (serverEvents as TaskEvent[])
                : [],
              runActive: false,
            }),
          );
        }
        applyStreamUpdate(evt);
        setPendingApproval(false);
        setStreamConnected(false);
        streamConnectedRef.current = false;
        const doneMessages = Array.isArray(serverMessages)
          ? (serverMessages as TaskMessage[])
          : [];
        const doneStillStreaming = doneMessages.some(
          (msg) => msg?.role === "assistant" && msg.streaming,
        );
        if (!doneStillStreaming) {
          setTask((prev) =>
            prev ? { ...prev, runStatus: "idle", run_status: "idle" } : prev,
          );
          stopRunStatusPoll();
        } else {
          // Premature terminal snapshot (e.g. stale reconnect): keep polling
          // so a page refresh or recovery reconnect can attach to the live run.
          startRunStatusPoll();
        }
        return;
      }

      if (type === "error") {
        const content = formatStreamError(String(evt.content ?? evt.message ?? ""));
        if (teamMode) {
          applyStreamUpdate({ ...evt, content, actor_id: "error", sender: "系统" });
        } else {
          applyStreamUpdate({ ...evt, content });
        }
        if (isFatalStreamError(evt)) {
          setPendingApproval(false);
          setTask((prev) =>
            prev ? { ...prev, runStatus: "idle", run_status: "idle" } : prev,
          );
        }
        return;
      }
      applyStreamUpdate(evt);
    },
    [artifact, applyStreamUpdate, stopRunStatusPoll, startRunStatusPoll],
  );

  const appendFileToComposer = useCallback(
    (path: string) => {
      const label = path.split("/").pop() || path;
      const snippet = `@${label}`;
      setInput((prev) => {
        const trimmed = prev.trim();
        if (!trimmed) return snippet;
        if (trimmed.includes(snippet)) return prev;
        return `${trimmed}\n${snippet}`;
      });
      composerInputRef.current?.focus();
    },
    [],
  );

  const handleArtifactContextMenu = useCallback(
    (path: string, event: MouseEvent) => {
      artifact.showContextMenu(path, event);
    },
    [artifact],
  );

  const renderAssistantContent = (
    text: string,
    options: {
      streaming?: boolean;
      message?: Record<string, unknown>;
      liveArtifacts?: boolean;
    } = {},
  ) => {
    const fromMessage = artifact.buildTurnArtifacts(options.message ?? {}, text);
    const fromLive = options.liveArtifacts
      ? artifact.buildLiveTurnArtifacts(text)
      : [];
    const turnArtifacts = mergeArtifactLists(fromMessage, fromLive);
    const products = turnArtifacts.filter(
      (item: ArtifactItem) => item.role === "product",
    );
    const changes = turnArtifacts.filter(
      (item: ArtifactItem) => item.role === "change",
    );

    return (
      <>
        {text ? (
          <InteractiveAssistantMarkdown
            content={text}
            streaming={options.streaming}
            onFileRefClick={(fileName) => void artifact.openFileRef(fileName)}
            onFileRefContextMenu={(fileName, event) =>
              handleArtifactContextMenu(fileName, event)
            }
          />
        ) : null}
        {(products.length > 0 || changes.length > 0) ? (
          <TurnArtifacts
            products={products}
            changes={changes}
            onOpen={(item) => void artifact.openArtifact(item)}
            onContextMenu={(item, event) =>
              handleArtifactContextMenu(item.path, event)
            }
            onViewAll={(tab) => void artifact.openPanel({ tab })}
          />
        ) : null}
      </>
    );
  };

  const runStream = useCallback(
    async (
      message: string,
      options: {
        reconnect?: boolean;
        fromRecovery?: boolean;
        resolvedAssignee?: Assignee;
      } = {},
    ) => {
      if (!taskId) return;
      const runTaskId = taskId;
      const trimmed = message.trim();
      if (!trimmed && !options.reconnect) return;

      abortRef.current?.abort();
      const streamGen = ++streamGenRef.current;
      streamOwnerTaskIdRef.current = runTaskId;
      doneHadMessagesRef.current = false;
      const controller = new AbortController();
      abortRef.current = controller;

      const runAssignee = options.resolvedAssignee ?? activeAssignee;
      const teamMode = runAssignee.type === "team";
      if (!options.reconnect && trimmed) {
        stopRunStatusPoll();
        recoveryAttemptedRef.current = false;
        setChatState((prev) => ({
          ...prev,
          turns: [
            ...prev.turns,
            {
              id: `local:user:${Date.now()}`,
              role: "user",
              name: "You",
              avatarKind: "user",
              text: trimmed,
              traceEvents: [],
              streaming: false,
            },
          ],
        }));
        setInput("");
        focusComposer();
        stickToBottomRef.current = true;
      }

      setStreamConnected(true);
      streamConnectedRef.current = true;
      startRunStatusPoll();
      reconnectStreamRef.current = Boolean(options.reconnect);
      if (options.reconnect) {
        reconnectInFlightRef.current = true;
      } else {
        setChatState((prev) => ({ ...prev, streamActive: true }));
      }
      setPendingApproval(false);

      const payload = buildChatPayload({
        taskId,
        message: trimmed,
        assignee: runAssignee,
        skillNames,
        planMode,
        teams,
        reconnect: options.reconnect,
      });

      if (!options.reconnect && payload.intent !== "skill_create") {
        setSkillTag(null);
        if (skillNames.includes(SKILL_CREATOR_SKILL)) {
          const nextSkills = skillNames.filter((name) => name !== SKILL_CREATOR_SKILL);
          useComposerStore.getState().setSkillNames(nextSkills);
          if (taskId) {
            saveComposerTaskCache(taskId, {
              ...readComposerSnapshot(),
              skillNames: nextSkills,
            });
          }
        }
      }

      const streamOptions = {
        signal: controller.signal,
        idleTimeoutMs: teamMode
          ? STREAM_TEAM_IDLE_TIMEOUT_MS
          : STREAM_IDLE_TIMEOUT_MS,
      };

      const onStreamEvent = (evt: StreamEvent) =>
        handleStreamEvent(evt, teamMode, runTaskId);

      try {
        if (options.reconnect) {
          await chatStreamReconnect(
            runTaskId,
            onStreamEvent,
            streamOptions,
          );
        } else {
          await chatStream(payload, onStreamEvent, {
            ...streamOptions,
          });
        }
      } catch (err) {
        const aborted =
          stoppedByUserRef.current ||
          (err instanceof Error && err.name === "AbortError");
        if (!aborted) {
          const msg = err instanceof Error ? err.message : String(err);
          const errText = formatStreamError(msg);
          applyStreamUpdate({ type: "error", content: errText });
        }
      } finally {
        if (streamGenRef.current !== streamGen) return;
        if (streamOwnerTaskIdRef.current !== runTaskId) return;

        const userStopped = stoppedByUserRef.current;
        stoppedByUserRef.current = false;
        // The SSE `done` event already hydrated from the authoritative
        // `done.messages` snapshot. Re-running loadTask() here would hydrate a
        // second time (historically a source of duplicated turns), so only fall
        // back to a server reload when no `done.messages` arrived -- e.g. the
        // stream dropped mid-run, or wizard turns that lag behind.
        const doneHydrated = doneHadMessagesRef.current;
        applyStreamUpdate({ type: "done" });
        reconnectStreamRef.current = false;
        setStreamConnected(false);
        setReconnectInFlight(false);
        streamConnectedRef.current = false;
        reconnectInFlightRef.current = false;

        if (doneHydrated) {
          // Clean completion: the run finished and the transcript is already in
          // sync with the server snapshot. No second hydration, no recovery.
          stopRunStatusPoll();
          return;
        }

        let remote: Awaited<ReturnType<typeof tasksApi.get>> | null = null;
        try {
          remote = await loadTask();
        } catch {
          /* keep local messages including partial draft */
        }

        if (
          !userStopped &&
          !options.fromRecovery &&
          remote &&
          isTaskRunActive(remote) &&
          !recoveryAttemptedRef.current
        ) {
          recoveryAttemptedRef.current = true;
          reconnectInFlightRef.current = true;
          setReconnectInFlight(true);
          try {
            await runStream("", {
              reconnect: true,
              fromRecovery: true,
              resolvedAssignee: runAssignee,
            });
          } catch {
            /* recovery reconnect failed — fall through to polling */
          } finally {
            reconnectInFlightRef.current = false;
            setReconnectInFlight(false);
          }
          return;
        }

        if (!userStopped && remote && isTaskRunActive(remote)) {
          startRunStatusPoll();
        } else {
          stopRunStatusPoll();
        }
      }
    },
    [
      taskId,
      activeAssignee,
      skillNames,
      planMode,
      teams,
      handleStreamEvent,
      applyStreamUpdate,
      loadTask,
      stopRunStatusPoll,
      startRunStatusPoll,
      focusComposer,
    ],
  );

  const clearConsumedLocationState = useCallback(
    (keys: (keyof LocationState)[]) => {
      const state = location.state as LocationState | null;
      if (!state) return;
      if (!keys.some((key) => state[key] !== undefined)) return;
      const next = { ...state } as Record<string, unknown>;
      for (const key of keys) delete next[key as string];
      navigate(location.pathname + location.search, {
        replace: true,
        state: Object.keys(next).length ? next : null,
      });
    },
    [location.pathname, location.search, location.state, navigate],
  );

  useEffect(() => {
    if (!taskId || initialSentRef.current) return;
    const state = location.state as LocationState | null;
    const initial = state?.initialMessage?.trim();
    if (initial) {
      initialSentRef.current = true;
      clearConsumedLocationState(["initialMessage"]);
      void runStream(initial);
      return;
    }
    if (isTaskRunActive(task)) {
      // Only auto-reconnect when *opening* a task that is already running on the
      // server (e.g. after a page refresh). If this component already drives an
      // active stream, the run going "running" is just an echo of our own
      // `stream_start`; opening a second stream here would abort the live one
      // and orphan the reply (empty assistant bubble / stuck team run).
      if (streamConnectedRef.current || reconnectInFlightRef.current) {
        initialSentRef.current = true;
        return;
      }
      initialSentRef.current = true;
      void runStream("", { reconnect: true, fromRecovery: true });
    }
  }, [location.state, taskId, task, runStream, clearConsumedLocationState]);

  useEffect(() => {
    if (!taskId) return;
    if (composerDraftAppliedRef.current === taskId) return;

    const state = location.state as LocationState | null;
    const draft = state?.composerDraft?.trim();
    if (!draft) return;

    composerDraftAppliedRef.current = taskId;
    setInput(draft);
    if (state?.skillTag) {
      setSkillTag(state.skillTag);
    }

    const marker = state?.selectDraftMarker ?? "……";
    window.requestAnimationFrame(() => {
      const el = composerInputRef.current;
      if (!el) return;
      el.focus();
      const start = draft.indexOf(marker);
      if (start >= 0) {
        el.setSelectionRange(start, start + marker.length);
      }
    });
    clearConsumedLocationState([
      "composerDraft",
      "skillTag",
      "selectDraftMarker",
    ]);
  }, [location.state, taskId, clearConsumedLocationState]);

  const handleStop = () => {
    if (!isAgentRunning(task, streamConnected, reconnectInFlight, chatState.turns, activeTeam)) return;
    stoppedByUserRef.current = true;
    abortRef.current?.abort();
    stopRunStatusPoll();
    setStreamConnected(false);
    setReconnectInFlight(false);
    setTask((prev) =>
      prev ? { ...prev, runStatus: "stopped", run_status: "stopped" } : prev,
    );
    if (taskId) {
      void tasksApi.stop(taskId).catch(() => {
        /* ignore */
      });
    }
  };

  const handleApprove = async (approved: boolean) => {
    if (!taskId) return;
    try {
      await chatApprove(taskId, approved);
      setPendingApproval(false);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : String(err));
    }
  };

  if (!taskId) {
    return <div className="p-6 text-gray-500">无效任务</div>;
  }

  const displayTurns = chatState.turns;
  const agentRunning = isAgentRunning(
    task,
    streamConnected,
    reconnectInFlight,
    displayTurns,
    activeTeam,
  );

  const renderChatTurn = (
    turn: (typeof chatState.turns)[number],
    idx: number,
  ) => {
      const isUser = turn.role === "user";
      const text = turn.text;
      const storedTraces = turn.traceEvents;
      const showObservability =
        !isUser && (storedTraces.length > 0 || turn.streaming);
      if (isUser && !text) return null;
      if (!isUser && !text && !showObservability) return null;
      return (
        <div
          key={turn.id || `msg-${idx}-${isUser ? "u" : "a"}`}
          className={isUser ? "flex justify-end" : undefined}
        >
          {isUser ? (
            <div className="max-w-[85%] rounded-2xl bg-emerald-600 px-4 py-2.5 text-[14px] leading-relaxed text-white shadow-sm">
              <div className="whitespace-pre-wrap">{text}</div>
            </div>
          ) : (
            <AssistantTurnRow
              breathing={turn.streaming}
              traces={showObservability ? storedTraces : []}
              isStreaming={turn.streaming}
              sender={turn.name}
              speakerAvatar={resolveSpeakerAvatar(turn.name)}
            >
              {text ? (
                renderAssistantContent(text, {
                  message: (turn.sourceMessage ?? {}) as Record<string, unknown>,
                  streaming: turn.streaming,
                  liveArtifacts: true,
                })
              ) : turn.streaming && storedTraces.length === 0 ? (
                <div className="text-gray-400">正在回复…</div>
              ) : null}
              {turn.error && isModelConfigurationError(turn.error) ? (
                <Link
                  to="/settings"
                  className="mt-2 inline-block text-[13px] font-medium text-red-700 underline"
                >
                  前往设置配置 API Key →
                </Link>
              ) : null}
            </AssistantTurnRow>
          )}
        </div>
      );
  };

  const teamLeaderProfile = activeTeam
    ? resolveTeamRepresentativeProfile(activeTeam, employees)
    : null;
  const teamLeaderLabel = activeTeam
    ? teamLeaderDisplayName(activeTeam.name)
    : "Leader";

  const renderLeaderDelegation = (
    text: string,
    itemKey: string,
    streaming = false,
  ) => (
    <AssistantTurnRow
      key={itemKey}
      sender={teamLeaderLabel}
      speakerAvatar={teamLeaderProfile ?? undefined}
      breathing={streaming}
      isStreaming={streaming}
    >
      {renderAssistantContent(text, {
        streaming,
        liveArtifacts: true,
      })}
    </AssistantTurnRow>
  );

  const renderTeamAssistantText = (
    text: string,
    options: { streaming?: boolean } = {},
  ) =>
    renderAssistantContent(text, {
      streaming: options.streaming,
      liveArtifacts: true,
    });

  const renderTeamMemberText = (
    text: string,
    options: { streaming?: boolean } = {},
  ) =>
    renderAssistantContent(text, {
      streaming: options.streaming,
      liveArtifacts: true,
    });

  const renderMemberReply = (
    turn: (typeof chatState.turns)[number],
    idx: number,
    memberLabel: string,
  ) => {
    const text = turn.text;
    const hasTrace = turn.traceEvents.length > 0;
    if (!text && !turn.streaming && !hasTrace) return null;
    const memberAvatar = resolveSpeakerAvatar(memberLabel);
    return (
      <div
        key={turn.id || `member-${idx}`}
        className="flex justify-end gap-2.5"
      >
        <div className="min-w-0 max-w-[85%]">
          <div className="mb-1 text-right text-[12px] font-medium text-slate-600">
            {memberLabel}
          </div>
          {hasTrace || turn.streaming ? (
            <div className="mb-1.5">
              <ProcessObservability
                events={turn.traceEvents}
                isStreaming={turn.streaming}
                className="mb-0"
              />
            </div>
          ) : null}
          {!text && !turn.streaming ? null : text || !hasTrace ? (
          <div
            className={[
              ASSISTANT_BUBBLE_CLASSES,
              turn.streaming ? "animate-pulse" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {text ? (
              renderAssistantContent(text, {
                message: (turn.sourceMessage ?? {}) as Record<string, unknown>,
                streaming: turn.streaming,
                liveArtifacts: true,
              })
            ) : (
              <div className="text-gray-400">正在回复…</div>
            )}
          </div>
          ) : null}
        </div>
        {memberAvatar ? (
          <AgentAvatar
            name={memberAvatar.name}
            avatar={memberAvatar.avatar}
            description={memberAvatar.description}
            portraitName={memberAvatar.portraitName}
            portraitDescription={memberAvatar.portraitDescription}
            role={memberAvatar.role}
            size="sm"
            className="mt-5 shrink-0"
          />
        ) : null}
      </div>
    );
  };

  const approvalBanner =
    pendingApproval ? (
      <div className="flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
        <span className="text-[13px] text-amber-900">需要您的审批</span>
        <button
          type="button"
          className="rounded bg-emerald-600 px-3 py-1 text-[12px] text-white"
          onClick={() => void handleApprove(true)}
        >
          批准
        </button>
        <button
          type="button"
          className="rounded border border-gray-300 bg-white px-3 py-1 text-[12px]"
          onClick={() => void handleApprove(false)}
        >
          拒绝
        </button>
      </div>
    ) : null;

  const showTitleLoading =
    taskLoading &&
    !task?.title &&
    displayTurns.length === 0 &&
    !streamConnected &&
    !reconnectInFlight;

  return (
    <div className="flex h-full min-h-0 bg-[#f8faf9]">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="shrink-0 border-b border-gray-200/80 bg-white/95 px-6 py-4 backdrop-blur-sm">
          <div className="mx-auto max-w-[860px]">
            <div className="text-[18px] font-semibold text-gray-900">
              {showTitleLoading ? "加载中…" : task?.title || "任务会话"}
            </div>
            <div className="mt-1 text-[12px] text-gray-500">
              任务会话 ·{" "}
              {activeAssignee.type === "team"
                ? "团队模式 · 会话标签"
                : "单智能体"}
            </div>
          </div>
        </div>

        <div className="relative flex min-h-0 flex-1 flex-col">
          {teamChatMode ? (
            <TeamChatTabbedView
              turns={displayTurns}
              team={activeTeam}
              employees={employees}
              activeSession={teamActiveSession}
              onActiveSessionChange={setTeamActiveSession}
              renderTurn={renderChatTurn}
              renderLeaderDelegation={renderLeaderDelegation}
              renderMemberReply={renderMemberReply}
              renderAssistantText={renderTeamAssistantText}
              renderMemberText={renderTeamMemberText}
              scrollRef={scrollRef}
              onScroll={handleMessagesScroll}
              footer={
                approvalBanner ? (
                  <div className="bg-[#f8faf9] px-4 py-3">
                    <div className="mx-auto max-w-[860px]">{approvalBanner}</div>
                  </div>
                ) : null
              }
            />
          ) : (
            <>
          <div
            ref={scrollRef}
            onScroll={handleMessagesScroll}
            className="h-full overflow-auto px-6 py-4 scrollbar-hide"
          >
            <div className="mx-auto max-w-[860px] space-y-3">
            {displayTurns.map((turn, idx) => renderChatTurn(turn, idx))}
            {approvalBanner}
            </div>
          </div>

          {scrollMetrics.hasOverflow ? (
            <div
              className={`wm-chat-scrollbar${
                scrollbarVisible || thumbDragging ? " wm-chat-scrollbar--visible" : ""
              }${thumbDragging ? " wm-chat-scrollbar--dragging" : ""}`}
              aria-hidden="true"
            >
              <button
                type="button"
                className="wm-chat-scrollbar__arrow"
                aria-label="向上滚动"
                onClick={() => scrollMessagesBy(-1)}
              >
                <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
                  <path
                    d="M2.5 7.5 6 4l3.5 3.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
              <div
                className="wm-chat-scrollbar__track"
                onPointerDown={handleTrackPointerDown}
              >
                <div
                  className={`wm-chat-scrollbar__thumb${
                    thumbDragging ? " wm-chat-scrollbar__thumb--dragging" : ""
                  }`}
                  style={{
                    height: scrollMetrics.thumbHeight,
                    transform: `translateY(${scrollMetrics.thumbTop}px)`,
                  }}
                  onPointerDown={handleThumbPointerDown}
                  onPointerMove={handleThumbPointerMove}
                  onPointerUp={handleThumbPointerUp}
                  onPointerCancel={handleThumbPointerCancel}
                />
              </div>
              <button
                type="button"
                className="wm-chat-scrollbar__arrow"
                aria-label="向下滚动"
                onClick={() => scrollMessagesBy(1)}
              >
                <svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true">
                  <path
                    d="M2.5 4.5 6 8l3.5-3.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>
          ) : null}
            </>
          )}
        </div>

        <div className="shrink-0 bg-[#f8faf9]">
          <div className="mx-auto max-w-[860px] px-6 pb-4 pt-2">
            {skillTag ? (
              <div className="mb-2 inline-flex items-center gap-1.5 rounded-lg border border-emerald-100 bg-emerald-50 px-2.5 py-1 text-[12px] font-medium text-emerald-700">
                <svg viewBox="0 0 20 20" fill="none" className="h-3.5 w-3.5" aria-hidden="true">
                  <path
                    d="M7.5 3.5l-1 3-3 1 3 1 1 3 1-3 3-1-3-1-1-3z"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinejoin="round"
                  />
                </svg>
                <span>{skillTag}</span>
              </div>
            ) : null}
            {teamChatMode && teamPartition ? (
              <TeamSessionTabs
                team={activeTeam}
                memberNames={teamPartition.memberNames}
                memberTurnsByName={teamPartition.memberTurnsByName}
                employees={employees}
                activeSession={teamActiveSession}
                onSelectSession={setTeamActiveSession}
                docked
              />
            ) : null}
            <div className="relative w-full">
              <div
                className={[
                  "wm-composer wm-home-composer w-full p-4 transition-[filter,opacity] duration-200",
                  teamMemberSessionActive
                    ? "pointer-events-none select-none opacity-35 blur-[2px]"
                    : "",
                ].join(" ")}
              >
                <textarea
                  ref={composerInputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void runStream(input);
                    }
                  }}
                  placeholder="输入消息..."
                  aria-label="任务消息输入"
                  readOnly={teamMemberSessionActive}
                  tabIndex={teamMemberSessionActive ? -1 : 0}
                  className="min-h-[80px] w-full resize-none border-none bg-transparent text-[14px] leading-relaxed text-gray-800 placeholder:text-gray-400 outline-none"
                />
                <ComposerToolbar
                  taskId={taskId}
                  submitButtonId="chatSendBtn"
                  onSend={() => void runStream(input)}
                  onStop={handleStop}
                  streaming={agentRunning}
                  disabled={!input.trim() && !agentRunning}
                  workspaceOpen={artifact.panelOpen}
                  showTopDivider={false}
                  onWorkspaceToggle={() => {
                    if (artifact.panelOpen) {
                      artifact.closePanel();
                    } else {
                      void artifact.openPanel();
                    }
                  }}
                />
              </div>
              {teamMemberSessionActive ? (
                <div className="absolute inset-0 flex items-center justify-center rounded-2xl bg-[#f8faf9]/55 backdrop-blur-md">
                  <button
                    type="button"
                    onClick={() => setTeamActiveSession("leader")}
                    className="inline-flex min-h-[40px] cursor-pointer items-center gap-2 rounded-full border border-white/80 bg-white/85 px-4 py-2 text-[14px] font-medium text-slate-700 shadow-sm backdrop-blur-sm transition-colors duration-200 hover:bg-white hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-500"
                    aria-label="返回主会话继续对话"
                  >
                    <svg
                      viewBox="0 0 20 20"
                      width="16"
                      height="16"
                      aria-hidden="true"
                      className="shrink-0 text-slate-500"
                    >
                      <path
                        d="M11.5 4.5 6.5 10l5 5.5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.6"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                    返回主会话继续对话
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      <ArtifactPanel
        taskId={taskId}
        open={artifact.panelOpen}
        tab={artifact.panelTab}
        selectedPath={artifact.selectedPath}
        productArtifacts={artifact.productArtifacts}
        onTabChange={artifact.setPanelTab}
        onSelectPath={artifact.setSelectedPath}
        onClose={artifact.closePanel}
        onFileContextMenu={handleArtifactContextMenu}
      />

      <ArtifactContextMenu
        open={artifact.contextMenu.open}
        x={artifact.contextMenu.x}
        y={artifact.contextMenu.y}
        onClose={artifact.closeContextMenu}
        onOpenFolder={() => void artifact.handleOpenFolder()}
        onShareFile={() => void artifact.handleShareFile()}
        onAddToComposer={() => {
          appendFileToComposer(artifact.contextMenu.path);
          artifact.closeContextMenu();
        }}
      />
    </div>
  );
}
