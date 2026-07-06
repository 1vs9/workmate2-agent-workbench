import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { StreamEvent } from "../../api/chatStream";
import ProcessObservability from "./ProcessObservability";

const thinkingEvent: StreamEvent = {
  type: "trace",
  step: "thinking_delta",
  detail: "Planning the response",
};

const toolEvents: StreamEvent[] = [
  {
    type: "trace",
    step: "tool_call_start",
    tool_name: "read_file",
    tool_call_id: "c1",
  },
  {
    type: "trace",
    step: "tool_call_end",
    tool_name: "read_file",
    tool_call_id: "c1",
    detail: '{"path":"D:\\\\proj\\\\MEMORY.md"}',
  },
  {
    type: "trace",
    step: "tool_result_end",
    tool_name: "read_file",
    tool_call_id: "c1",
    detail: "file contents",
    state: "success",
  },
];

describe("ProcessObservability", () => {
  it("renders nothing when there are no trace events", () => {
    const { container } = render(
      <ProcessObservability events={[]} isStreaming={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows a streaming placeholder when there are no trace events yet", () => {
    render(<ProcessObservability events={[]} isStreaming />);
    expect(screen.getByText("执行中…")).toBeInTheDocument();
  });

  it("shows expanded body while streaming", () => {
    render(
      <ProcessObservability events={[thinkingEvent]} isStreaming />,
    );

    const toggle = screen.getByRole("button", { name: /执行中/i });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle.parentElement?.querySelector(".wm-trace-body")).toHaveAttribute(
      "aria-hidden",
      "false",
    );
  });

  it("auto-collapses when streaming stops", () => {
    const { rerender } = render(
      <ProcessObservability events={[thinkingEvent]} isStreaming />,
    );

    rerender(
      <ProcessObservability events={[thinkingEvent]} isStreaming={false} />,
    );

    const toggle = screen.getByRole("button", { name: /过程消息/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    const body = toggle.parentElement?.querySelector(".wm-trace-body");
    expect(body).toHaveAttribute("aria-hidden", "true");
  });

  it("toggles expanded state from the summary header", () => {
    render(
      <ProcessObservability events={[thinkingEvent]} isStreaming={false} />,
    );

    const toggle = screen.getByRole("button", { name: /过程消息/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(toggle.parentElement?.querySelector(".wm-trace-body")).toHaveAttribute(
      "aria-hidden",
      "false",
    );
    expect(screen.getByText("Planning the response")).toBeInTheDocument();

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
  });

  it("shows summary counts and nested thinking section", () => {
    render(
      <ProcessObservability
        events={[...toolEvents, thinkingEvent]}
        isStreaming={false}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /工具调用 1，过程消息 1/i }));

    expect(screen.getByRole("button", { name: /深度思考/i })).toBeInTheDocument();
    expect(screen.getByText("read file")).toBeInTheDocument();
    expect(screen.getByText(/MEMORY\.md/)).toBeInTheDocument();
  });

  it("shows collapsed info repeat count in the process panel", () => {
    const infoEvents: StreamEvent[] = Array.from({ length: 4 }, () => ({
      type: "info",
      label: "继续执行…",
      detail: "模型正在下一轮推理",
    }));
    render(
      <ProcessObservability events={infoEvents} isStreaming={false} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /过程消息 1/i }));
    expect(screen.getByText("继续执行… ×4")).toBeInTheDocument();
    expect(screen.getByText("模型正在下一轮推理")).toBeInTheDocument();
  });
});
