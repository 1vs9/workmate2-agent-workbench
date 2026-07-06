import type { ChatStreamBody } from "../api/chatStream";
import type { Team } from "../api/teams";
import type { Assignee } from "../types/assignee";
import { isCasualChatMessage } from "./casualChat";
import {
  isSkillCreateMessage,
  isSkillFindMessage,
  SKILL_CREATOR_SKILL,
} from "./skillCreate";

export interface BuildChatPayloadOptions {
  taskId: string;
  message: string;
  assignee: Assignee;
  skillNames: string[];
  planMode: boolean;
  teams?: Team[];
  reconnect?: boolean;
  forcePlan?: boolean;
  teamMember?: string;
}

export function buildChatPayload(
  options: BuildChatPayloadOptions,
): ChatStreamBody {
  const {
    taskId,
    message,
    assignee,
    skillNames,
    planMode,
    teams = [],
    reconnect = false,
    forcePlan = false,
    teamMember,
  } = options;

  const useTeam = assignee.type === "team";
  const usePlan = (forcePlan || planMode) && !useTeam;

  const payload: ChatStreamBody = {
    task_id: taskId,
    message,
    reconnect,
    mode: useTeam ? "team" : "single",
    chat_mode: usePlan ? "plan" : "chat",
  };

  if (useTeam) {
    const team =
      teams.find((t) => t.id === assignee.teamId) ||
      teams.find((t) => t.name === assignee.name);
    payload.team_id = assignee.teamId || team?.id;
    payload.team_name = assignee.name;
    if (teamMember?.trim()) {
      payload.team_member = teamMember.trim();
    }
  } else if (assignee.type === "employee") {
    payload.employee_name = assignee.name;
  }

  const skillCreateIntent =
    !reconnect &&
    !isCasualChatMessage(message) &&
    !isSkillFindMessage(message) &&
    isSkillCreateMessage(message);

  const routedSkillNames =
    skillCreateIntent || isCasualChatMessage(message)
      ? skillNames
      : skillNames.filter((name) => name !== SKILL_CREATOR_SKILL);

  if (routedSkillNames.length && !isCasualChatMessage(message)) {
    payload.skill_names = [...routedSkillNames];
  }

  if (skillCreateIntent && !useTeam) {
    payload.intent = "skill_create";
    payload.wizard_action = "start";
  }

  return payload;
}
