import type { Assignee } from "../types/assignee";

export interface ComposerTaskSnapshot {
  assignee: Assignee;
  skillNames: string[];
  planMode: boolean;
}

const cache = new Map<string, ComposerTaskSnapshot>();

function cloneSnapshot(snapshot: ComposerTaskSnapshot): ComposerTaskSnapshot {
  return {
    assignee: { ...snapshot.assignee },
    skillNames: [...snapshot.skillNames],
    planMode: snapshot.planMode,
  };
}

export function getComposerTaskCache(taskId: string): ComposerTaskSnapshot | undefined {
  const trimmed = taskId.trim();
  if (!trimmed) return undefined;
  const cached = cache.get(trimmed);
  return cached ? cloneSnapshot(cached) : undefined;
}

export function saveComposerTaskCache(
  taskId: string,
  snapshot: ComposerTaskSnapshot,
): void {
  const trimmed = taskId.trim();
  if (!trimmed) return;
  cache.set(trimmed, cloneSnapshot(snapshot));
}

export function removeComposerTaskCache(taskId: string): void {
  const trimmed = taskId.trim();
  if (!trimmed) return;
  cache.delete(trimmed);
}

export function clearComposerTaskCache(): void {
  cache.clear();
}
