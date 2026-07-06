import { describe, expect, it, beforeEach } from "vitest";

import type { ChatStreamState } from "./chatStreamReducer";
import {
  clearTaskChatStateCache,
  getCachedChatState,
  setCachedChatState,
} from "./taskChatStateCache";

function stateWithTurn(text = "partial answer"): ChatStreamState {
  return {
    streamActive: true,
    activeActorId: "assistant",
    activeTurnId: "live:assistant:assistant",
    turns: [
      {
        id: "u1",
        role: "user",
        name: "You",
        avatarKind: "user",
        text: "hello",
        traceEvents: [],
        streaming: false,
      },
      {
        id: "live:assistant:assistant",
        role: "assistant",
        name: "AgentDesk企伴",
        avatarKind: "assistant",
        text,
        traceEvents: [{ type: "thinking_start", message_id: "live:assistant:assistant" }],
        streaming: true,
      },
    ],
  };
}

describe("taskChatStateCache", () => {
  beforeEach(() => {
    clearTaskChatStateCache();
  });

  it("restores cached task transcript after the in-memory cache is cleared", () => {
    setCachedChatState("task-1", stateWithTurn());

    // Simulates a page refresh: module memory is gone, but sessionStorage stays.
    clearTaskChatStateCache({ storage: false });

    const restored = getCachedChatState("task-1");
    expect(restored?.turns.map((turn) => turn.text)).toEqual([
      "hello",
      "partial answer",
    ]);
    expect(restored?.streamActive).toBe(true);
  });

  it("does not let an empty state erase a persisted transcript", () => {
    setCachedChatState("task-1", stateWithTurn("keep me"));

    setCachedChatState("task-1", { turns: [], streamActive: false });

    expect(getCachedChatState("task-1")?.turns[1]?.text).toBe("keep me");
  });
});
