import type { NavigateFunction } from "react-router-dom";
import { buildTaskTitle, tasksApi } from "../api/tasks";
import { seedComposerTaskCache } from "./seedComposerTaskCache";

interface OpenChatWithSkillOptions {
  skillName: string;
  /** Human-readable title; falls back to skillName. */
  displayName?: string;
  resetForNewChat: (skillNames?: string[]) => void;
  prependTask: (task: Awaited<ReturnType<typeof tasksApi.create>>) => void;
  setActiveTaskId: (id: string) => void;
  navigate: NavigateFunction;
}

/** Start a new task chat with the given skill pre-selected in the composer. */
export async function openChatWithSkill({
  skillName,
  displayName,
  resetForNewChat,
  prependTask,
  setActiveTaskId,
  navigate,
}: OpenChatWithSkillOptions): Promise<void> {
  const mountedName = skillName.trim();
  if (!mountedName) {
    throw new Error("无法识别已安装的技能名称，请刷新后重试");
  }
  resetForNewChat([mountedName]);
  const titleLabel = (displayName ?? mountedName).trim() || mountedName;
  const created = await tasksApi.create({
    title: buildTaskTitle(`使用 ${titleLabel}`),
  });
  prependTask(created);
  setActiveTaskId(created.id);
  seedComposerTaskCache(created.id);
  navigate(`/task/${created.id}`, { replace: true });
}
