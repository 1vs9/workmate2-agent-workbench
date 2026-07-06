import { type ReactNode, type RefObject, useEffect, useMemo } from "react";
import type { Employee } from "../../api/plaza";
import type { Team } from "../../api/teams";
import type { ChatTurn } from "../../utils/chatStreamReducer";
import { buildMemberConversationThread } from "../../utils/memberConversationThread";
import { partitionTeamConversation } from "../../utils/partitionTeamConversation";
import {
  resolveTeamRepresentativeProfile,
  resolveTeamSpeakerProfile,
  teamLeaderDisplayName,
} from "../../utils/resolveTeamSpeakerProfile";
import AgentAvatar from "../agents/AgentAvatar";
import ProcessObservability from "../chat/ProcessObservability";
import type { TeamActiveSession } from "./TeamSessionTabs";

export interface TeamChatTabbedViewProps {
  turns: ChatTurn[];
  team: Team | null;
  employees: Employee[];
  activeSession: TeamActiveSession;
  onActiveSessionChange: (session: TeamActiveSession) => void;
  renderTurn: (turn: ChatTurn, idx: number) => ReactNode;
  renderLeaderDelegation?: (
    text: string,
    itemKey: string,
    streaming?: boolean,
  ) => ReactNode;
  renderMemberReply?: (
    turn: ChatTurn,
    idx: number,
    memberName: string,
  ) => ReactNode;
  renderAssistantText?: (
    text: string,
    options?: { streaming?: boolean },
  ) => ReactNode;
  renderMemberText?: (
    text: string,
    options?: { streaming?: boolean },
  ) => ReactNode;
  scrollRef?: RefObject<HTMLDivElement>;
  onScroll?: () => void;
  footer?: ReactNode;
}

function MemberEmptyState({ memberName }: { memberName: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-10 text-center">
      <div className="text-[14px] font-medium text-slate-700">{memberName}</div>
      <div className="mt-2 max-w-[280px] text-[13px] leading-relaxed text-slate-500">
        等待 Leader 派工。派工后此处会显示 Leader 指令与该成员的回复。
      </div>
    </div>
  );
}

function renderPlainText(text: string) {
  return <div className="whitespace-pre-wrap">{text}</div>;
}

function DefaultLeaderDelegation({
  text,
  itemKey,
  leaderLabel,
  leaderProfile,
  streaming = false,
  renderAssistantText,
}: {
  text: string;
  itemKey: string;
  leaderLabel: string;
  leaderProfile: ReturnType<typeof resolveTeamRepresentativeProfile> | null;
  streaming?: boolean;
  renderAssistantText?: TeamChatTabbedViewProps["renderAssistantText"];
}) {
  return (
    <div key={itemKey} className="flex justify-start gap-2.5">
      {leaderProfile ? (
        <AgentAvatar
          name={leaderProfile.name}
          avatar={leaderProfile.avatar}
          description={leaderProfile.description}
          portraitName={leaderProfile.portraitName}
          portraitDescription={leaderProfile.portraitDescription}
          role={leaderProfile.role}
          size="sm"
          className="mt-0.5 shrink-0"
        />
      ) : null}
      <div className="min-w-0 max-w-[85%] flex-1 space-y-2">
        <div className="text-[12px] font-medium text-slate-600">{leaderLabel}</div>
        <div className="rounded-2xl border border-gray-200/80 bg-white px-4 py-2.5 text-[14px] leading-relaxed text-gray-800 shadow-sm">
          {renderAssistantText?.(text, { streaming }) ?? renderPlainText(text)}
        </div>
      </div>
    </div>
  );
}

const ASSISTANT_BUBBLE_CLASSES =
  "rounded-2xl border border-gray-200/80 bg-white px-4 py-2.5 text-[14px] leading-relaxed text-gray-800 shadow-sm";

function DefaultMemberReply({
  turn,
  idx,
  memberLabel,
  memberAvatar,
  renderMemberText,
}: {
  turn: ChatTurn;
  idx: number;
  memberLabel: string;
  memberAvatar?: ReturnType<typeof resolveTeamSpeakerProfile>;
  renderMemberText?: TeamChatTabbedViewProps["renderMemberText"];
}) {
  const text = turn.text.trim();
  const hasTrace = turn.traceEvents.length > 0;
  if (!text && !turn.streaming && !hasTrace) return null;
  return (
    <div key={turn.id || `member-${idx}`} className="flex justify-end gap-2.5">
      <div className="min-w-0 max-w-[85%]">
        <div className="mb-1 text-right text-[12px] font-medium text-slate-600">
          {memberLabel}
        </div>
        {hasTrace || turn.streaming ? (
          <div className="mb-1.5">
            <ProcessObservability
              events={turn.traceEvents}
              isStreaming={turn.streaming}
              className="mb-0"
            />
          </div>
        ) : null}
        {text || (turn.streaming && !hasTrace) ? (
          <div
            className={[
              ASSISTANT_BUBBLE_CLASSES,
              turn.streaming ? "animate-pulse" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {text ? (
              renderMemberText?.(text, { streaming: turn.streaming }) ??
              renderPlainText(text)
            ) : (
              <div className="text-gray-400">正在回复…</div>
            )}
          </div>
        ) : null}
      </div>
      {memberAvatar ? (
        <AgentAvatar
          name={memberAvatar.name}
          avatar={memberAvatar.avatar}
          description={memberAvatar.description}
          portraitName={memberAvatar.portraitName}
          portraitDescription={memberAvatar.portraitDescription}
          role={memberAvatar.role}
          size="sm"
          className="mt-5 shrink-0"
        />
      ) : null}
    </div>
  );
}

export default function TeamChatTabbedView({
  turns,
  team,
  employees,
  activeSession,
  onActiveSessionChange,
  renderTurn,
  renderLeaderDelegation,
  renderMemberReply,
  renderAssistantText,
  renderMemberText,
  scrollRef,
  onScroll,
  footer,
}: TeamChatTabbedViewProps) {
  const partition = useMemo(
    () => partitionTeamConversation(turns, team, employees),
    [turns, team, employees],
  );

  useEffect(() => {
    if (activeSession === "leader") return;
    const stillValid = partition.memberNames.some(
      (name) => name.toLowerCase() === activeSession.toLowerCase(),
    );
    if (!stillValid) {
      onActiveSessionChange("leader");
    }
  }, [activeSession, partition.memberNames, onActiveSessionChange]);

  const isLeaderSession = activeSession === "leader";
  const memberName = isLeaderSession ? null : activeSession;
  const memberThread = useMemo(
    () =>
      memberName
        ? buildMemberConversationThread(turns, memberName, team, employees)
        : [],
    [turns, memberName, team, employees],
  );

  const leaderProfile = team
    ? resolveTeamRepresentativeProfile(team, employees)
    : null;
  const leaderLabel = team ? teamLeaderDisplayName(team.name) : "Leader";
  const memberProfile =
    memberName != null
      ? resolveTeamSpeakerProfile(memberName, team, employees)
      : null;

  const visibleTurns = isLeaderSession ? partition.leaderTurns : [];

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="min-h-0 flex-1 overflow-y-auto px-6 py-4 scrollbar-hide"
        aria-label={isLeaderSession ? "Leader 主会话" : `${memberName} 成员会话`}
      >
        {isLeaderSession ? (
          <div className="mx-auto max-w-[860px] space-y-3">
            {visibleTurns.length === 0 ? (
              <div className="rounded-xl border border-dashed border-gray-200 bg-white/70 px-4 py-8 text-center text-[13px] text-slate-500">
                发送消息后，Leader 将在此协调团队并派工给成员。
              </div>
            ) : (
              visibleTurns.map((turn, idx) => renderTurn(turn, idx))
            )}
          </div>
        ) : memberName ? (
          memberThread.length === 0 ? (
            <div className="mx-auto flex min-h-[240px] max-w-[860px] flex-col">
              {memberProfile ? (
                <div className="mb-4 flex items-center gap-2.5">
                  <AgentAvatar
                    name={memberProfile.name}
                    avatar={memberProfile.avatar}
                    description={memberProfile.description}
                    portraitName={memberProfile.portraitName}
                    portraitDescription={memberProfile.portraitDescription}
                    role={memberProfile.role}
                    size="sm"
                  />
                  <div className="text-[13px] font-medium text-slate-700">
                    {memberName}
                  </div>
                </div>
              ) : null}
              <MemberEmptyState memberName={memberName} />
            </div>
          ) : (
            <div className="mx-auto max-w-[860px] space-y-3">
              {memberThread.map((item, idx) => {
                if (item.kind === "leader") {
                  return (
                    renderLeaderDelegation?.(item.text, item.id) ?? (
                      <DefaultLeaderDelegation
                        key={item.id}
                        itemKey={item.id}
                        text={item.text}
                        leaderLabel={leaderLabel}
                        leaderProfile={leaderProfile}
                        renderAssistantText={renderAssistantText}
                      />
                    )
                  );
                }
                return (
                  renderMemberReply?.(item.turn, idx, memberName) ?? (
                    <DefaultMemberReply
                      key={item.turn.id || `member-${idx}`}
                      turn={item.turn}
                      idx={idx}
                      memberLabel={memberName}
                      memberAvatar={memberProfile ?? undefined}
                      renderMemberText={renderMemberText}
                    />
                  )
                );
              })}
            </div>
          )
        ) : null}
      </div>

      {footer}
    </div>
  );
}

export function isTeamMemberSessionActive(
  activeSession: TeamActiveSession,
): boolean {
  return activeSession !== "leader";
}
