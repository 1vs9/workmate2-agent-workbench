import type { NavigateFunction } from "react-router-dom";
import { buildTaskTitle, tasksApi } from "../api/tasks";
import { seedComposerTaskCache } from "./seedComposerTaskCache";
import {
  SKILL_CREATE_DRAFT,
  SKILL_DRAFT_MARKER,
  SKILL_FIND_DRAFT,
} from "./skillCreate";

export type SkillTaskFlowKind = "find" | "create";

export interface SkillTaskComposerState {
  composerDraft: string;
  selectDraftMarker: string;
  skillTag?: string;
}

interface OpenSkillTaskFlowOptions {
  kind: SkillTaskFlowKind;
  resetForNewChat: (skillNames?: string[]) => void;
  prependTask: (task: Awaited<ReturnType<typeof tasksApi.create>>) => void;
  setActiveTaskId: (id: string) => void;
  navigate: NavigateFunction;
}

/** Start a new task chat with a prefilled skill find/create draft. */
export async function openSkillTaskFlow({
  kind,
  resetForNewChat,
  prependTask,
  setActiveTaskId,
  navigate,
}: OpenSkillTaskFlowOptions): Promise<void> {
  const isCreate = kind === "create";
  resetForNewChat(isCreate ? ["make-skill"] : []);

  const title = isCreate ? "技能创建" : "技能查找";
  const composerDraft = isCreate ? SKILL_CREATE_DRAFT : SKILL_FIND_DRAFT;

  const created = await tasksApi.create({ title: buildTaskTitle(title) });
  prependTask(created);
  setActiveTaskId(created.id);
  seedComposerTaskCache(created.id);

  const state: SkillTaskComposerState = {
    composerDraft,
    selectDraftMarker: SKILL_DRAFT_MARKER,
    ...(isCreate ? { skillTag: "skill-creator" } : {}),
  };

  navigate(`/task/${created.id}`, { replace: true, state });
}
