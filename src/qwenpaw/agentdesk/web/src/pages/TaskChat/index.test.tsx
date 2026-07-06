import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import type { StreamEvent } from "../../api/chatStream";
import type { Assignee } from "../../types/assignee";
import { getDefaultAssignee } from "../../types/assignee";
import TaskChatPage from "./index";
import { clearTaskChatStateCache } from "../../utils/taskChatStateCache";
import { clearComposerTaskCache } from "../../utils/composerTaskCache";

const chatStreamMock = vi.fn();
const chatStreamReconnectMock = vi.fn();

const { appStoreState, isAgentRunningMock, isTaskRunActiveMock } = vi.hoisted(
  () => ({
    appStoreState: {
      tasks: [] as unknown[],
      updateTask: vi.fn(),
      setActiveTaskId: vi.fn(),
    },
    isAgentRunningMock: vi.fn(
      (_task: unknown, streamConnected: boolean, reconnecting = false) =>
        streamConnected || reconnecting,
    ),
    isTaskRunActiveMock: vi.fn(
      (_task?: { runStatus?: string } | null) => false,
    ),
  }),
);

vi.mock("../../api/chatStream", () => ({
  chatApprove: vi.fn(),
  chatStream: (...args: unknown[]) => chatStreamMock(...args),
  chatStreamReconnect: (...args: unknown[]) => chatStreamReconnectMock(...args),
}));

vi.mock("../../api/teams", () => ({
  teamsApi: {
    listTeams: vi.fn().mockResolvedValue([]),
  },
}));

const getTaskMock = vi.fn().mockResolvedValue({
  id: "t1",
  title: "Trace task",
  runStatus: "idle",
  run_status: "idle",
  messages: [
    { role: "user", id: "u1", content: "hello" },
    { role: "assistant", id: "a1", content: "final answer" },
  ],
});

const getEventsMock = vi.fn().mockResolvedValue([
  { type: "trace", step: "thinking_start", message_id: "a1" },
  { type: "trace", step: "thinking_end", detail: "plan complete", message_id: "a1" },
  { type: "trace", step: "tool_call_start", tool_name: "search", tool_call_id: "c1", message_id: "a1" },
  { type: "trace", step: "tool_result_end", tool_name: "search", tool_call_id: "c1", detail: "done", state: "success", message_id: "a1" },
]);

vi.mock("../../api/tasks", () => ({
  tasksApi: {
    get: (...args: unknown[]) => getTaskMock(...args),
    getEvents: (...args: unknown[]) => getEventsMock(...args),
    stop: vi.fn(),
  },
}));

vi.mock("../../components/chat/ArtifactContextMenu", () => ({
  default: () => null,
}));

vi.mock("../../components/chat/InteractiveAssistantMarkdown", () => ({
  default: ({ content }: { content: string }) => (
    <div data-testid="assistant-md">{content}</div>
  ),
}));

vi.mock("../../components/chat/TurnArtifacts", () => ({
  default: () => null,
}));

vi.mock("../../components/composer/ComposerToolbar", () => ({
  default: ({
    onSend,
    disabled,
  }: {
    onSend: () => void;
    disabled?: boolean;
  }) => (
    <button
      type="button"
      aria-label="发送消息"
      disabled={disabled}
      onClick={onSend}
    >
      发送
    </button>
  ),
}));

vi.mock("../../components/task/ArtifactPanel", () => ({
  default: () => null,
}));

vi.mock("../../components/branding/AgentDeskIcon", () => ({
  AgentDeskAvatar: () => <div data-testid="wm-avatar" />,
}));

vi.mock("../../hooks/useArtifactInteractions", () => ({
  useArtifactInteractions: () => ({
    panelOpen: false,
    panelTab: "products",
    selectedPath: "",
    productArtifacts: [],
    contextMenu: { open: false, x: 0, y: 0, path: "" },
    resetLiveArtifacts: vi.fn(),
    pushLiveArtifact: vi.fn(),
    takeLiveArtifacts: vi.fn(() => []),
    attachArtifactsToMessage: vi.fn((msg) => msg),
    buildLiveTurnArtifacts: vi.fn(() => []),
    buildTurnArtifacts: vi.fn(() => []),
    openFileRef: vi.fn(),
    openArtifact: vi.fn(),
    openPanel: vi.fn(async () => {}),
    closePanel: vi.fn(),
    setPanelOpen: vi.fn(),
    setPanelTab: vi.fn(),
    setSelectedPath: vi.fn(),
    showContextMenu: vi.fn(),
    closeContextMenu: vi.fn(),
    handleOpenFolder: vi.fn(),
    handleShareFile: vi.fn(),
    reset: vi.fn(),
  }),
}));

vi.mock("../../store/appStore", () => {
  // Real Zustand returns *stable* action references across renders. Recreating
  // the state object on every selector call (the previous behavior) handed back
  // a fresh `updateTask`/`setActiveTaskId` each render, which made
  // refreshTaskFromServer/loadTask/runStream unstable and drove the hydration
  // effect into an infinite setState→re-render loop (heap OOM) as soon as a
  // send-click injected non-bailing state updates.
  return {
    useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
      selector(appStoreState),
  };
});

const composerStoreState: {
  assignee: Assignee;
  skillNames: string[];
  planMode: boolean;
  resetForNewChat: ReturnType<typeof vi.fn>;
  applyComposerSnapshot: ReturnType<typeof vi.fn>;
  setAssignee: ReturnType<typeof vi.fn>;
  setSkillNames: ReturnType<typeof vi.fn>;
  setPlanMode: ReturnType<typeof vi.fn>;
} = {
  assignee: getDefaultAssignee(),
  skillNames: [],
  planMode: false,
  resetForNewChat: vi.fn((skillNames: string[] = [], assignee?: Assignee) => {
    composerStoreState.assignee = assignee ?? getDefaultAssignee();
    composerStoreState.skillNames = skillNames;
    composerStoreState.planMode = false;
  }),
  applyComposerSnapshot: vi.fn((snapshot: {
    assignee: Assignee;
    skillNames: string[];
    planMode: boolean;
  }) => {
    composerStoreState.assignee = snapshot.assignee;
    composerStoreState.skillNames = [...snapshot.skillNames];
    composerStoreState.planMode = snapshot.planMode;
  }),
  setAssignee: vi.fn((assignee: Assignee) => {
    composerStoreState.assignee = assignee;
  }),
  setSkillNames: vi.fn((names: string[]) => {
    composerStoreState.skillNames = names;
  }),
  setPlanMode: vi.fn((enabled: boolean) => {
    composerStoreState.planMode = enabled;
  }),
};

vi.mock("../../store/composerStore", () => ({
  useComposerStore: Object.assign(
    (selector: (state: Record<string, unknown>) => unknown) =>
      selector(composerStoreState),
    {
      getState: () => composerStoreState,
    },
  ),
}));

vi.mock("../../store/skillsStore", () => ({
  useSkillsStore: {
    getState: () => ({ bumpSkillsRevision: vi.fn() }),
  },
}));

const referenceDataState = {
  teams: [] as unknown[],
  employees: [] as unknown[],
  skills: [] as unknown[],
  providers: [] as unknown[],
  loadedAt: 0,
  loading: false,
  ensureLoaded: vi.fn().mockResolvedValue(undefined),
  refresh: vi.fn().mockResolvedValue(undefined),
  refreshEmployees: vi.fn().mockResolvedValue(undefined),
  refreshTeams: vi.fn().mockResolvedValue(undefined),
  refreshSkills: vi.fn().mockResolvedValue(undefined),
  invalidate: vi.fn(),
};

vi.mock("../../store/referenceDataStore", () => ({
  useReferenceDataStore: Object.assign(
    (selector: (state: Record<string, unknown>) => unknown) =>
      selector(referenceDataState),
    { getState: () => referenceDataState },
  ),
}));

vi.mock("../../utils/streamErrorHandling", () => ({
  isFatalStreamError: () => true,
}));

vi.mock("../../utils/taskRunStatus", () => ({
  isAgentRunning: (
    task: unknown,
    streamConnected: boolean,
    reconnecting?: boolean,
  ) => isAgentRunningMock(task, streamConnected, reconnecting),
  isTaskRunActive: (task: unknown) =>
    isTaskRunActiveMock(task as { runStatus?: string } | null),
}));

class ResizeObserverMock {
  observe() {}
  disconnect() {}
  unobserve() {}
}

describe("TaskChatPage trace layout", () => {
  beforeEach(() => {
    clearTaskChatStateCache();
    clearComposerTaskCache();
    composerStoreState.assignee = getDefaultAssignee();
    composerStoreState.skillNames = [];
    composerStoreState.planMode = false;
    chatStreamMock.mockReset();
    chatStreamReconnectMock.mockReset();
    getTaskMock.mockClear();
    getEventsMock.mockClear();
  });

  it("renders process panel above assistant bubble", async () => {
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);

    render(
      <MemoryRouter initialEntries={["/task/t1"]}>
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("Trace task");
    await waitFor(() => expect(getEventsMock).toHaveBeenCalledWith("t1"));

    const traceToggle = screen.getByRole("button", { name: /工具调用 1，过程消息 1/i });
    const assistant = screen.getByTestId("assistant-md");
    const avatar = screen.getByTestId("wm-avatar");

    expect(traceToggle.compareDocumentPosition(assistant) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(avatar.compareDocumentPosition(traceToggle) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByTestId("assistant-md")).toHaveTextContent("final answer");
    expect(screen.getByTestId("assistant-md")).not.toHaveTextContent(
      "plan complete",
    );
    // Default agent renders under its single canonical brand identity.
    expect(screen.getByText("AgentDesk企伴")).toBeInTheDocument();
  });
});

describe("TaskChatPage team streaming", () => {
  const teamFixture = {
    id: "team-1",
    name: "测试团队",
    tags: [],
    desc: "",
    avatar: "",
    members: ["成员A"],
    leader: "Leader",
  };

  function isMemberWatchPayload(payload: unknown): boolean {
    return Boolean(
      payload &&
        typeof payload === "object" &&
        String((payload as { team_member?: string }).team_member || "").trim(),
    );
  }

  function mockMainChatStream(
    impl: (
      payload: unknown,
      onEvent: (evt: StreamEvent) => void,
    ) => Promise<void> | void,
  ) {
    chatStreamMock.mockImplementation(async (payload, onEvent) => {
      if (isMemberWatchPayload(payload)) return;
      await impl(payload, onEvent);
    });
  }

  beforeEach(() => {
    clearTaskChatStateCache();
    clearComposerTaskCache();
    composerStoreState.assignee = {
      type: "team",
      name: "测试团队",
      teamId: "team-1",
    };
    referenceDataState.teams = [teamFixture];
    chatStreamMock.mockReset();
    chatStreamReconnectMock.mockReset();
    getTaskMock.mockClear();
    getEventsMock.mockClear();
    getTaskMock.mockResolvedValue({
      id: "t1",
      title: "Trace task",
      runStatus: "idle",
      run_status: "idle",
      mode: "team",
      team_id: "team-1",
      team_name: "测试团队",
      messages: [],
    });
    getEventsMock.mockResolvedValue([]);
  });

  afterEach(() => {
    referenceDataState.teams = [];
  });

  it("keeps live team actors mounted across worker transitions without reloading title", async () => {
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);

    const events: StreamEvent[] = [
      { type: "stream_start" },
      { type: "text_delta", delta: "leader plan", sender: "Leader" },
      { type: "worker_start", worker: "成员A", actor_id: "成员A" },
      { type: "text_delta", delta: "worker reply", worker: "成员A", actor_id: "成员A" },
      { type: "worker_done", worker: "成员A", actor_id: "成员A" },
      {
        type: "done",
        messages: [
          { role: "user", id: "u1", content: "hello" },
          { role: "assistant", id: "a1", content: "leader plan", sender: "Leader" },
          { role: "assistant", id: "a2", content: "worker reply", sender: "成员A" },
        ],
      },
    ];

    mockMainChatStream(
      async (
        _payload: unknown,
        onEvent: (evt: StreamEvent) => void,
      ) => {
        for (const evt of events) onEvent(evt);
      },
    );

    render(
      <MemoryRouter
        initialEntries={[{ pathname: "/task/t1", state: { initialMessage: "hello" } }]}
      >
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("Trace task");
    expect(screen.queryByText("加载中…")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("leader plan")).toBeInTheDocument();
    });

    expect(screen.queryByText("worker reply")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("assistant-md")).toHaveLength(1);

    fireEvent.click(
      screen.getByRole("button", { name: /查看 成员A 的成员会话/i }),
    );
    await waitFor(() => {
      expect(screen.getByText("worker reply")).toBeInTheDocument();
    });
    expect(screen.queryByText("leader plan")).not.toBeInTheDocument();
    await waitFor(() => expect(chatStreamMock).toHaveBeenCalled());
  });

  it("shows streaming placeholder after stream_start before text arrives", async () => {
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);

    let resumeStream!: () => void;
    const waitForResume = new Promise<void>((resolve) => {
      resumeStream = resolve;
    });

    mockMainChatStream(
      async (_payload: unknown, onEvent: (evt: StreamEvent) => void) => {
        onEvent({ type: "stream_start", sender: "AgentDesk企伴" });
        await waitForResume;
        onEvent({ type: "text_delta", delta: "你好", sender: "AgentDesk企伴" });
        onEvent({
          type: "done",
          messages: [
            { role: "user", id: "u1", content: "hello" },
            { role: "assistant", id: "a1", content: "你好", sender: "AgentDesk企伴" },
          ],
        });
      },
    );

    render(
      <MemoryRouter
        initialEntries={[{ pathname: "/task/t1", state: { initialMessage: "hello" } }]}
      >
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("hello");
    await waitFor(() => {
      expect(screen.getByText("正在回复…")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("assistant-md")).not.toBeInTheDocument();

    resumeStream();
    await waitFor(() => {
      expect(screen.getByTestId("assistant-md")).toHaveTextContent("你好");
    });
  });

  it("grows team actor bubble as text_delta chunks arrive", async () => {
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);

    let resumeStream!: () => void;
    const waitForResume = new Promise<void>((resolve) => {
      resumeStream = resolve;
    });

    mockMainChatStream(
      async (_payload: unknown, onEvent: (evt: StreamEvent) => void) => {
        onEvent({ type: "stream_start" });
        onEvent({
          type: "text_delta",
          delta: "你",
          sender: "Leader",
          actor_id: "Leader",
        });
        await waitForResume;
        onEvent({
          type: "text_delta",
          delta: "好",
          sender: "Leader",
          actor_id: "Leader",
        });
        onEvent({
          type: "done",
          messages: [
            { role: "user", id: "u1", content: "hello" },
            { role: "assistant", id: "a1", content: "你好", sender: "Leader" },
          ],
        });
      },
    );

    render(
      <MemoryRouter
        initialEntries={[{ pathname: "/task/t1", state: { initialMessage: "hello" } }]}
      >
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("hello");
    await waitFor(() => {
      expect(
        screen
          .getAllByTestId("assistant-md")
          .some((node) => node.textContent === "你"),
      ).toBe(true);
    });
    expect(
      screen
        .getAllByTestId("assistant-md")
        .every((node) => !node.textContent?.includes("好")),
    ).toBe(true);

    resumeStream();
    await waitFor(() => {
      const combined = screen
        .getAllByTestId("assistant-md")
        .map((node) => node.textContent ?? "")
        .join("");
      expect(combined.includes("你") && combined.includes("好")).toBe(true);
    });
  });

  it("keeps leader greeting visible when done payload assistant is empty", async () => {
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);

    const events: StreamEvent[] = [
      {
        type: "team_phase",
        phase: "planning",
        source_member: "开户协同小队·leader",
      },
      {
        type: "stream_start",
        sender: "开户协同小队·leader",
        source_member: "开户协同小队·leader",
      },
      { type: "trace", step: "reply_start" },
      {
        type: "text_delta",
        sender: "开户协同小队·leader",
        source_member: "开户协同小队·leader",
        content: "你好! 我是开户协同小队的 Leader。",
      },
      {
        type: "done",
        messages: [
          { role: "user", id: "u1", content: "你好" },
          {
            role: "assistant",
            id: "a1",
            sender: "开户协同小队·leader",
            content: "",
            streaming: true,
          },
        ],
      },
    ];

    mockMainChatStream(
      async (_payload: unknown, onEvent: (evt: StreamEvent) => void) => {
        for (const evt of events) onEvent(evt);
      },
    );

    render(
      <MemoryRouter
        initialEntries={[{ pathname: "/task/t1", state: { initialMessage: "你好" } }]}
      >
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("你好");
    await waitFor(() => {
      expect(screen.getByTestId("assistant-md")).toHaveTextContent(
        "你好! 我是开户协同小队的 Leader。",
      );
    });
  });

  it("shows return-to-leader overlay on member tab while keeping composer height", async () => {
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);

    getTaskMock.mockResolvedValue({
      id: "t1",
      title: "团队任务",
      runStatus: "idle",
      run_status: "idle",
      mode: "team",
      team_id: "team-1",
      team_name: "测试团队",
      messages: [
        { role: "user", id: "u1", content: "hello" },
        { role: "assistant", id: "a1", content: "leader plan", sender: "测试团队·leader" },
        { role: "assistant", id: "a2", content: "worker reply", sender: "成员A" },
      ],
    });

    render(
      <MemoryRouter initialEntries={["/task/t1"]}>
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("团队任务");
    expect(screen.getByLabelText("任务消息输入")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: /查看 成员A 的成员会话/i }),
    );

    await waitFor(() => {
      expect(screen.getByLabelText("任务消息输入")).toHaveAttribute("readonly");
    });
    expect(
      screen.getByRole("button", { name: "返回主会话继续对话" }),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("button", { name: "返回主会话继续对话" }),
    );

    await waitFor(() => {
      expect(screen.getByLabelText("任务消息输入")).not.toHaveAttribute("readonly");
    });
    expect(screen.getByText("leader plan")).toBeInTheDocument();
    expect(screen.queryByText("worker reply")).not.toBeInTheDocument();
  });

  it("renders leader session tab before member tabs", async () => {
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);

    referenceDataState.teams = [
      {
        id: "team-2",
        name: "分析团队",
        tags: [],
        desc: "",
        avatar: "",
        members: ["研究员", "写手"],
        leader: "PM",
      },
    ];

    getTaskMock.mockResolvedValue({
      id: "t1",
      title: "分析任务",
      runStatus: "idle",
      run_status: "idle",
      mode: "team",
      team_id: "team-2",
      team_name: "分析团队",
      messages: [],
    });

    render(
      <MemoryRouter initialEntries={["/task/t1"]}>
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("分析任务");

    const tablist = screen.getByRole("tablist", { name: "团队会话参与者" });
    const tabs = tablist.querySelectorAll("button");
    expect(tabs[0]).toHaveAccessibleName(/分析团队·leader 主会话/i);
    expect(tabs[1]).toHaveAccessibleName(/查看 研究员 的成员会话/i);
    expect(tabs[2]).toHaveAccessibleName(/查看 写手 的成员会话/i);
  });

  it("renders team session tabs directly above composer input", async () => {
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);

    getTaskMock.mockResolvedValue({
      id: "t1",
      title: "团队任务",
      runStatus: "idle",
      run_status: "idle",
      mode: "team",
      team_id: "team-1",
      team_name: "测试团队",
      messages: [],
    });

    render(
      <MemoryRouter initialEntries={["/task/t1"]}>
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("团队任务");

    const tablist = screen.getByRole("tablist", { name: "团队会话参与者" });
    const composer = screen.getByLabelText("任务消息输入");
    expect(
      tablist.compareDocumentPosition(composer) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

});

describe("TaskChatPage streaming hydration", () => {
  beforeEach(() => {
    clearTaskChatStateCache();
    clearComposerTaskCache();
    appStoreState.tasks = [];
    composerStoreState.assignee = getDefaultAssignee();
    composerStoreState.skillNames = [];
    composerStoreState.planMode = false;
    chatStreamMock.mockReset();
    chatStreamReconnectMock.mockReset();
    getTaskMock.mockClear();
    getEventsMock.mockClear();
    isAgentRunningMock.mockImplementation(
      (_task: unknown, streamConnected: boolean, reconnecting = false) =>
        streamConnected || reconnecting,
    );
    isTaskRunActiveMock.mockReturnValue(false);
    vi.stubGlobal("ResizeObserver", ResizeObserverMock);
  });

  it("renders the sidebar task snapshot immediately while detail hydration is pending", () => {
    appStoreState.tasks = [
      {
        id: "cached-task",
        title: "Cached sidebar task",
        runStatus: "idle",
        run_status: "idle",
        messages: [
          { role: "user", id: "u-cached", content: "cached prompt" },
          {
            role: "assistant",
            id: "a-cached",
            content: "cached answer",
          },
        ],
      },
    ];
    getTaskMock.mockImplementation(
      () =>
        new Promise(() => {
          /* keep detail hydration pending */
        }),
    );
    getEventsMock.mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={["/task/cached-task"]}>
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Cached sidebar task")).toBeInTheDocument();
    expect(screen.getByText("cached prompt")).toBeInTheDocument();
    expect(screen.getByTestId("assistant-md")).toHaveTextContent(
      "cached answer",
    );
  });

  it("starts task detail and event hydration in parallel", async () => {
    getTaskMock.mockImplementation(
      () =>
        new Promise(() => {
          /* keep detail hydration pending */
        }),
    );
    getEventsMock.mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={["/task/t1"]}>
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(getTaskMock).toHaveBeenCalledWith("t1"));
    await waitFor(() => expect(getEventsMock).toHaveBeenCalledWith("t1"));
  });

  it("does not show title loading while streaming with visible messages", async () => {
    let resolveTask!: (value: unknown) => void;
    getTaskMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveTask = resolve;
        }),
    );
    getEventsMock.mockResolvedValue([]);

    chatStreamMock.mockImplementation(
      async (_payload: unknown, onEvent: (evt: StreamEvent) => void) => {
        onEvent({ type: "text_delta", delta: "partial reply" });
        await new Promise(() => {
          /* keep stream open */
        });
      },
    );

    render(
      <MemoryRouter
        initialEntries={[{ pathname: "/task/t1", state: { initialMessage: "hello" } }]}
      >
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("hello");
    expect(screen.queryByText("加载中…")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("assistant-md")).toHaveTextContent("partial reply");
    });

    resolveTask({
      id: "t1",
      title: "Late title",
      runStatus: "running",
      run_status: "running",
      messages: [{ role: "user", id: "u1", content: "hello" }],
    });
    await waitFor(() => expect(screen.getByText("Late title")).toBeInTheDocument());
    expect(screen.queryByText("加载中…")).not.toBeInTheDocument();
  });

  it("does not replace live draft with server messages while stream is open", async () => {
    getTaskMock.mockResolvedValue({
      id: "t1",
      title: "Trace task",
      runStatus: "running",
      run_status: "running",
      messages: [
        { role: "user", id: "u1", content: "hello" },
        { role: "assistant", id: "a-server", content: "server only" },
      ],
    });
    getEventsMock.mockResolvedValue([]);

    chatStreamMock.mockImplementation(
      async (_payload: unknown, onEvent: (evt: StreamEvent) => void) => {
        onEvent({ type: "text_delta", delta: "draft text" });
        await new Promise(() => {
          /* keep stream open */
        });
      },
    );

    render(
      <MemoryRouter
        initialEntries={[{ pathname: "/task/t1", state: { initialMessage: "hello" } }]}
      >
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("assistant-md")).toHaveTextContent("draft text");
    });
    expect(screen.queryByText("server only")).not.toBeInTheDocument();
  });

  it("grows single-agent draft as text_delta chunks arrive", async () => {
    getTaskMock.mockResolvedValue({
      id: "t1",
      title: "Trace task",
      runStatus: "idle",
      run_status: "idle",
      messages: [],
    });
    getEventsMock.mockResolvedValue([]);

    let resumeStream!: () => void;
    const waitForResume = new Promise<void>((resolve) => {
      resumeStream = resolve;
    });

    chatStreamMock.mockImplementation(
      async (_payload: unknown, onEvent: (evt: StreamEvent) => void) => {
        onEvent({ type: "text_delta", delta: "你" });
        await waitForResume;
        onEvent({ type: "text_delta", delta: "好" });
        await new Promise(() => {
          /* keep stream open */
        });
      },
    );

    render(
      <MemoryRouter
        initialEntries={[{ pathname: "/task/t1", state: { initialMessage: "hello" } }]}
      >
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("assistant-md")).toHaveTextContent("你");
    });
    expect(screen.getByTestId("assistant-md")).not.toHaveTextContent("你好");

    resumeStream();
    await waitFor(() => {
      expect(screen.getByTestId("assistant-md")).toHaveTextContent("你好");
    });
  });

  it("keeps assistant text visible through done event without flashing away", async () => {
    getTaskMock.mockResolvedValue({
      id: "t1",
      title: "Trace task",
      runStatus: "idle",
      run_status: "idle",
      messages: [],
    });
    getEventsMock.mockResolvedValue([]);

    chatStreamMock.mockImplementation(
      async (_payload: unknown, onEvent: (evt: StreamEvent) => void) => {
        onEvent({ type: "text_delta", delta: "final body" });
        onEvent({
          type: "done",
          messages: [
            { role: "user", id: "u1", content: "hello" },
            { role: "assistant", id: "a1", content: "final body" },
          ],
        });
      },
    );

    render(
      <MemoryRouter
        initialEntries={[{ pathname: "/task/t1", state: { initialMessage: "hello" } }]}
      >
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("assistant-md")).toHaveTextContent("final body");
    });
    expect(screen.getByTestId("assistant-md")).toHaveTextContent("final body");
  });

  it("merges live draft when done payload assistant is still empty", async () => {
    getTaskMock.mockResolvedValue({
      id: "t1",
      title: "Trace task",
      runStatus: "idle",
      run_status: "idle",
      messages: [],
    });
    getEventsMock.mockResolvedValue([]);

    chatStreamMock.mockImplementation(
      async (_payload: unknown, onEvent: (evt: StreamEvent) => void) => {
        onEvent({ type: "text_delta", delta: "你好！" });
        onEvent({
          type: "done",
          messages: [
            { role: "user", id: "u1", content: "你好" },
            { role: "assistant", id: "a1", content: "", streaming: true },
          ],
        });
      },
    );

    render(
      <MemoryRouter
        initialEntries={[{ pathname: "/task/t1", state: { initialMessage: "你好" } }]}
      >
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("assistant-md")).toHaveTextContent("你好！");
    });
  });

  it("shows persisted assistant reply after reload when streaming flag is stale", async () => {
    getTaskMock.mockResolvedValue({
      id: "t1",
      title: "派发 · SIM卡开通业务员",
      runStatus: "idle",
      run_status: "idle",
      messages: [
        { role: "user", id: "u1", content: "你好" },
        { role: "assistant", id: "a1", content: "你好！", streaming: true },
      ],
    });
    getEventsMock.mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={["/task/t1"]}>
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("派发 · SIM卡开通业务员");
    await waitFor(() => {
      expect(screen.getByTestId("assistant-md")).toHaveTextContent("你好！");
    });
  });

  it("hydrates persisted assistant reply when done payload is stale", async () => {
    getTaskMock
      .mockResolvedValueOnce({
        id: "t1",
        title: "添加员工",
        runStatus: "idle",
        run_status: "idle",
        messages: [],
      })
      .mockResolvedValue({
        id: "t1",
        title: "添加员工",
        runStatus: "idle",
        run_status: "idle",
        messages: [
          { role: "user", id: "u1", content: "帮我创建销售专家" },
          {
            role: "assistant",
            id: "a1",
            content: "已创建员工「销售专家」，并挂载技能 make_plan、file_reader。",
            streaming: false,
          },
        ],
      });
    getEventsMock.mockResolvedValue([]);

    chatStreamMock.mockImplementation(
      async (_payload: unknown, onEvent: (evt: StreamEvent) => void) => {
        onEvent({
          type: "trace",
          step: "tool_call_end",
          tool_name: "create_plaza_card",
        });
        onEvent({
          type: "done",
          messages: [
            { role: "user", id: "u1", content: "帮我创建销售专家" },
            { role: "assistant", id: "a1", content: "", streaming: true },
          ],
        });
      },
    );

    render(
      <MemoryRouter
        initialEntries={[
          {
            pathname: "/task/t1",
            state: { initialMessage: "帮我创建销售专家" },
          },
        ]}
      >
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("assistant-md")).toHaveTextContent(
        "已创建员工「销售专家」，并挂载技能 make_plan、file_reader。",
      );
    });
    expect(getTaskMock.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("sends the initial message exactly once and does not re-seed the input", async () => {
    getTaskMock.mockResolvedValue({
      id: "t1",
      title: "派发 · SIM卡开通业务员",
      runStatus: "idle",
      run_status: "idle",
      messages: [],
    });
    getEventsMock.mockResolvedValue([]);

    chatStreamMock.mockImplementation(
      async (_payload: unknown, onEvent: (evt: StreamEvent) => void) => {
        onEvent({ type: "text_delta", delta: "你好！" });
        onEvent({
          type: "done",
          messages: [
            { role: "user", id: "u1", content: "你好" },
            { role: "assistant", id: "a1", content: "你好！" },
          ],
        });
      },
    );

    render(
      <MemoryRouter
        initialEntries={[{ pathname: "/task/t1", state: { initialMessage: "你好" } }]}
      >
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("assistant-md")).toHaveTextContent("你好！");
    });

    // Give any re-render-driven effects a chance to (incorrectly) re-fire.
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(chatStreamMock.mock.calls.length).toBe(1);
    const composer = screen.getByLabelText("任务消息输入") as HTMLTextAreaElement;
    expect(composer.value).toBe("");
  });

  it("refocuses composer after clicking send", async () => {
    getTaskMock.mockResolvedValue({
      id: "t1",
      title: "Trace task",
      runStatus: "idle",
      run_status: "idle",
      messages: [],
    });
    getEventsMock.mockResolvedValue([]);

    chatStreamMock.mockImplementation(
      async (_payload: unknown, onEvent: (evt: StreamEvent) => void) => {
        onEvent({ type: "text_delta", delta: "reply" });
        onEvent({
          type: "done",
          messages: [
            { role: "user", id: "u1", content: "next message" },
            { role: "assistant", id: "a1", content: "reply" },
          ],
        });
      },
    );

    render(
      <MemoryRouter initialEntries={["/task/t1"]}>
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("Trace task");

    const composer = screen.getByLabelText("任务消息输入") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "next message" } });

    const sendBtn = screen.getByRole("button", { name: "发送消息" });
    sendBtn.focus();
    fireEvent.click(sendBtn);

    await waitFor(() => expect(composer.value).toBe(""));
    await waitFor(() => expect(document.activeElement).toBe(composer));
    expect(composer.disabled).toBe(false);
  });

  it("does not abort its own live stream by spuriously reconnecting", async () => {
    // Regression for the empty-reply bug. Sending a message flips the task to
    // runStatus="running" via our own `stream_start`. The open/recovery effect
    // must NOT treat that as "a run already exists on the server" and open a
    // second (reconnect) stream — doing so aborts the live stream and orphans
    // the reply (empty assistant bubble / stuck team run). The previous test
    // suite masked this by hard-mocking isTaskRunActive => false.
    isTaskRunActiveMock.mockImplementation(
      (task: { runStatus?: string } | null | undefined) =>
        String(task?.runStatus ?? "") === "running",
    );
    getTaskMock.mockResolvedValue({
      id: "t1",
      title: "Trace task",
      runStatus: "idle",
      run_status: "idle",
      messages: [],
    });
    getEventsMock.mockResolvedValue([]);

    chatStreamMock.mockImplementation(
      async (_payload: unknown, onEvent: (evt: StreamEvent) => void) => {
        // Flip runStatus to running, then keep the stream open so the
        // open/recovery effect runs while we are still actively streaming.
        onEvent({ type: "stream_start", sender: "Readme编写大师" });
        onEvent({
          type: "text_delta",
          sender: "Readme编写大师",
          delta: "你好呀！",
        });
        await new Promise(() => {
          /* keep stream open */
        });
      },
    );

    render(
      <MemoryRouter initialEntries={["/task/t1"]}>
        <Routes>
          <Route path="/task/:taskId" element={<TaskChatPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("Trace task");
    const composer = screen.getByLabelText("任务消息输入") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "你好" } });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));

    await waitFor(() => {
      expect(screen.getByTestId("assistant-md")).toHaveTextContent("你好呀！");
    });
    // Give the (previously buggy) open/recovery effect a chance to fire.
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(chatStreamReconnectMock).not.toHaveBeenCalled();
    expect(chatStreamMock.mock.calls.length).toBe(1);
    expect(screen.getByTestId("assistant-md")).toHaveTextContent("你好呀！");
  });
});

describe("TaskChatPage concurrent stream isolation", () => {
  beforeEach(() => {
    clearTaskChatStateCache();
    chatStreamMock.mockReset();
    chatStreamReconnectMock.mockReset();
    getTaskMock.mockReset();
    getEventsMock.mockReset();
    isAgentRunningMock.mockImplementation(
      (_task: unknown, streamConnected: boolean, reconnecting = false) =>
        streamConnected || reconnecting,
    );
    isTaskRunActiveMock.mockImplementation(() => false);
  });

  it("ignores stale stream events after navigating to another task", async () => {
    let staleEmit: ((evt: StreamEvent) => void) | null = null;
    let releaseStale: () => void = () => {};

    getTaskMock.mockImplementation(async (id: string) => ({
      id,
      title: id === "skill-task" ? "技能创建" : "添加员工",
      runStatus: "idle",
      run_status: "idle",
      messages: [],
    }));
    getEventsMock.mockResolvedValue([]);

    chatStreamMock.mockImplementation(
      async (
        payload: { task_id?: string },
        onEvent: (evt: StreamEvent) => void,
      ) => {
        if (payload.task_id === "skill-task") {
          staleEmit = onEvent;
          await new Promise<void>((resolve) => {
            releaseStale = resolve;
          });
          return;
        }
        if (payload.task_id === "employee-task") {
          onEvent({
            type: "text_delta",
            task_id: "employee-task",
            delta: "员工回复",
          });
          onEvent({ type: "done", messages: [], task_id: "employee-task" });
        }
      },
    );

    function NavHarness() {
      const navigate = useNavigate();
      return (
        <>
          <button type="button" onClick={() => navigate("/task/employee-task")}>
            切换任务
          </button>
          <Routes>
            <Route path="/task/:taskId" element={<TaskChatPage />} />
          </Routes>
        </>
      );
    }

    render(
      <MemoryRouter initialEntries={["/task/skill-task"]}>
        <Routes>
          <Route path="*" element={<NavHarness />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("技能创建");
    const composer = screen.getByLabelText("任务消息输入") as HTMLTextAreaElement;
    fireEvent.change(composer, { target: { value: "创建技能测试" } });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));

    await waitFor(() => expect(chatStreamMock).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: "切换任务" }));
    await screen.findByText("添加员工");

    fireEvent.change(composer, { target: { value: "创建员工" } });
    fireEvent.click(screen.getByRole("button", { name: "发送消息" }));

    await waitFor(() => {
      expect(screen.getByTestId("assistant-md")).toHaveTextContent("员工回复");
    });

    // `staleEmit` is only ever assigned inside the mock closure above, which
    // makes TS narrow it to `never` here; re-widen via the declared type so the
    // optional call type-checks under `tsc --noEmit`.
    const emitStale = staleEmit as ((evt: StreamEvent) => void) | null;
    emitStale?.({
      type: "text_delta",
      task_id: "skill-task",
      delta: "技能创建泄漏",
    });

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByTestId("assistant-md")).toHaveTextContent("员工回复");
    expect(screen.getByTestId("assistant-md")).not.toHaveTextContent(
      "技能创建泄漏",
    );

    releaseStale();
  });
});
