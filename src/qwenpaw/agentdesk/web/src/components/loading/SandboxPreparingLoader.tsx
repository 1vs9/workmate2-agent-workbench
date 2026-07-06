import type { CSSProperties } from "react";
import AgentDeskIcon from "../branding/AgentDeskIcon";

export interface SandboxPreparingLoaderProps {
  /** Primary status line (default: 正在准备沙箱环境…) */
  title?: string;
  /** Secondary hint below the illustration */
  hint?: string;
  /** Show AgentDesk branding above the loader */
  showBrand?: boolean;
  /** full = centered page overlay; inline = compact block for panels */
  variant?: "full" | "inline";
  className?: string;
  style?: CSSProperties;
}

const DEFAULT_TITLE = "正在准备沙箱环境…";
const DEFAULT_HINT = "隔离工作区 · 挂载依赖 · 校验权限";

/** Animated sandbox-prep loader — matches AgentDesk emerald / soft-card visual system. */
export default function SandboxPreparingLoader({
  title = DEFAULT_TITLE,
  hint = DEFAULT_HINT,
  showBrand = true,
  variant = "full",
  className = "",
  style,
}: SandboxPreparingLoaderProps) {
  const isFull = variant === "full";

  return (
    <div
      className={[
        isFull
          ? "wm-sandbox-loader wm-sandbox-loader--full"
          : "wm-sandbox-loader wm-sandbox-loader--inline",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      style={style}
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label={title}
    >
      {isFull ? (
        <div className="wm-sandbox-loader__bg" aria-hidden="true" />
      ) : null}

      <div className="wm-sandbox-loader__card">
        {showBrand ? (
          <div className="wm-sandbox-loader__brand">
            <AgentDeskIcon size={36} ring breathing aria-hidden />
          </div>
        ) : null}

        <div className="wm-sandbox-loader__art" aria-hidden="true">
          <svg
            className="wm-sandbox-loader__svg"
            viewBox="0 0 200 200"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <defs>
              <linearGradient
                id="wm-sb-ring"
                x1="40"
                y1="20"
                x2="160"
                y2="180"
                gradientUnits="userSpaceOnUse"
              >
                <stop stopColor="#10B981" />
                <stop offset="1" stopColor="#3B82F6" stopOpacity="0.55" />
              </linearGradient>
              <linearGradient
                id="wm-sb-fill"
                x1="70"
                y1="70"
                x2="130"
                y2="130"
                gradientUnits="userSpaceOnUse"
              >
                <stop stopColor="#ECFDF5" />
                <stop offset="1" stopColor="#F0FDF4" />
              </linearGradient>
              <filter
                id="wm-sb-shadow"
                x="-20%"
                y="-20%"
                width="140%"
                height="140%"
              >
                <feDropShadow
                  dx="0"
                  dy="4"
                  stdDeviation="6"
                  floodColor="#0F172A"
                  floodOpacity="0.08"
                />
              </filter>
            </defs>

            {/* Outer security ring */}
            <circle
              className="wm-sandbox-loader__ring-outer"
              cx="100"
              cy="100"
              r="78"
              stroke="url(#wm-sb-ring)"
              strokeWidth="2"
              strokeDasharray="8 10"
              strokeLinecap="round"
              opacity="0.55"
            />
            <circle
              className="wm-sandbox-loader__ring-inner"
              cx="100"
              cy="100"
              r="68"
              stroke="#059669"
              strokeWidth="1.5"
              strokeDasharray="4 14"
              opacity="0.28"
            />

            {/* Sandbox container */}
            <rect
              x="58"
              y="58"
              width="84"
              height="84"
              rx="16"
              fill="url(#wm-sb-fill)"
              stroke="rgba(16, 185, 129, 0.35)"
              strokeWidth="1.5"
              filter="url(#wm-sb-shadow)"
            />

            {/* 3×3 grid cells — staggered boot sequence */}
            {[
              [72, 72],
              [92, 72],
              [112, 72],
              [72, 92],
              [92, 92],
              [112, 92],
              [72, 112],
              [92, 112],
              [112, 112],
            ].map(([x, y], i) => (
              <rect
                key={`${x}-${y}`}
                className="wm-sandbox-loader__cell"
                style={{ animationDelay: `${i * 0.12}s` }}
                x={x}
                y={y}
                width="14"
                height="14"
                rx="4"
                fill="#059669"
              />
            ))}

            {/* Scan line */}
            <rect
              className="wm-sandbox-loader__scan"
              x="62"
              y="62"
              width="76"
              height="3"
              rx="1.5"
              fill="#34D399"
              opacity="0.7"
            />

            {/* Corner status nodes */}
            <circle
              className="wm-sandbox-loader__node wm-sandbox-loader__node--a"
              cx="36"
              cy="100"
              r="5"
              fill="#10B981"
            />
            <circle
              className="wm-sandbox-loader__node wm-sandbox-loader__node--b"
              cx="164"
              cy="72"
              r="4"
              fill="#3B82F6"
              opacity="0.75"
            />
            <circle
              className="wm-sandbox-loader__node wm-sandbox-loader__node--c"
              cx="164"
              cy="128"
              r="4"
              fill="#059669"
              opacity="0.6"
            />
          </svg>
        </div>

        <p className="wm-sandbox-loader__title">{title}</p>
        <p className="wm-sandbox-loader__hint">{hint}</p>

        <div className="wm-sandbox-loader__progress" aria-hidden="true">
          <span className="wm-sandbox-loader__progress-bar" />
        </div>
      </div>
    </div>
  );
}
