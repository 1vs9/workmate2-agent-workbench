import { saveComposerTaskCache } from "./composerTaskCache";
import { readComposerSnapshot } from "./hydrateComposerFromTask";

/** Persist the current composer toolbar state for a task before navigation. */
export function seedComposerTaskCache(taskId: string): void {
  const trimmed = taskId.trim();
  if (!trimmed) return;
  saveComposerTaskCache(trimmed, readComposerSnapshot());
}
