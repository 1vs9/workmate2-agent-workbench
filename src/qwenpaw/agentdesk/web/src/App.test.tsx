import { vi } from "vitest";

vi.mock("@agentscope-ai/design", () => ({
  bailianTheme: { theme: {} },
  bailianDarkTheme: { theme: {} },
  ConfigProvider: ({ children }: { children?: React.ReactNode }) => children,
}));

vi.mock("@agentscope-ai/chat", async () => {
  const React = await import("react");
  return {
    AgentScopeRuntimeWebUI: () =>
      React.createElement("div", { "data-testid": "chat-ui" }),
  };
});

vi.mock("./api/health", () => ({
  probeBackend: vi.fn().mockResolvedValue({ ok: true }),
}));

vi.mock("./api/tasks", () => ({
  buildTaskTitle: (t: string) => t.slice(0, 28) || "新任务",
  tasksApi: {
    list: vi.fn().mockResolvedValue([]),
    get: vi.fn(),
    create: vi.fn(),
    delete: vi.fn(),
    stop: vi.fn(),
  },
}));

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import App from "./App";

describe("App", () => {
  it("renders the legacy-style home at the default route", () => {
    render(<App />);
    expect(screen.getByText(/Claw Your Ideas Into/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "新建任务" })).toBeInTheDocument();
  });
});
