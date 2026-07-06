export type AssigneeType = "default" | "employee" | "team";

export interface Assignee {
  type: AssigneeType;
  name: string;
  subtitle?: string;
  avatar?: string;
  teamId?: string;
  agentId?: string;
}

/** True when value looks like an internal QwenPaw agent id (e.g. emp_838c055f12). */
export function isInternalAgentId(value: string | undefined | null): boolean {
  const trimmed = String(value ?? "").trim();
  return /^emp_[a-f0-9]{6,}/i.test(trimmed);
}

export const AGENTDESK_BRAND_NAME = "AgentDesk企伴";

export const AGENTDESK_DEFAULT_SUBTITLE =
  "企业智能工作助手 · 日常办公、知识问答、文档处理与工具协作";

/** True when a label refers to the AgentDesk product assistant (not an employee). */
export function isAgentDeskBrandName(name: string | undefined | null): boolean {
  const trimmed = String(name ?? "").trim();
  return (
    trimmed === AGENTDESK_BRAND_NAME ||
    trimmed === "AgentDesk" ||
    // Legacy/in-progress rename alias: older persisted turns and the previous
    // reducer fallback labelled the default agent "WorkBuddy". Treat it as the
    // same brand so a single agent never splits into two differently-named rows.
    trimmed === "WorkBuddy" ||
    trimmed === "Default Agent"
  );
}

export function getDefaultAssignee(): Assignee {
  return {
    type: "default",
    name: AGENTDESK_BRAND_NAME,
    subtitle: AGENTDESK_DEFAULT_SUBTITLE,
  };
}

export function getAssigneeLabel(assignee: Assignee): string {
  if (assignee.type === "default") return AGENTDESK_BRAND_NAME;
  const name = assignee.name?.trim() || "";
  if (!name || isInternalAgentId(name)) return "数字员工";
  return name;
}

export function resolveEmployeeDisplayName(employee: {
  name: string;
  id?: string;
  agent_id?: string;
  desc?: string;
}): string {
  const name = employee.name?.trim() || "";
  if (name && !isInternalAgentId(name)) return name;
  const desc = employee.desc?.trim() || "";
  if (desc && !isInternalAgentId(desc)) return desc.slice(0, 32);
  return "数字员工";
}

/** Drop duplicate employee rows from merged agent-profile + store lists. */
export function dedupeEmployees<
  T extends { name: string; id?: string; agent_id?: string; desc?: string },
>(employees: T[]): T[] {
  const seenIds = new Set<string>();
  const seenNames = new Set<string>();
  const result: T[] = [];

  for (const emp of employees) {
    const stableId = String(emp.agent_id || emp.id || "").trim();
    const label = resolveEmployeeDisplayName(emp);

    if (stableId && seenIds.has(stableId)) continue;
    if (label && seenNames.has(label)) continue;

    if (stableId) seenIds.add(stableId);
    if (label) seenNames.add(label);
    result.push(emp);
  }

  return result;
}

export function buildEmployeeAssignee(card: {
  name: string;
  id?: string;
  agent_id?: string;
  desc?: string;
  tags?: string[];
  avatar?: string;
}): Assignee {
  const displayName = resolveEmployeeDisplayName(card);
  return {
    type: "employee",
    name: displayName,
    agentId: card.agent_id || card.id,
    subtitle: (card.tags ?? []).slice(0, 2).join(" / ") || card.desc?.slice(0, 40) || "单智能体",
    avatar: card.avatar,
  };
}

export function buildTeamAssignee(team: {
  id: string;
  name: string;
  tags?: string[];
  avatar?: string;
}): Assignee {
  return {
    type: "team",
    name: team.name,
    teamId: team.id,
    subtitle: (team.tags ?? []).slice(0, 3).join(" / ") || "多智能体团队",
    avatar: team.avatar,
  };
}
