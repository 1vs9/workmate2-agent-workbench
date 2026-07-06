import type { StreamEvent } from "../api/chatStream";

/** Only fatal stream errors should tear down the active run UI. */
export function isFatalStreamError(evt: StreamEvent): boolean {
  if (String(evt.type || "") !== "error") return false;
  if (evt.fatal === false) return false;
  return true;
}
