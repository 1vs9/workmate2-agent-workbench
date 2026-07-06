import { describe, expect, it } from "vitest";

import { isFatalStreamError } from "./streamErrorHandling";

describe("isFatalStreamError", () => {
  it("treats explicit non-fatal errors as recoverable", () => {
    expect(
      isFatalStreamError({ type: "error", content: "warn", fatal: false }),
    ).toBe(false);
  });

  it("treats missing fatal flag as terminal", () => {
    expect(isFatalStreamError({ type: "error", content: "fail" })).toBe(true);
  });

  it("ignores non-error events", () => {
    expect(isFatalStreamError({ type: "text_delta", content: "hi" })).toBe(false);
  });
});
