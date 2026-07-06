import type { KeyboardEvent, MouseEvent } from "react";
import AgentAvatar from "./AgentAvatar";

export type AgentTeamCardBadgeVariant = "featured" | "joined" | "default";

export interface AgentTeamCardBadge {
  label: string;
  variant?: AgentTeamCardBadgeVariant;
}

export interface AgentTeamCardAction {
  key: string;
  label: string;
  onClick: () => void;
  loading?: boolean;
  disabled?: boolean;
  variant?: "primary" | "secondary" | "muted" | "danger";
  hidden?: boolean;
}

export interface AgentTeamCardProps {
  name: string;
  avatar?: string;
  subtitle?: string;
  description?: string;
  avatarRole?: "employee" | "team";
  tags?: string[];
  badge?: AgentTeamCardBadge;
  meta?: string;
  actions?: AgentTeamCardAction[];
  onClick?: () => void;
  className?: string;
}

function badgeClass(variant: AgentTeamCardBadgeVariant = "default"): string {
  switch (variant) {
    case "featured":
      return "wm-expert-card__badge wm-expert-card__badge--featured";
    case "joined":
      return "wm-expert-card__badge wm-expert-card__badge--joined";
    default:
      return "wm-expert-card__badge";
  }
}

function actionClass(variant: AgentTeamCardAction["variant"] = "secondary"): string {
  switch (variant) {
    case "primary":
      return "wm-expert-card__action wm-expert-card__action--primary";
    case "muted":
      return "wm-expert-card__action wm-expert-card__action--muted";
    case "danger":
      return "wm-expert-card__action wm-expert-card__action--danger";
    default:
      return "wm-expert-card__action wm-expert-card__action--secondary";
  }
}

export default function AgentTeamCard({
  name,
  avatar,
  subtitle,
  description,
  avatarRole = "employee",
  tags = [],
  badge,
  meta,
  actions = [],
  onClick,
  className = "",
}: AgentTeamCardProps) {
  const visibleActions = actions.filter((action) => !action.hidden);
  const visibleTags = tags.filter((tag) => tag.trim()).slice(0, 3);
  const clickable = Boolean(onClick);

  const handleCardClick = () => {
    onClick?.();
  };

  const handleCardKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (!clickable) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onClick?.();
    }
  };

  const stopActionClick = (event: MouseEvent, action: AgentTeamCardAction) => {
    event.stopPropagation();
    if (action.disabled || action.loading) return;
    action.onClick();
  };

  return (
    <article
      className={`wm-expert-card${clickable ? " wm-expert-card--clickable" : ""} ${className}`.trim()}
      onClick={clickable ? handleCardClick : undefined}
      onKeyDown={clickable ? handleCardKeyDown : undefined}
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
    >
      <div className="wm-expert-card__head">
        <div className="wm-expert-card__identity">
          <AgentAvatar
            name={name}
            avatar={avatar}
            description={description}
            role={avatarRole}
            size="md"
          />
          <div className="wm-expert-card__titles">
            <div className="wm-expert-card__title-row">
              <h3 className="wm-expert-card__title" title={name}>
                {name}
              </h3>
              {badge ? (
                <span className={badgeClass(badge.variant)}>{badge.label}</span>
              ) : null}
            </div>
            {visibleTags.length > 0 ? (
              <div className="wm-expert-card__tags wm-expert-card__tags--head">
                {visibleTags.map((tag) => (
                  <span key={tag} className="wm-expert-card__tag">
                    {tag}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <p className="wm-expert-card__desc line-clamp-2">{description || "—"}</p>

      {meta ? <p className="wm-expert-card__meta line-clamp-1">{meta}</p> : null}

      {visibleActions.length > 0 ? (
        <div className="wm-expert-card__footer">
          <div className="wm-expert-card__footer-left">
            {subtitle ? (
              <span className="wm-expert-card__footer-label">{subtitle}</span>
            ) : null}
          </div>
          <div className="wm-expert-card__footer-right wm-expert-card__footer-right--always">
            {visibleActions.map((action) =>
              action.variant === "muted" ? (
                <span key={action.key} className={actionClass(action.variant)}>
                  {action.label}
                </span>
              ) : (
                <button
                  key={action.key}
                  type="button"
                  className={actionClass(action.variant)}
                  onClick={(event) => stopActionClick(event, action)}
                  disabled={action.disabled || action.loading}
                >
                  {action.loading ? (
                    <span className="wm-expert-card__spinner" aria-hidden="true" />
                  ) : null}
                  {action.label}
                </button>
              ),
            )}
          </div>
        </div>
      ) : null}
    </article>
  );
}
