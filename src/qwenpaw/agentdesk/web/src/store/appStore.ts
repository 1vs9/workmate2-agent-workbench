import { create } from "zustand";
import { tasksApi, type Task } from "../api/tasks";

function sortTasks(tasks: Task[]): Task[] {
  return [...tasks].sort((a, b) => {
    const ta = taskSortValue(a);
    const tb = taskSortValue(b);
    return tb - ta;
  });
}

function taskSortValue(task: Task): number {
  const raw = task.createdAt ?? task.created_at ?? task.updated_at ?? 0;
  const n = Number(raw);
  if (!Number.isFinite(n)) return 0;
  return n < 1e12 ? n : n / 1000;
}

interface AppState {
  tasks: Task[];
  activeTaskId: string | null;
  apiOnline: boolean | null;
  taskSearch: string;
  tasksExpanded: boolean;
  setTaskSearch: (value: string) => void;
  setTasksExpanded: (value: boolean) => void;
  setActiveTaskId: (id: string | null) => void;
  setApiOnline: (ok: boolean) => void;
  loadTasks: () => Promise<void>;
  prependTask: (task: Task) => void;
  updateTask: (task: Task) => void;
  setTaskPinned: (id: string, pinned: boolean) => void;
  removeTask: (id: string) => void;
}

export const useAppStore = create<AppState>((set) => ({
  tasks: [],
  activeTaskId: null,
  apiOnline: null,
  taskSearch: "",
  tasksExpanded: true,
  setTaskSearch: (taskSearch) => set({ taskSearch }),
  setTasksExpanded: (tasksExpanded) => set({ tasksExpanded }),
  setActiveTaskId: (activeTaskId) =>
    set((state) =>
      state.activeTaskId === activeTaskId ? state : { activeTaskId },
    ),
  setApiOnline: (ok) => set({ apiOnline: ok }),
  loadTasks: async () => {
    const tasks = await tasksApi.list();
    set({ tasks: sortTasks(tasks) });
  },
  prependTask: (task) =>
    set((state) => ({
      tasks: sortTasks([task, ...state.tasks.filter((t) => t.id !== task.id)]),
    })),
  updateTask: (task) =>
    set((state) => {
      const idx = state.tasks.findIndex((t) => t.id === task.id);
      if (idx < 0) return state;
      const merged = { ...state.tasks[idx], ...task };
      const prev = state.tasks[idx];
      const runStatus = merged.runStatus ?? merged.run_status;
      const prevRunStatus = prev.runStatus ?? prev.run_status;
      if (
        merged.title === prev.title &&
        runStatus === prevRunStatus &&
        (merged.messages ?? []).length === (prev.messages ?? []).length
      ) {
        return state;
      }
      const next = state.tasks.map((t, i) => (i === idx ? merged : t));
      return { tasks: sortTasks(next) };
    }),
  setTaskPinned: (id, pinned) =>
    set((state) => {
      const idx = state.tasks.findIndex((t) => t.id === id);
      if (idx < 0 || Boolean(state.tasks[idx].pinned) === pinned) return state;
      const next = state.tasks.map((t, i) =>
        i === idx ? { ...t, pinned } : t,
      );
      return { tasks: next };
    }),
  removeTask: (id) =>
    set((state) => ({
      tasks: state.tasks.filter((t) => t.id !== id),
      activeTaskId: state.activeTaskId === id ? null : state.activeTaskId,
    })),
}));

export function filterTasks(tasks: Task[], query: string): Task[] {
  const q = query.trim().toLowerCase();
  if (!q) return tasks;
  return tasks.filter((t) => (t.title || "").toLowerCase().includes(q));
}
