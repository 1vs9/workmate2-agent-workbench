import type { ReactNode } from "react";
import { ToolOutlined } from "@ant-design/icons";
import AgentAvatar from "../agents/AgentAvatar";
import { AgentDeskBrandAvatar } from "../branding/AgentDeskIcon";
import { isAgentDeskBrandName } from "../../types/assignee";
import { isAvatarImageUrl } from "../../utils/agentAvatar";
import { SkillIcon } from "../../utils/skillIcon";

export interface PullUpSelectOption {
  id: string;
  label: string;
  subtitle?: string;
  avatar?: string;
  /** Tool icon key from skill metadata (iconMode="skill"). */
  icon?: string | null;
  /** Skill description for icon resolution (iconMode="skill"). */
  description?: string;
}

export interface PullUpSelectSection {
  label?: string;
  options: PullUpSelectOption[];
}

export interface PullUpSelectProps {
  open: boolean;
  headerTitle?: string;
  headerSubtitle?: string;
  headerAvatar?: string;
  headerSelected?: boolean;
  onHeaderSelect?: () => void;
  /** Called after header selection (e.g. parent closes the panel). */
  onClose?: () => void;
  sections: PullUpSelectSection[];
  selectedId?: string;
  selectedIds?: string[];
  onSelect: (option: PullUpSelectOption) => void;
  className?: string;
  widthClass?: string;
  footer?: ReactNode;
  /** "avatar" for people/teams; "skill" for Ant Design tool icons (no portraits). */
  iconMode?: "avatar" | "skill";
}

function AssigneeAvatar({
  avatar,
  name = "数字员工",
  size = "md",
}: {
  avatar?: string;
  name?: string;
  size?: "sm" | "md";
}) {
  if (isAgentDeskBrandName(name)) {
    return <AgentDeskBrandAvatar size={size} />;
  }
  if (isAvatarImageUrl(avatar) || !avatar) {
    return <AgentAvatar name={name} avatar={avatar} size={size} />;
  }
  return <AgentAvatar name={name} avatar={undefined} size={size} />;
}

function SkillOptionIcon({
  name,
  icon,
  description,
  size = "sm",
}: {
  name: string;
  icon?: string | null;
  description?: string;
  size?: "sm" | "md";
}) {
  const boxClass =
    size === "sm"
      ? "h-7 w-7 text-sm"
      : "h-8 w-8 text-base";
  return (
    <span
      className={`flex shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700 ${boxClass}`}
    >
      <SkillIcon name={name} icon={icon} description={description} className="text-[inherit]" />
    </span>
  );
}

function PullUpOptionIcon({
  option,
  iconMode,
  size = "sm",
}: {
  option: PullUpSelectOption;
  iconMode: "avatar" | "skill";
  size?: "sm" | "md";
}) {
  if (iconMode === "skill") {
    return (
      <SkillOptionIcon
        name={option.label}
        icon={option.icon}
        description={option.description}
        size={size}
      />
    );
  }
  return <AssigneeAvatar avatar={option.avatar} name={option.label} size={size} />;
}

function PullUpHeaderIcon({
  iconMode,
  avatar,
  name,
}: {
  iconMode: "avatar" | "skill";
  avatar?: string;
  name: string;
}) {
  if (iconMode === "skill") {
    return (
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gray-100 text-gray-500">
        <ToolOutlined aria-hidden />
      </span>
    );
  }
  return <AssigneeAvatar avatar={avatar} name={name} size="md" />;
}

export default function PullUpSelect({
  open,
  headerTitle,
  headerSubtitle,
  headerAvatar,
  headerSelected = false,
  onHeaderSelect,
  onClose,
  sections,
  selectedId,
  selectedIds,
  onSelect,
  className = "left-0",
  widthClass = "w-[280px]",
  footer,
  iconMode = "avatar",
}: PullUpSelectProps) {
  if (!open) return null;

  return (
    <div
      className={`wm-pullup ${widthClass} ${className}`}
      role="listbox"
      aria-label={headerTitle ?? "选项"}
    >
      {headerTitle && onHeaderSelect ? (
        <>
          <button
            type="button"
            className={`wm-pullup__header ${headerSelected ? "wm-pullup__header--selected" : ""}`}
            onClick={() => {
              onHeaderSelect?.();
              onClose?.();
            }}
          >
            <PullUpHeaderIcon iconMode={iconMode} avatar={headerAvatar} name={headerTitle} />
            <span className="min-w-0 flex-1 text-left">
              <span className="block truncate text-[13px] font-semibold text-gray-900">
                {headerTitle}
              </span>
              {headerSubtitle ? (
                <span className="block truncate text-[11px] font-normal text-gray-500">
                  {headerSubtitle}
                </span>
              ) : null}
            </span>
            {headerSelected ? (
              <span className="shrink-0 text-emerald-500" aria-hidden="true">
                ✓
              </span>
            ) : null}
          </button>
          <div className="wm-pullup__divider" />
        </>
      ) : headerTitle ? (
        <>
          <div className="wm-pullup__header wm-pullup__header--static">
            <span className="text-[13px] font-semibold text-gray-900">{headerTitle}</span>
          </div>
          <div className="wm-pullup__divider" />
        </>
      ) : null}

      {sections.map((section, sectionIdx) => (
        <div key={section.label ?? sectionIdx} className="wm-pullup__section">
          {section.label ? (
            <div className="wm-pullup__section-label">{section.label}</div>
          ) : null}
          {section.options.map((option) => {
            const selected =
              selectedId === option.id ||
              (selectedIds?.includes(option.id) ?? false);
            return (
              <button
                key={option.id}
                type="button"
                role="option"
                aria-selected={selected}
                className={`wm-pullup__item ${selected ? "wm-pullup__item--selected" : ""}`}
                onClick={() => onSelect(option)}
              >
                <PullUpOptionIcon option={option} iconMode={iconMode} size="sm" />
                <span className="min-w-0 flex-1 text-left">
                  <span className="block truncate text-[13px] font-medium text-gray-900">
                    {option.label}
                  </span>
                  {option.subtitle ? (
                    <span className="block truncate text-[11px] text-gray-500">
                      {option.subtitle}
                    </span>
                  ) : null}
                </span>
                {selected ? (
                  <span className="shrink-0 text-emerald-500" aria-hidden="true">
                    ✓
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      ))}

      {footer ? <div className="wm-pullup__footer">{footer}</div> : null}
    </div>
  );
}
