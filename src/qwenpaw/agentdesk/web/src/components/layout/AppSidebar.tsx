import { useCallback, useEffect, useMemo, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { probeBackend } from "../../api/health";
import { tasksApi, type Task } from "../../api/tasks";
import { filterTasks, useAppStore } from "../../store/appStore";
import { useComposerStore } from "../../store/composerStore";
import AgentDeskIcon from "../branding/AgentDeskIcon";
import { formatTaskRelativeTime, taskTimestamp } from "../../utils/formatTaskRelativeTime";
import { isTaskRunActive } from "../../utils/taskRunStatus";
import { removeCachedChatState } from "../../utils/taskChatStateCache";
import { removeComposerTaskCache } from "../../utils/composerTaskCache";

const TASK_PREVIEW_COUNT = 10;
const APP_VERSION_SHORT = `v${VITE_AGENTDESK_VERSION || "0.0.0"}`;
const APP_VERSION_TITLE = [
  APP_VERSION_SHORT,
  VITE_AGENTDESK_BUILD ? `build ${VITE_AGENTDESK_BUILD}` : "",
  VITE_AGENTDESK_COMMIT ? `commit ${VITE_AGENTDESK_COMMIT}` : "",
]
  .filter(Boolean)
  .join(" · ");

const NAV_ITEMS = [
  {
    path: "/plaza",
    label: "岗位智能体",
    icon: (
      <svg viewBox="0 0 20 20" fill="none" className="wm-sidebar-icon" aria-hidden="true">
        <path
          d="M10 3l1.4 4.3L15.5 8l-4.1 1.4L10 13.5 8.6 9.4 4.5 8l4.1-1.4L10 3z"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
  {
    path: "/team",
    label: "多智能体团队",
    icon: (
      <svg viewBox="0 0 20 20" fill="none" className="wm-sidebar-icon" aria-hidden="true">
        <path
          d="M7 8.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM13 9.5a2 2 0 100-4 2 2 0 000 4zM2.5 15.5A4.5 4.5 0 017 11h0a4.5 4.5 0 014.5 4.5M10.5 15.5A3.5 3.5 0 0114 12h0a3.5 3.5 0 013.5 3.5"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
  {
    path: "/skills",
    label: "技能市场",
    icon: (
      <svg viewBox="0 0 20 20" fill="none" className="wm-sidebar-icon" aria-hidden="true">
        <path
          d="M7.5 3.5l-1 3-3 1 3 1 1 3 1-3 3-1-3-1-1-3zM14 10l-.8 2.4L11 13l2.2.6L14 16l.8-2.4L17 13l-2.2-.6L14 10z"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
      </svg>
    ),
  },
  {
    path: "/cases",
    label: "案例库",
    icon: (
      <svg viewBox="0 0 20 20" fill="none" className="wm-sidebar-icon" aria-hidden="true">
        <path
          d="M6 4.5h8l1.5 2v9a1 1 0 01-1 1H5.5a1 1 0 01-1-1v-9L6 4.5z"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        <path d="M8 9h4M8 12h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    path: "/mcp",
    label: "MCP 工具",
    icon: (
      <svg viewBox="0 0 20 20" fill="none" className="wm-sidebar-icon" aria-hidden="true">
        <path
          d="M7 7.5h6M7 10.5h4M6 4.5h8a1.5 1.5 0 011.5 1.5v8a1.5 1.5 0 01-1.5 1.5H6A1.5 1.5 0 014.5 14v-8A1.5 1.5 0 016 4.5z"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    ),
  },
  {
    path: "/knowledge",
    label: "资料库",
    icon: (
      <svg viewBox="0 0 20 20" fill="none" className="wm-sidebar-icon" aria-hidden="true">
        <path
          d="M4 6.5A2.5 2.5 0 016.5 4H14v12H6.5A2.5 2.5 0 014 13.5v-7zM14 4h1.5A1.5 1.5 0 0117 5.5v9a1.5 1.5 0 01-1.5 1.5H14"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
      </svg>
    ),
    chevron: true,
  },
  {
    path: "/automation",
    label: "定时任务",
    icon: (
      <svg viewBox="0 0 20 20" fill="none" className="wm-sidebar-icon" aria-hidden="true">
        <circle cx="10" cy="10" r="6.5" stroke="currentColor" strokeWidth="1.5" />
        <path d="M10 6.5V10l2.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    ),
  },
] as const;

function TaskStatusIcon({ running }: { running: boolean }) {
  if (running) {
    return (
      <svg viewBox="0 0 20 20" fill="none" className="wm-sidebar-task-icon wm-sidebar-task-icon--running" aria-hidden="true">
        <circle cx="10" cy="10" r="6.5" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3.5 3.5" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 20 20" fill="none" className="wm-sidebar-task-icon" aria-hidden="true">
      <circle cx="10" cy="10" r="6.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M7 10.2l2 2 4.2-4.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function PinIcon({ pinned }: { pinned?: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      className={`h-3.5 w-3.5 shrink-0 ${pinned ? "text-amber-500" : "text-gray-400"}`}
      aria-hidden="true"
    >
      <path
        d="M10 3.5l1.2 4.2 4.3.6-3.2 2.8.9 4.2L10 13.2l-3.2 2.1.9-4.2-3.2-2.8 4.3-.6L10 3.5z"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
        fill={pinned ? "currentColor" : "none"}
      />
    </svg>
  );
}

interface TaskRowProps {
  task: Task;
  selected: boolean;
  menuOpen: boolean;
  onSelect: () => void;
  onToggleMenu: () => void;
  onTogglePin: () => void;
  onDelete: () => void;
  showPin?: boolean;
}

function TaskRow({
  task,
  selected,
  menuOpen,
  onSelect,
  onToggleMenu,
  onTogglePin,
  onDelete,
  showPin,
}: TaskRowProps) {
  const running = isTaskRunActive(task);
  const pinned = Boolean(task.pinned);
  const timeLabel = formatTaskRelativeTime(taskTimestamp(task));

  return (
    <div className={`wm-sidebar-task-row group ${selected ? "wm-sidebar-task-row--active" : ""}`}>
      <button type="button" onClick={onSelect} className="wm-sidebar-task-row__main" title={task.title}>
        <TaskStatusIcon running={running} />
        <span className="wm-sidebar-task-row__title">{task.title || "未命名任务"}</span>
        {timeLabel ? <span className="wm-sidebar-task-row__time">{timeLabel}</span> : null}
      </button>
      <div className="wm-sidebar-task-row__actions">
        {showPin && pinned ? <PinIcon pinned /> : null}
        <button
          type="button"
          aria-label="任务菜单"
          onClick={(e) => {
            e.stopPropagation();
            onToggleMenu();
          }}
          className="wm-sidebar-task-row__menu"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5" aria-hidden="true">
            <circle cx="4" cy="10" r="1.2" />
            <circle cx="10" cy="10" r="1.2" />
            <circle cx="16" cy="10" r="1.2" />
          </svg>
        </button>
      </div>
      {menuOpen ? (
        <div className="wm-sidebar-task-menu">
          <button type="button" className="wm-sidebar-task-menu__item" onClick={onTogglePin}>
            {pinned ? "取消置顶" : "置顶"}
          </button>
          <button type="button" className="wm-sidebar-task-menu__item wm-sidebar-task-menu__item--danger" onClick={onDelete}>
            删除
          </button>
        </div>
      ) : null}
    </div>
  );
}

export default function AppSidebar() {
  const navigate = useNavigate();
  const location = useLocation();

  const tasks = useAppStore((s) => s.tasks);
  const taskSearch = useAppStore((s) => s.taskSearch);
  const tasksExpanded = useAppStore((s) => s.tasksExpanded);
  const apiOnline = useAppStore((s) => s.apiOnline);
  const activeTaskId = useAppStore((s) => s.activeTaskId);
  const setTaskSearch = useAppStore((s) => s.setTaskSearch);
  const setTasksExpanded = useAppStore((s) => s.setTasksExpanded);
  const setActiveTaskId = useAppStore((s) => s.setActiveTaskId);
  const setApiOnline = useAppStore((s) => s.setApiOnline);
  const loadTasks = useAppStore((s) => s.loadTasks);
  const removeTask = useAppStore((s) => s.removeTask);
  const setTaskPinned = useAppStore((s) => s.setTaskPinned);
  const resetForNewChat = useComposerStore((s) => s.resetForNewChat);

  const [menuTaskId, setMenuTaskId] = useState<string | null>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [taskListExpanded, setTaskListExpanded] = useState(false);

  const filteredTasks = useMemo(
    () => filterTasks(tasks, taskSearch),
    [tasks, taskSearch],
  );

  const pinnedTasks = useMemo(
    () => filteredTasks.filter((task) => Boolean(task.pinned)),
    [filteredTasks],
  );

  const regularTasks = useMemo(
    () => filteredTasks.filter((task) => !task.pinned),
    [filteredTasks],
  );

  const visibleRegularTasks = taskListExpanded
    ? regularTasks
    : regularTasks.slice(0, TASK_PREVIEW_COUNT);
  const hiddenTaskCount = Math.max(0, regularTasks.length - TASK_PREVIEW_COUNT);

  const probe = useCallback(async () => {
    const result = await probeBackend();
    setApiOnline(result.ok);
  }, [setApiOnline]);

  const deleteTask = async (id: string) => {
    if (!window.confirm("确认删除该任务？将中止运行中的任务并清除会话文件。")) return;
    try {
      await tasksApi.delete(id);
      removeTask(id);
      removeCachedChatState(id);
      removeComposerTaskCache(id);
      setMenuTaskId(null);
      if (activeTaskId === id) {
        setActiveTaskId(null);
        navigate("/");
      }
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "删除失败");
    }
  };

  const togglePin = async (id: string) => {
    const task = tasks.find((t) => t.id === id);
    if (!task) return;
    const nextPinned = !task.pinned;
    setMenuTaskId(null);
    setTaskPinned(id, nextPinned);
    try {
      await tasksApi.update(id, { pinned: nextPinned });
    } catch (err) {
      setTaskPinned(id, !nextPinned);
      window.alert(err instanceof Error ? err.message : "置顶失败");
    }
  };

  const openTask = (id: string) => {
    setActiveTaskId(id);
    setMenuTaskId(null);
    navigate(`/task/${id}`);
  };

  useEffect(() => {
    void probe();
    void loadTasks().catch(() => setApiOnline(false));
  }, [probe, loadTasks, setApiOnline]);

  const isHome = location.pathname === "/";
  const isTaskRoute = location.pathname.startsWith("/task/");

  const renderTaskList = (list: Task[], showPin?: boolean) =>
    list.map((task) => (
      <TaskRow
        key={task.id}
        task={task}
        selected={activeTaskId === task.id && isTaskRoute}
        menuOpen={menuTaskId === task.id}
        showPin={showPin}
        onSelect={() => openTask(task.id)}
        onToggleMenu={() => setMenuTaskId((id) => (id === task.id ? null : task.id))}
        onTogglePin={() => void togglePin(task.id)}
        onDelete={() => void deleteTask(task.id)}
      />
    ));

  return (
    <aside className="wm-sidebar">
      <div className="wm-sidebar__header">
        <div className="wm-sidebar__brand">
          <AgentDeskIcon size={24} aria-hidden />
          <div className="wm-sidebar__brand-text">
            <span className="wm-sidebar__brand-title">
              <span className="wm-sidebar__brand-name">AgentDesk企伴</span>
              <span className="wm-sidebar__brand-version" title={APP_VERSION_TITLE}>
                {APP_VERSION_SHORT}
              </span>
            </span>
          </div>
          {apiOnline === true ? (
            <span className="wm-sidebar__status-dot" title="后端已连接" aria-label="后端已连接" />
          ) : null}
          {apiOnline === false ? (
            <button
              type="button"
              className="wm-sidebar__status wm-sidebar__status--offline"
              onClick={() => void probe()}
              title="后端未连接，点击重试"
            >
              离线
            </button>
          ) : null}
        </div>
        <button
          type="button"
          aria-label={searchOpen ? "关闭搜索" : "搜索任务"}
          className="wm-sidebar__search-toggle"
          onClick={() => setSearchOpen((v) => !v)}
        >
          <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4" aria-hidden="true">
            <path
              d="M13.5 13.5L17 17M15.5 9a6.5 6.5 0 11-13 0 6.5 6.5 0 0113 0z"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
        </button>
      </div>

      {searchOpen ? (
        <div className="wm-sidebar__search">
          <input
            type="search"
            value={taskSearch}
            onChange={(e) => setTaskSearch(e.target.value)}
            placeholder="搜索任务"
            aria-label="搜索任务"
            className="wm-sidebar__search-input"
            autoFocus
          />
        </div>
      ) : null}

      <button
        type="button"
        onClick={() => {
          setActiveTaskId(null);
          resetForNewChat();
          navigate("/");
        }}
        className={`wm-sidebar-new-task ${isHome ? "wm-sidebar-new-task--active" : ""}`}
      >
        <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4 shrink-0" aria-hidden="true">
          <path d="M10 4v12M4 10h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        <span>新建任务</span>
      </button>

      <nav className="wm-sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              ["wm-nav-link", isActive && !isHome && !isTaskRoute ? "wm-nav-active" : ""]
                .filter(Boolean)
                .join(" ")
            }
            onClick={() => setActiveTaskId(null)}
          >
            {item.icon}
            <span className="wm-sidebar-nav__label">{item.label}</span>
            {"chevron" in item && item.chevron ? (
              <svg viewBox="0 0 20 20" fill="none" className="wm-sidebar-nav__chevron" aria-hidden="true">
                <path d="M5 8l5 5 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            ) : null}
          </NavLink>
        ))}
      </nav>

      <div className="wm-sidebar__sections">
        {pinnedTasks.length > 0 ? (
          <section className="wm-sidebar-section">
            <h2 className="wm-sidebar-section__title">置顶任务</h2>
            <div className="wm-sidebar-scroll">{renderTaskList(pinnedTasks, true)}</div>
          </section>
        ) : null}

        <section className="wm-sidebar-section wm-sidebar-section--grow">
          <button
            type="button"
            onClick={() => setTasksExpanded(!tasksExpanded)}
            className="wm-sidebar-section__title wm-sidebar-section__title--toggle"
          >
            <span>任务</span>
            <svg
              viewBox="0 0 20 20"
              fill="none"
              className={`wm-sidebar-section__chevron ${tasksExpanded ? "" : "wm-sidebar-section__chevron--collapsed"}`}
              aria-hidden="true"
            >
              <path d="M5 8l5 5 5-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>

          {tasksExpanded ? (
            <div className="wm-sidebar-scroll">
              {filteredTasks.length === 0 ? (
                <p className="wm-sidebar-empty">暂无任务</p>
              ) : (
                <>
                  {renderTaskList(visibleRegularTasks)}
                  {hiddenTaskCount > 0 && !taskListExpanded ? (
                    <button
                      type="button"
                      className="wm-sidebar-expand"
                      onClick={() => setTaskListExpanded(true)}
                    >
                      展开更多 ({hiddenTaskCount})
                    </button>
                  ) : null}
                  {taskListExpanded && hiddenTaskCount > 0 ? (
                    <button
                      type="button"
                      className="wm-sidebar-expand"
                      onClick={() => setTaskListExpanded(false)}
                    >
                      收起
                    </button>
                  ) : null}
                </>
              )}
            </div>
          ) : null}
        </section>
      </div>

      <footer className="wm-sidebar-footer">
        <button type="button" onClick={() => navigate("/settings")} className="wm-sidebar-profile">
          <span className="wm-sidebar-profile__avatar" aria-hidden="true">
            树
          </span>
          <span className="wm-sidebar-profile__name">一棵树</span>
          <svg viewBox="0 0 20 20" fill="none" className="wm-sidebar-profile__chevron" aria-hidden="true">
            <path d="M8 5l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </footer>
    </aside>
  );
}
