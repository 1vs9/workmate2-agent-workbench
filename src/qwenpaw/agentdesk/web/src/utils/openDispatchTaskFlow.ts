import type { NavigateFunction } from "react-router-dom";
import { buildTaskTitle, tasksApi } from "../api/tasks";
import { getAssigneeLabel, type Assignee } from "../types/assignee";
import { seedComposerTaskCache } from "./seedComposerTaskCache";

interface OpenDispatchTaskFlowOptions {
  assignee: Assignee;
  resetForNewChat: (skillNames?: string[], assignee?: Assignee) => void;
  prependTask: (task: Awaited<ReturnType<typeof tasksApi.create>>) => void;
  setActiveTaskId: (id: string) => void;
  navigate: NavigateFunction;
}

/** Start a new task chat with the given employee or team as assignee. */
export async function openDispatchTaskFlow({
  assignee,
  resetForNewChat,
  prependTask,
  setActiveTaskId,
  navigate,
}: OpenDispatchTaskFlowOptions): Promise<void> {
  resetForNewChat([], assignee);

  const titleLabel = getAssigneeLabel(assignee);
  const created = await tasksApi.create({
    title: buildTaskTitle(`派发 · ${titleLabel}`),
  });
  prependTask(created);
  setActiveTaskId(created.id);
  seedComposerTaskCache(created.id);
  navigate(`/task/${created.id}`, { replace: true });
}
