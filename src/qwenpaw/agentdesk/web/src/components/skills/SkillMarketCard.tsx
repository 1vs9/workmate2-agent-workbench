import { SkillIcon, type SkillIconKey } from "../../utils/skillIcon";

export interface SkillMarketCardProps {
  iconKey?: SkillIconKey | string;
  name?: string;
  description?: string;
  iconTone?: string;
  installed?: boolean;
  installing?: boolean;
  provider?: string;
  onInstall?: () => void;
  onChat?: () => void;
  onClick?: () => void;
}

const PlusIcon = () => (
  <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4" aria-hidden="true">
    <path
      d="M10 4v12M4 10h12"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
    />
  </svg>
);

const ChatIcon = () => (
  <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4" aria-hidden="true">
    <path
      d="M4 5.5A2.5 2.5 0 016.5 3h7A2.5 2.5 0 0116 5.5v5A2.5 2.5 0 0113.5 13H9l-3.5 3v-3H6.5A2.5 2.5 0 014 10.5v-5z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinejoin="round"
    />
  </svg>
);

export default function SkillMarketCard({
  iconKey,
  name = "",
  description = "",
  iconTone = "bg-emerald-50 text-emerald-600",
  installed = false,
  installing = false,
  provider,
  onInstall,
  onChat,
  onClick,
}: SkillMarketCardProps) {
  const clickable = Boolean(onClick);
  return (
    <article
      className={`wm-skill-card group flex h-full flex-col p-3.5 transition-all duration-200${
        clickable ? " cursor-pointer" : ""
      }`}
      onClick={clickable ? onClick : undefined}
      onKeyDown={
        clickable
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick?.();
              }
            }
          : undefined
      }
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
    >
      <div className="flex min-w-0 items-start gap-2.5">
        <div
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${iconTone}`}
        >
          <SkillIcon iconKey={iconKey} name={name} description={description} className="text-lg" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <h3
              className="min-w-0 text-[13px] font-semibold leading-snug text-gray-900"
              style={{
                display: "-webkit-box",
                WebkitBoxOrient: "vertical",
                WebkitLineClamp: 2,
                overflow: "hidden",
              }}
              title={name}
            >
              {name}
            </h3>
            {installed ? (
              <button
                type="button"
                title="挂载到对话"
                aria-label={`将 ${name} 挂载到对话`}
                onClick={(e) => {
                  e.stopPropagation();
                  onChat?.();
                }}
                className="inline-flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-emerald-100 bg-emerald-50 text-emerald-700 transition-colors hover:bg-emerald-100"
              >
                <ChatIcon />
              </button>
            ) : (
              <button
                type="button"
                title="安装技能"
                aria-label={`安装 ${name}`}
                disabled={installing}
                onClick={(e) => {
                  e.stopPropagation();
                  onInstall?.();
                }}
                className="inline-flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-gray-200 bg-white text-gray-600 transition-colors hover:border-emerald-200 hover:bg-emerald-50 hover:text-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {installing ? (
                  <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-emerald-200 border-t-emerald-600" />
                ) : (
                  <PlusIcon />
                )}
              </button>
            )}
          </div>
          {provider ? (
            <div className="mt-1 flex flex-wrap gap-1">
              <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-500">
                {provider}
              </span>
            </div>
          ) : null}
        </div>
      </div>

      <p className="mt-2 line-clamp-2 min-h-[2.25rem] flex-1 text-[12px] leading-relaxed text-gray-500">
        {description || "—"}
      </p>

      <div className="mt-2.5 text-[11px] text-gray-400">
        {installed ? "已安装" : "AgentDesk 技能"}
      </div>
    </article>
  );
}
