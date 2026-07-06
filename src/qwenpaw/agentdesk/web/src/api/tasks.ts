import { request } from "./request";

import type { StreamEvent } from "./chatStream";

export interface TaskMessage {
  role?: string;
  content?: string | unknown;
  sender?: string;
  id?: string;
  sessionId?: string;
  session_id?: string;
  traceEvents?: StreamEvent[];
  [key: string]: unknown;
}

export interface Task {
  id: string;
  title: string;
  createdAt?: number;
  created_at?: number;
  messages?: TaskMessage[];
  runStatus?: string;
  /** @deprecated Prefer camelCase runStatus from API */
  run_status?: string;
  skill_names?: string[];
  pinned?: boolean;
  [key: string]: unknown;
}

export interface TaskEvent {
  type: string;
  [key: string]: unknown;
}

export interface WorkspaceNode {
  name: string;
  path: string;
  type: "file" | "dir";
  children?: WorkspaceNode[];
}

export interface WorkspaceFileEntry {
  path: string;
}

export interface WorkspaceFilePreview {
  path: string;
  content: string;
  lines?: string[];
  binary?: boolean;
}

export interface QueueItem {
  id: string;
  message: string;
  [key: string]: unknown;
}

export interface TaskPlan {
  status?: string;
  tasks?: unknown[];
  [key: string]: unknown;
}

export function buildTaskTitle(text: string): string {
  const trimmed = text.trim().replace(/\s+/g, " ");
  if (!trimmed) return "新任务";
  if (trimmed.length <= 28) return trimmed;
  return `${trimmed.slice(0, 28)}…`;
}

export const tasksApi = {
  list: () => request<Task[]>("/tasks"),
  get: (id: string) => request<Task>(`/tasks/${encodeURIComponent(id)}`),
  create: (body: { title?: string; id?: string; workspace_dir?: string }) =>
    request<Task>("/tasks", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (id: string, body: { title?: string; pinned?: boolean }) =>
    request<Task>(`/tasks/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  delete: (id: string) =>
    request<void>(`/tasks/${encodeURIComponent(id)}`, { method: "DELETE" }),
  stop: (id: string) =>
    request<void>(`/tasks/${encodeURIComponent(id)}/stop`, { method: "POST" }),
  getEvents: (id: string) =>
    request<TaskEvent[]>(`/tasks/${encodeURIComponent(id)}/events`),
  getStats: (id: string) =>
    request<Record<string, unknown>>(`/tasks/${encodeURIComponent(id)}/stats`),
  getWorkspaceTree: async (taskId: string) => {
    const data = await request<
      WorkspaceNode[] | { files?: WorkspaceFileEntry[] }
    >(`/tasks/${encodeURIComponent(taskId)}/workspace/tree`);
    if (Array.isArray(data)) return data;
    const files = data?.files ?? [];
    return files.map((entry) => {
      const path = entry.path;
      const name = path.split("/").pop() || path;
      return { name, path, type: "file" as const };
    });
  },
  getWorkspaceFiles: async (taskId: string): Promise<string[]> => {
    const data = await request<{ files?: WorkspaceFileEntry[] }>(
      `/tasks/${encodeURIComponent(taskId)}/workspace/tree`,
    );
    return (data.files ?? []).map((entry) => entry.path);
  },
  getWorkspaceFile: (taskId: string, filePath: string) =>
    request<WorkspaceFilePreview>(
      `/tasks/${encodeURIComponent(taskId)}/workspace/file?path=${encodeURIComponent(filePath)}`,
    ),
  revealWorkspacePath: (taskId: string, filePath: string) =>
    request<void>(`/tasks/${encodeURIComponent(taskId)}/workspace/reveal`, {
      method: "POST",
      body: JSON.stringify({ path: filePath }),
    }),
  previewContextBudget: (
    taskId: string,
    body: Record<string, unknown>,
  ) =>
    request<Record<string, unknown>>(
      `/tasks/${encodeURIComponent(taskId)}/context/budget`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  getQueue: (taskId: string) =>
    request<QueueItem[]>(`/tasks/${encodeURIComponent(taskId)}/queue`),
  updateQueueItem: (taskId: string, itemId: string, message: string) =>
    request<QueueItem>(
      `/tasks/${encodeURIComponent(taskId)}/queue/${encodeURIComponent(itemId)}`,
      { method: "PUT", body: JSON.stringify({ message }) },
    ),
  deleteQueueItem: (taskId: string, itemId: string) =>
    request<void>(
      `/tasks/${encodeURIComponent(taskId)}/queue/${encodeURIComponent(itemId)}`,
      { method: "DELETE" },
    ),
  reorderQueue: (taskId: string, ids: string[]) =>
    request<void>(`/tasks/${encodeURIComponent(taskId)}/queue/reorder`, {
      method: "POST",
      body: JSON.stringify({ ids }),
    }),
  getPlan: (taskId: string) =>
    request<TaskPlan>(`/tasks/${encodeURIComponent(taskId)}/plan`),
  confirmPlan: (taskId: string, action: string) =>
    request<TaskPlan>(
      `/tasks/${encodeURIComponent(taskId)}/plan/confirm`,
      { method: "POST", body: JSON.stringify({ action }) },
    ),
};
