export interface TeamLeaderPromptMember {
  name: string;
  desc?: string;
}

export interface GenerateTeamLeaderPromptInput {
  teamName: string;
  members: TeamLeaderPromptMember[];
}

export type GenerateTeamLeaderPromptResult =
  | { ok: true; prompt: string }
  | { ok: false; reason: "missing_name" | "missing_members" };

function summarizeMemberDesc(desc?: string): string {
  const trimmed = (desc ?? "").trim();
  if (!trimmed) {
    return "按岗位完成 Leader 派工任务";
  }
  const firstLine = trimmed.split(/\n/)[0]?.trim() || trimmed;
  if (firstLine.length <= 72) {
    return firstLine;
  }
  return `${firstLine.slice(0, 69)}…`;
}

function formatMemberLines(members: TeamLeaderPromptMember[]): string {
  return members
    .map(
      (member) =>
        `- **${member.name}**：${summarizeMemberDesc(member.desc)}`,
    )
    .join("\n");
}

function formatMemberNames(members: TeamLeaderPromptMember[]): string {
  const names = members.map((member) => member.name);
  if (names.length <= 3) {
    return names.join("、");
  }
  return `${names.slice(0, 3).join("、")} 等 ${names.length} 人`;
}

/** Deterministic team Leader prompt from team name and worker roster. */
export function generateTeamLeaderPrompt(
  input: GenerateTeamLeaderPromptInput,
): GenerateTeamLeaderPromptResult {
  const teamName = input.teamName.trim();
  const members = input.members
    .map((member) => ({
      name: member.name.trim(),
      desc: member.desc,
    }))
    .filter((member) => member.name);

  if (!teamName) {
    return { ok: false, reason: "missing_name" };
  }
  if (members.length === 0) {
    return { ok: false, reason: "missing_members" };
  }

  const memberLines = formatMemberLines(members);
  const memberSummary = formatMemberNames(members);

  const prompt = `你是「${teamName}」的 leader，负责协调 ${memberSummary}。你只负责调度、规划、派工与汇总，不亲自执行具体任务。

### 团队成员（执行者）
${memberLines}

### 你的工作方式
1. 理解用户目标，将任务拆解为可派工的子项
2. 使用 @成员名 将子任务分配给最合适的执行者
3. 跟进各成员进展，整合产出并向用户汇报结论

### 边界
- 不亲自写代码、查资料、生成报告等应由成员完成的工作
- 不替代执行者完成岗位任务`;

  return { ok: true, prompt };
}

export const TEAM_LEADER_PROMPT_VALIDATION_MESSAGES: Record<
  Exclude<GenerateTeamLeaderPromptResult, { ok: true }>["reason"],
  string
> = {
  missing_name: "请先填写团队名称",
  missing_members: "请至少选择一名执行者",
};
