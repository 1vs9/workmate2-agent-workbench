/**
 * Stub for @agentscope-ai/chat in tests.
 * The real package is large and can OOM/hang vitest workers.
 */
import { vi } from "vitest";
import React from "react";

export const AgentScopeRuntimeWebUI = vi.fn(() =>
  React.createElement("div", { "data-testid": "chat-ui" }),
);
export const useChatAnywhereInput = vi.fn(() => ({
  setLoading: vi.fn(),
  getLoading: vi.fn(),
}));

export default AgentScopeRuntimeWebUI;
