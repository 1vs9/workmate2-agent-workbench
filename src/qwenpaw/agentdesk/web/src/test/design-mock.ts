/**
 * Stub for @agentscope-ai/design in tests.
 * The real package is large and can hang vitest workers.
 */
import React from "react";

export const bailianTheme = { theme: {} };
export const bailianDarkTheme = { theme: {} };

export function ConfigProvider({
  children,
}: {
  children?: React.ReactNode;
}) {
  return React.createElement(React.Fragment, null, children);
}
