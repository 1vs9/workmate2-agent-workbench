import type { ReactNode } from "react";

interface PageShellProps {
  children: ReactNode;
  narrow?: boolean;
}

/** Content page wrapper — same ambient bg as Home. */
export default function PageShell({ children, narrow = false }: PageShellProps) {
  return (
    <div
      className={`wm-page-shell h-full min-h-0 overflow-auto ${narrow ? "wm-page-shell--narrow" : ""}`}
    >
      <div className="wm-page-shell__inner">{children}</div>
    </div>
  );
}
