import {
  createChatStreamState,
  type ChatStreamState,
} from "./chatStreamReducer";

const cache = new Map<string, ChatStreamState>();
const STORAGE_PREFIX = "agentdesk:task-chat-state:";

interface ClearTaskChatStateCacheOptions {
  storage?: boolean;
}

function cloneState(state: ChatStreamState): ChatStreamState {
  return {
    ...state,
    turns: state.turns.map((turn) => ({
      ...turn,
      traceEvents: [...turn.traceEvents],
    })),
  };
}

function storageKey(taskId: string): string {
  return `${STORAGE_PREFIX}${taskId}`;
}

function getSessionStorage(): Storage | undefined {
  if (typeof window === "undefined") return undefined;
  try {
    return window.sessionStorage;
  } catch {
    return undefined;
  }
}

function readStoredState(taskId: string): ChatStreamState | undefined {
  const storage = getSessionStorage();
  if (!storage) return undefined;
  try {
    const raw = storage.getItem(storageKey(taskId));
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as Partial<ChatStreamState> | null;
    if (!parsed || !Array.isArray(parsed.turns)) return undefined;
    return cloneState({
      ...createChatStreamState(),
      ...parsed,
      turns: parsed.turns as ChatStreamState["turns"],
      streamActive: Boolean(parsed.streamActive),
    });
  } catch {
    storage.removeItem(storageKey(taskId));
    return undefined;
  }
}

function writeStoredState(taskId: string, state: ChatStreamState): void {
  const storage = getSessionStorage();
  if (!storage) return;
  try {
    storage.setItem(storageKey(taskId), JSON.stringify(cloneState(state)));
  } catch {
    /* Ignore quota/private-mode failures; the in-memory cache still works. */
  }
}

function removeStoredState(taskId: string): void {
  const storage = getSessionStorage();
  if (!storage) return;
  storage.removeItem(storageKey(taskId));
}

function clearStoredStates(): void {
  const storage = getSessionStorage();
  if (!storage) return;
  for (let i = storage.length - 1; i >= 0; i -= 1) {
    const key = storage.key(i);
    if (key?.startsWith(STORAGE_PREFIX)) storage.removeItem(key);
  }
}

export function getCachedChatState(taskId: string): ChatStreamState | undefined {
  const trimmed = taskId.trim();
  if (!trimmed) return undefined;
  const cached = cache.get(trimmed);
  if (cached) return cloneState(cached);
  const stored = readStoredState(trimmed);
  if (!stored) return undefined;
  cache.set(trimmed, cloneState(stored));
  return stored;
}

export function setCachedChatState(taskId: string, state: ChatStreamState): void {
  const trimmed = taskId.trim();
  if (!trimmed) return;
  if (!state.turns.length && !state.streamActive) {
    cache.delete(trimmed);
    return;
  }
  const snapshot = cloneState(state);
  cache.set(trimmed, snapshot);
  writeStoredState(trimmed, snapshot);
}

export function restoreCachedChatState(taskId: string): ChatStreamState {
  return getCachedChatState(taskId) ?? createChatStreamState();
}

export function removeCachedChatState(taskId: string): void {
  const trimmed = taskId.trim();
  if (!trimmed) return;
  cache.delete(trimmed);
  removeStoredState(trimmed);
}

export function clearTaskChatStateCache(
  options: ClearTaskChatStateCacheOptions = {},
): void {
  cache.clear();
  if (options.storage !== false) clearStoredStates();
}
