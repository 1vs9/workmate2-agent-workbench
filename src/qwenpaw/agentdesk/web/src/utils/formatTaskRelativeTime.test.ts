import { describe, expect, it, vi } from "vitest";
import {
  formatTaskRelativeTime,
  normalizeTimestampMs,
  taskTimestamp,
} from "./formatTaskRelativeTime";

describe("normalizeTimestampMs", () => {
  it("converts unix seconds to milliseconds", () => {
    expect(normalizeTimestampMs(1_700_000_000)).toBe(1_700_000_000_000);
  });

  it("keeps millisecond timestamps unchanged", () => {
    expect(normalizeTimestampMs(1_700_000_000_000)).toBe(1_700_000_000_000);
  });
});

describe("formatTaskRelativeTime", () => {
  it("formats recent unix-second timestamps correctly", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-15T12:00:00Z"));

    const fiveMinutesAgoSec = Math.floor(Date.now() / 1000) - 5 * 60;
    expect(formatTaskRelativeTime(normalizeTimestampMs(fiveMinutesAgoSec))).toBe("5分钟前");

    vi.useRealTimers();
  });
});

describe("taskTimestamp", () => {
  it("prefers updated_at and normalizes seconds", () => {
    const ms = taskTimestamp({ updated_at: 1_700_000_000 });
    expect(ms).toBe(1_700_000_000_000);
  });
});
