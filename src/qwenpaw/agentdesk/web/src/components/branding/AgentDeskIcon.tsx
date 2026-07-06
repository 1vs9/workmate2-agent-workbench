import type { CSSProperties } from "react";

const SPARKLE_PATHS = (
  <>
    <path d="M12 3l1.6 4.9L18.5 9l-4.9 1.6L12 15.5 9.4 10.6 4.5 9l4.9-1.6L12 3z" />
    <path d="M19 14l.9 2.7L22.5 18l-2.6.9L19 21.5l-.9-2.6L15.5 18l2.6-.9L19 14z" />
  </>
);

export interface AgentDeskIconProps {
  /** Pixel size of the outer square (default 24). */
  size?: number;
  className?: string;
  /** Homepage-style glow ring behind the icon. */
  ring?: boolean;
  /** Subtle scale/opacity pulse for active agent replies. */
  breathing?: boolean;
  style?: CSSProperties;
  "aria-label"?: string;
  "aria-hidden"?: boolean;
}

export function AgentDeskSparkles({
  className,
  size,
}: {
  className?: string;
  size?: number;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      width={size}
      height={size}
      className={className}
      aria-hidden="true"
    >
      {SPARKLE_PATHS}
    </svg>
  );
}

/** White rounded square with teal sparkle stars — system & agent branding. */
export default function AgentDeskIcon({
  size = 24,
  className = "",
  ring = false,
  breathing = false,
  style,
  "aria-label": ariaLabel = "AgentDesk",
  "aria-hidden": ariaHidden,
}: AgentDeskIconProps) {
  const radius = Math.round(size * 0.28);
  const sparkleSize = Math.round(size * 0.58);

  const box = (
    <div
      role={ariaHidden ? undefined : "img"}
      aria-label={ariaHidden ? undefined : ariaLabel}
      aria-hidden={ariaHidden}
      className={[
        "relative flex shrink-0 items-center justify-center border border-white/80 bg-white text-emerald-800 shadow-[0_4px_14px_rgba(15,23,42,0.08)]",
        breathing ? "wm-avatar-breathe" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      style={{
        width: size,
        height: size,
        borderRadius: radius,
        ...style,
      }}
    >
      <AgentDeskSparkles className="text-emerald-800" size={sparkleSize} />
    </div>
  );

  if (!ring) return box;

  const ringRadius = radius + 2;
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <div
        className="wm-home-logo-ring pointer-events-none absolute -inset-1 opacity-80 blur-sm"
        style={{ borderRadius: ringRadius }}
        aria-hidden="true"
      />
      {box}
    </div>
  );
}

/** Chat avatar wrapper — same icon with optional breathing while streaming. */
export function AgentDeskAvatar({
  breathing = false,
  className = "",
}: {
  breathing?: boolean;
  className?: string;
}) {
  return (
    <AgentDeskIcon
      size={28}
      breathing={breathing}
      className={className}
      aria-hidden
    />
  );
}

const BRAND_AVATAR_PX = { sm: 20, md: 32 } as const;

/** Compact brand mark for composer toolbar and assignee pickers (not employee portraits). */
export function AgentDeskBrandAvatar({
  size = "md",
  className = "",
}: {
  size?: keyof typeof BRAND_AVATAR_PX;
  className?: string;
}) {
  return (
    <AgentDeskIcon
      size={BRAND_AVATAR_PX[size]}
      className={className}
      aria-hidden
    />
  );
}
