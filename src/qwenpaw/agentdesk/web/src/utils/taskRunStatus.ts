import type { Task } from "../api/tasks";
import type { ChatTurn } from "./chatStreamReducer";
import { isLeaderAssistantTurn } from "./sanitizeMemberSession";
import type { Team } from "../api/teams";

/** Normalize backend runStatus / run_status for UI decisions. */
export function resolveTaskRunStatus(task: Task | null | undefined): string {
  if (!task) return "idle";
  const raw = task.runStatus ?? task.run_status;
  return String(raw || "idle").toLowerCase();
}

export function isTaskRunActive(task: Task | null | undefined): boolean {
  return resolveTaskRunStatus(task) === "running";
}

/** True when team member bubbles are still streaming (worker not done). */
export function hasStreamingTeamWorkers(
  turns: ChatTurn[],
  team: Team | null | undefined,
): boolean {
  return turns.some(
    (turn) =>
      turn.role === "assistant" &&
      turn.streaming &&
      Boolean(turn.name?.trim()) &&
      !isLeaderAssistantTurn(turn.name, team ?? null),
  );
}

/** True while the agent may still be executing (local SSE or backend runStatus). */
export function isAgentRunning(
  task: Task | null | undefined,
  streamConnected: boolean,
  reconnecting = false,
  teamTurns: ChatTurn[] = [],
  team: Team | null | undefined = null,
): boolean {
  return (
    streamConnected ||
    reconnecting ||
    isTaskRunActive(task) ||
    hasStreamingTeamWorkers(teamTurns, team)
  );
}
