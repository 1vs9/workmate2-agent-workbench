import { vi } from "vitest";

vi.mock("@agentscope-ai/design", () => ({
  bailianTheme: { theme: {} },
  bailianDarkTheme: { theme: {} },
  ConfigProvider: ({ children }: { children?: React.ReactNode }) => children,
}));

// Capture the options passed to AgentScopeRuntimeWebUI so we can exercise
// customFetch without the heavy real component.
let capturedOptions: Record<string, unknown> | null = null;
vi.mock("@agentscope-ai/chat", async () => {
  const React = await import("react");
  return {
    AgentScopeRuntimeWebUI: (props: { options: Record<string, unknown> }) => {
      capturedOptions = props.options;
      return React.createElement("div", { "data-testid": "chat-ui" });
    },
  };
});

import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { ThemeProvider } from "../../theme/ThemeContext";
import { MemoryRouter } from "react-router-dom";
import ChatPage from "./index";

function renderChat() {
  return render(
    <ThemeProvider>
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe("ChatPage", () => {
  beforeEach(() => {
    capturedOptions = null;
  });

  it("renders the chat UI", () => {
    renderChat();
    expect(screen.getByTestId("chat-ui")).toBeInTheDocument();
  });

  it("customFetch posts to /api/console/chat with stream body", async () => {
    renderChat();

    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}"));

    const api = (capturedOptions as { api: { fetch: Function } }).api;
    await api.fetch({
      input: [
        {
          role: "user",
          content: [{ type: "text", text: "hello" }],
          session: { session_id: "s1", user_id: "u1", channel: "console" },
        },
      ],
    });

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(String(url)).toContain("/api/console/chat");
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body.stream).toBe(true);
    expect(body.session_id).toBe("s1");
    expect(body.input[0].role).toBe("user");

    fetchSpy.mockRestore();
  });
});
