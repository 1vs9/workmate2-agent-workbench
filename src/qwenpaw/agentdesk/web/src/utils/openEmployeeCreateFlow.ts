import type { NavigateFunction } from "react-router-dom";
import { skillsApi } from "../api/skills";
import { buildTaskTitle, tasksApi } from "../api/tasks";
import { seedComposerTaskCache } from "./seedComposerTaskCache";
import {
  EMPLOYEE_CREATE_DRAFT,
  EMPLOYEE_CREATE_MARKER,
  EMPLOYEE_CREATOR_SKILL,
  EMPLOYEE_CREATOR_TAG,
} from "./employeeCreate";

export interface EmployeeCreateComposerState {
  composerDraft: string;
  selectDraftMarker: string;
  skillTag?: string;
}

interface OpenEmployeeCreateFlowOptions {
  resetForNewChat: (skillNames?: string[]) => void;
  prependTask: (task: Awaited<ReturnType<typeof tasksApi.create>>) => void;
  setActiveTaskId: (id: string) => void;
  navigate: NavigateFunction;
}

/** Open task chat with employee-creator skill and a structured creation message. */
export async function openEmployeeCreateFlow({
  resetForNewChat,
  prependTask,
  setActiveTaskId,
  navigate,
}: OpenEmployeeCreateFlowOptions): Promise<void> {
  try {
    await skillsApi.importBuiltin([EMPLOYEE_CREATOR_SKILL]);
  } catch {
    /* may already exist in pool */
  }
  await skillsApi.mountSkill(EMPLOYEE_CREATOR_SKILL, { scope: "agent" });

  resetForNewChat([EMPLOYEE_CREATOR_SKILL]);

  const created = await tasksApi.create({
    title: buildTaskTitle("添加员工"),
  });
  prependTask(created);
  setActiveTaskId(created.id);
  seedComposerTaskCache(created.id);

  const state: EmployeeCreateComposerState = {
    composerDraft: EMPLOYEE_CREATE_DRAFT,
    selectDraftMarker: EMPLOYEE_CREATE_MARKER,
    skillTag: EMPLOYEE_CREATOR_TAG,
  };

  navigate(`/task/${created.id}`, { replace: true, state });
}