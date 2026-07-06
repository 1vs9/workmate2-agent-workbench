import { useEffect, useRef } from "react";
import AgentAvatar from "../agents/AgentAvatar";
import type { Employee } from "../../api/plaza";
import type { Team } from "../../api/teams";
import {
  memberSessionStatus,
} from "../../utils/partitionTeamConversation";
import { getMemberTurnsFromPartition } from "../../utils/memberConversationThread";
import type { ChatTurn } from "../../utils/chatStreamReducer";
import {
  resolveTeamRepresentativeProfile,
  resolveTeamSpeakerProfile,
  teamLeaderDisplayName,
} from "../../utils/resolveTeamSpeakerProfile";

export type TeamActiveSession = "leader" | string;

export interface TeamSessionTabsProps {
  team: Team | null;
  memberNames: string[];
  memberTurnsByName: Map<string, ChatTurn[]>;
  employees: Employee[];
  activeSession: TeamActiveSession;
  onSelectSession: (session: TeamActiveSession) => void;
  /** When true, render flush above the composer without section borders. */
  docked?: boolean;
}

function handleSessionTrackWheel(e: WheelEvent) {
  const track = e.currentTarget as HTMLDivElement | null;
  if (!track) return;
  if (track.scrollWidth <= track.clientWidth) return;

  const delta =
    Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX;
  if (!delta) return;

  e.preventDefault();
  e.stopPropagation();
  track.scrollLeft += delta;
}

function DoneBadge() {
  return (
    <span
      className="absolute -bottom-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full border border-white bg-emerald-200 text-[9px] text-emerald-700"
      aria-label="已完成"
    >
      <svg viewBox="0 0 12 12" width="8" height="8" aria-hidden="true">
        <path
          d="M2.5 6.2 5 8.7 9.5 3.8"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

function WorkingBadge() {
  return (
    <span
      className="absolute -bottom-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full border border-white bg-amber-400 text-[9px] text-white"
      aria-label="执行中"
    >
      ·
    </span>
  );
}

function SelectedBadge() {
  return (
    <span
      className="absolute -bottom-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full border border-white bg-emerald-500 text-white"
      aria-label="当前选中"
    >
      <svg viewBox="0 0 12 12" width="8" height="8" aria-hidden="true">
        <path
          d="M2.5 6.2 5 8.7 9.5 3.8"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  );
}

function SessionTab({
  label,
  profile,
  selected,
  working = false,
  done = false,
  onClick,
  ariaLabel,
  docked = false,
}: {
  label: string;
  profile: ReturnType<typeof resolveTeamSpeakerProfile>;
  selected: boolean;
  working?: boolean;
  done?: boolean;
  onClick: () => void;
  ariaLabel: string;
  docked?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      aria-label={ariaLabel}
      className={[
        "group flex min-h-[36px] shrink-0 cursor-pointer items-center gap-1.5 rounded-full border px-1.5 py-1 transition-colors duration-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-500",
        selected
          ? docked
            ? "border-emerald-200 bg-white text-slate-900 shadow-sm shadow-emerald-100/60"
            : "border-white/80 bg-white/95 text-slate-800"
          : docked
            ? "border-transparent text-slate-500 hover:bg-white/75 hover:text-slate-800"
            : "border-transparent bg-transparent text-slate-600 hover:bg-white/70 hover:text-slate-800",
      ].join(" ")}
    >
      <span className="relative">
        <AgentAvatar
          name={profile.name}
          avatar={profile.avatar}
          description={profile.description}
          portraitName={profile.portraitName}
          portraitDescription={profile.portraitDescription}
          role={profile.role}
          size="sm"
          className="!h-8 !w-8"
        />
        {selected ? (
          <SelectedBadge />
        ) : working ? (
          <WorkingBadge />
        ) : done ? (
          <DoneBadge />
        ) : null}
      </span>
      <span className={[
        "max-w-[120px] truncate text-[12px]",
        selected ? "font-semibold" : "font-medium",
      ].join(" ")}>
        {label}
      </span>
    </button>
  );
}

export default function TeamSessionTabs({
  team,
  memberNames,
  memberTurnsByName,
  employees,
  activeSession,
  onSelectSession,
  docked = false,
}: TeamSessionTabsProps) {
  const leaderLabel = team?.name
    ? teamLeaderDisplayName(team.name)
    : teamLeaderDisplayName("团队");
  const leaderProfile = team
    ? resolveTeamRepresentativeProfile(team, employees)
    : resolveTeamSpeakerProfile(leaderLabel, team, employees);
  const leaderSelected = activeSession === "leader";
  const sessionTrackRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!docked) return;
    const track = sessionTrackRef.current;
    if (!track) return;
    track.addEventListener("wheel", handleSessionTrackWheel, {
      passive: false,
    });
    return () => {
      track.removeEventListener("wheel", handleSessionTrackWheel);
    };
  }, [docked]);

  return (
    <div
      className={
        docked
          ? "relative mb-2 h-11 shrink-0 overflow-hidden rounded-full bg-white/70 px-1.5 backdrop-blur"
          : "shrink-0 bg-[#f8faf9] px-6 pb-1 pt-2.5"
      }
      role="tablist"
      aria-label="团队会话参与者"
    >
      <div
        ref={sessionTrackRef}
        data-team-session-track
        className={
          docked
            ? "scrollbar-hide flex h-full items-center gap-1.5 overflow-x-auto px-1 py-1"
            : "scrollbar-hide mx-auto flex max-w-[860px] items-center gap-2 overflow-x-auto pb-0.5"
        }
      >
        <SessionTab
          label={leaderLabel}
          profile={leaderProfile}
          selected={leaderSelected}
          onClick={() => onSelectSession("leader")}
          ariaLabel={`查看 ${leaderLabel} 主会话`}
          docked={docked}
        />
        {memberNames.map((name) => {
          const profile = resolveTeamSpeakerProfile(name, team, employees);
          const status = memberSessionStatus(getMemberTurnsFromPartition(memberTurnsByName, name));
          const working = status === "working";
          const done = status === "done";
          const selected =
            activeSession !== "leader" &&
            activeSession.toLowerCase() === name.toLowerCase();

          return (
            <SessionTab
              key={name}
              label={name}
              profile={profile}
              selected={selected}
              working={working}
              done={done}
              onClick={() => onSelectSession(name)}
              ariaLabel={`查看 ${name} 的成员会话`}
              docked={docked}
            />
          );
        })}
      </div>
    </div>
  );
}
