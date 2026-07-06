import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useProcessPanelExpanded } from "./useProcessPanelExpanded";

describe("useProcessPanelExpanded", () => {
  it("starts expanded when streaming", () => {
    const { result } = renderHook(() => useProcessPanelExpanded(true));
    expect(result.current[0]).toBe(true);
  });

  it("starts collapsed when not streaming", () => {
    const { result } = renderHook(() => useProcessPanelExpanded(false));
    expect(result.current[0]).toBe(false);
  });

  it("auto-expands when stream starts", () => {
    const { result, rerender } = renderHook(
      ({ streaming }) => useProcessPanelExpanded(streaming),
      { initialProps: { streaming: false } },
    );

    rerender({ streaming: true });
    expect(result.current[0]).toBe(true);
  });

  it("auto-collapses when stream ends", () => {
    const { result, rerender } = renderHook(
      ({ streaming }) => useProcessPanelExpanded(streaming),
      { initialProps: { streaming: true } },
    );

    rerender({ streaming: false });
    expect(result.current[0]).toBe(false);
  });

  it("allows manual expand after stream completes", () => {
    const { result, rerender } = renderHook(
      ({ streaming }) => useProcessPanelExpanded(streaming),
      { initialProps: { streaming: true } },
    );

    rerender({ streaming: false });
    expect(result.current[0]).toBe(false);

    act(() => {
      result.current[1]();
    });
    expect(result.current[0]).toBe(true);
  });

  it("allows manual collapse during streaming without re-expanding until next stream", () => {
    const { result, rerender } = renderHook(
      ({ streaming }) => useProcessPanelExpanded(streaming),
      { initialProps: { streaming: true } },
    );

    act(() => {
      result.current[1]();
    });
    expect(result.current[0]).toBe(false);

    rerender({ streaming: true });
    expect(result.current[0]).toBe(false);

    rerender({ streaming: false });
    expect(result.current[0]).toBe(false);
  });

  it("re-expands on a new stream after user had expanded history manually", () => {
    const { result, rerender } = renderHook(
      ({ streaming }) => useProcessPanelExpanded(streaming),
      { initialProps: { streaming: false } },
    );

    act(() => {
      result.current[1]();
    });
    expect(result.current[0]).toBe(true);

    rerender({ streaming: true });
    expect(result.current[0]).toBe(true);
  });
});
