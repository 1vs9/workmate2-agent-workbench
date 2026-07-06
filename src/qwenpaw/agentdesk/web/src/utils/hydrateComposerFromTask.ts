import type { Task } from "../api/tasks";
import type { Team } from "../api/teams";
import { useComposerStore } from "../store/composerStore";
import {
  buildTeamAssignee,
  getDefaultAssignee,
  type Assignee,
} from "../types/assignee";
import type { ComposerTaskSnapshot } from "./composerTaskCache";

export function resolveTaskAssignee(
  task: Task | null,
  teams: Team[],
  fallback: Assignee,
): Assignee {
  if (!task) return fallback;
  const mode = String(task.mode ?? "").trim().toLowerCase();
  const teamId = String(task.team_id ?? task.teamId ?? "").trim();
  const teamName = String(task.team_name ?? task.teamName ?? "").trim();
  const employeeName = String(task.employee_name ?? task.employeeName ?? "").trim();

  if (mode === "team" || teamId || teamName) {
    const team =
      teams.find((item) => item.id === teamId) ||
      teams.find((item) => item.name === teamName);
    if (team) return buildTeamAssignee(team);
    return {
      type: "team",
      name: teamName || fallback.name,
      teamId: teamId || undefined,
      subtitle: fallback.subtitle,
      avatar: fallback.avatar,
    };
  }

  if (employeeName) {
    return {
      type: "employee",
      name: employeeName,
      agentId: employeeName,
      subtitle: fallback.subtitle,
      avatar: fallback.avatar,
    };
  }

  return fallback;
}

function taskHasRoutingMetadata(task: Task): boolean {
  const mode = String(task.mode ?? "").trim().toLowerCase();
  const teamId = String(task.team_id ?? task.teamId ?? "").trim();
  const teamName = String(task.team_name ?? task.teamName ?? "").trim();
  const employeeName = String(task.employee_name ?? task.employeeName ?? "").trim();
  // A persisted ``mode`` (even plain "single") means the task is already bound
  // to a target. Opening it must reset the composer to that binding so a team
  // selected in a previous task does not leak in and route the next message to
  // the wrong recipient (which flips the task to team and crosses threads).
  return (
    mode === "team" ||
    mode === "single" ||
    Boolean(teamId || teamName || employeeName)
  );
}

function readTaskSkillNames(task: Task): string[] {
  const raw = task.skill_names;
  if (!Array.isArray(raw)) return [];
  return raw.map((name) => String(name).trim()).filter(Boolean);
}

/** Apply persisted task routing/skills to the global composer when present. */
export function hydrateComposerFromTask(task: Task, teams: Team[]): void {
  const { setAssignee, setSkillNames } = useComposerStore.getState();

  if (taskHasRoutingMetadata(task)) {
    setAssignee(resolveTaskAssignee(task, teams, getDefaultAssignee()));
  }

  const skillNames = readTaskSkillNames(task);
  if (skillNames.length > 0) {
    setSkillNames(skillNames);
  }
}

export function readComposerSnapshot(): ComposerTaskSnapshot {
  const { assignee, skillNames, planMode } = useComposerStore.getState();
  return { assignee, skillNames, planMode };
}
