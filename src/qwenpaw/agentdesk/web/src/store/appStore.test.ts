import { beforeEach, describe, expect, it } from "vitest";
import { useAppStore } from "./appStore";

describe("appStore setTaskPinned", () => {
  beforeEach(() => {
    useAppStore.setState({ tasks: [], activeTaskId: null });
  });

  it("toggles the pinned flag on an existing task", () => {
    useAppStore.setState({
      tasks: [
        { id: "a", title: "A" },
        { id: "b", title: "B", pinned: true },
      ],
    });

    useAppStore.getState().setTaskPinned("a", true);
    expect(useAppStore.getState().tasks.find((t) => t.id === "a")?.pinned).toBe(true);

    useAppStore.getState().setTaskPinned("b", false);
    expect(useAppStore.getState().tasks.find((t) => t.id === "b")?.pinned).toBe(false);
  });

  it("returns the same state for unknown ids or no-op updates", () => {
    useAppStore.setState({ tasks: [{ id: "a", title: "A", pinned: true }] });
    const before = useAppStore.getState().tasks;

    useAppStore.getState().setTaskPinned("missing", true);
    expect(useAppStore.getState().tasks).toBe(before);

    useAppStore.getState().setTaskPinned("a", true);
    expect(useAppStore.getState().tasks).toBe(before);
  });
});
