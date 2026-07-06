import { useEffect, useMemo, useRef, useState } from "react";

import modelConfigApi from "../../api/modelConfig";
import { type Employee } from "../../api/plaza";
import { useComposerStore } from "../../store/composerStore";
import { useReferenceDataStore } from "../../store/referenceDataStore";
import {
  buildEmployeeAssignee,
  buildTeamAssignee,
  dedupeEmployees,
  getAssigneeLabel,
  getDefaultAssignee,
  isInternalAgentId,
  resolveEmployeeDisplayName,
  type Assignee,
} from "../../types/assignee";
import PullUpSelect, { type PullUpSelectOption } from "./PullUpSelect";
import { AgentDeskBrandAvatar } from "../branding/AgentDeskIcon";
import AgentAvatar from "../agents/AgentAvatar";
import { resolveTeamRepresentativeProfile } from "../../utils/resolveTeamSpeakerProfile";

export interface ComposerToolbarProps {
  taskId?: string;
  onSend: () => void;
  onStop?: () => void;
  sending?: boolean;
  streaming?: boolean;
  disabled?: boolean;
  submitButtonId?: string;
  workspaceOpen?: boolean;
  onWorkspaceToggle?: () => void;
  showTopDivider?: boolean;
}

type MenuId = "assignee" | "model" | "skills" | null;

const ChevronDown = () => (
  <svg viewBox="0 0 20 20" fill="none" className="h-3 w-3 shrink-0 opacity-60" aria-hidden="true">
    <path
      d="M6 8l4 4 4-4"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

function employeeOptionId(emp: Employee): string {
  return emp.agent_id || emp.id || emp.name;
}

function isSameAssignee(a: Assignee, b: Assignee): boolean {
  if (a.type !== b.type) return false;
  if (a.type === "default" && b.type === "default") return true;
  if (a.type === "team" && b.type === "team") {
    return (a.teamId && a.teamId === b.teamId) || a.name === b.name;
  }
  if (a.type === "employee" && b.type === "employee") {
    if (a.agentId && b.agentId && a.agentId === b.agentId) return true;
    return a.name === b.name;
  }
  return false;
}

export default function ComposerToolbar({
  taskId,
  onSend,
  onStop,
  sending = false,
  streaming = false,
  disabled = false,
  submitButtonId = "submitInputBtn",
  workspaceOpen = false,
  onWorkspaceToggle,
  showTopDivider = true,
}: ComposerToolbarProps) {
  const assignee = useComposerStore((s) => s.assignee);
  const skillNames = useComposerStore((s) => s.skillNames);
  const planMode = useComposerStore((s) => s.planMode);
  const modelAuto = useComposerStore((s) => s.modelAuto);
  const modelName = useComposerStore((s) => s.modelName);
  const modelProviderId = useComposerStore((s) => s.modelProviderId);
  const modelId = useComposerStore((s) => s.modelId);
  const setAssignee = useComposerStore((s) => s.setAssignee);
  const setSkillNames = useComposerStore((s) => s.setSkillNames);
  const toggleSkill = useComposerStore((s) => s.toggleSkill);
  const setPlanMode = useComposerStore((s) => s.setPlanMode);
  const setModelAuto = useComposerStore((s) => s.setModelAuto);
  const setModel = useComposerStore((s) => s.setModel);

  const [openMenu, setOpenMenu] = useState<MenuId>(null);
  // Reference lists come from the shared cache so opening a chat / switching
  // tasks does not re-issue these requests on every mount.
  const employees = useReferenceDataStore((s) => s.employees);
  const teams = useReferenceDataStore((s) => s.teams);
  const skills = useReferenceDataStore((s) => s.skills);
  const providers = useReferenceDataStore((s) => s.providers);
  const ensureReferenceData = useReferenceDataStore((s) => s.ensureLoaded);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void ensureReferenceData();
  }, [ensureReferenceData]);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpenMenu(null);
      }
    };
    document.addEventListener("click", onDocClick);
    return () => document.removeEventListener("click", onDocClick);
  }, []);

  useEffect(() => {
    if (assignee.type !== "employee" || employees.length === 0) return;
    if (!isInternalAgentId(assignee.name)) return;
    const match = employees.find(
      (emp) =>
        emp.agent_id === assignee.name ||
        emp.id === assignee.name ||
        emp.agent_id === assignee.agentId ||
        emp.id === assignee.agentId,
    );
    if (match) {
      setAssignee(buildEmployeeAssignee(match));
    }
  }, [assignee, employees, setAssignee]);

  const matchedTeam = useMemo(() => {
    if (assignee.type !== "team") return undefined;
    const teamId = assignee.teamId?.trim();
    const name = assignee.name?.trim();
    if (teamId) {
      const byId = teams.find((team) => team.id === teamId);
      if (byId) return byId;
    }
    if (name) {
      return teams.find((team) => team.name === name);
    }
    return undefined;
  }, [assignee, teams]);

  useEffect(() => {
    if (assignee.type !== "team" || teams.length === 0 || !matchedTeam) return;
    const enriched = buildTeamAssignee(matchedTeam);
    if (
      assignee.avatar !== enriched.avatar ||
      assignee.teamId !== enriched.teamId ||
      assignee.subtitle !== enriched.subtitle
    ) {
      setAssignee(enriched);
    }
  }, [assignee, matchedTeam, setAssignee, teams.length]);

  const teamDisplayProfile = useMemo(() => {
    if (assignee.type !== "team") return undefined;
    const team =
      matchedTeam ??
      teams.find((item) => item.name === assignee.name?.trim()) ??
      (assignee.teamId
        ? teams.find((item) => item.id === assignee.teamId?.trim())
        : undefined);
    if (!team) return undefined;
    return resolveTeamRepresentativeProfile(team, employees);
  }, [assignee.type, assignee.name, assignee.teamId, matchedTeam, teams, employees]);

  const visibleEmployees = useMemo(
    () =>
      dedupeEmployees(
        employees.filter((emp) => {
          const label = resolveEmployeeDisplayName(emp);
          return label && !isInternalAgentId(label);
        }),
      ),
    [employees],
  );

  const modelOptions = useMemo(() => {
    const options: Array<{
      providerId: string;
      modelId: string;
      label: string;
    }> = [];

    providers.forEach((provider) => {
      const configured =
        Boolean(provider.api_key_configured) || !provider.require_api_key;
      if (!configured) return;

      (provider.models ?? []).forEach((model) => {
        options.push({
          providerId: provider.id,
          modelId: model.id,
          label: `${provider.name} / ${model.name || model.id}`,
        });
      });
    });

    return options;
  }, [providers]);

  const skillLabel =
    skillNames.length === 0
      ? "选择技能"
      : skillNames.length === 1
        ? skillNames[0]
        : skillNames.length === 2
          ? `${skillNames[0]}、${skillNames[1]}`
          : `技能·${skillNames.length}`;

  const modelLabel = modelAuto ? "Auto" : modelName || "Auto";

  const pickAssignee = (next: Assignee) => {
    setAssignee(next);
    setOpenMenu(null);
  };

  const toggleMenu = (menu: Exclude<MenuId, null>) => (e: React.MouseEvent) => {
    e.stopPropagation();
    setOpenMenu((m) => (m === menu ? null : menu));
  };

  const isStop = streaming;
  const handlePrimaryClick = () => {
    if (isStop) {
      onStop?.();
      return;
    }
    onSend();
  };

  const defaultAssignee = getDefaultAssignee();
  const assigneeSelectedId =
    assignee.type === "default"
      ? "default"
      : assignee.type === "team"
        ? assignee.teamId || assignee.name
        : assignee.agentId || assignee.name;

  const employeeSections = useMemo(() => {
    const sections = [];
    if (visibleEmployees.length > 0) {
      sections.push({
        label: "员工",
        options: visibleEmployees.map((emp) => ({
          id: employeeOptionId(emp),
          label: resolveEmployeeDisplayName(emp),
          subtitle: emp.desc?.slice(0, 48) || undefined,
          avatar: emp.avatar,
        })),
      });
    }
    if (teams.length > 0) {
      sections.push({
        label: "团队",
        options: teams.map((team) => ({
          id: team.id,
          label: team.name,
          subtitle: (team.tags ?? []).slice(0, 2).join(" / ") || "多智能体团队",
          avatar: team.avatar,
        })),
      });
    }
    return sections;
  }, [visibleEmployees, teams]);

  const handleAssigneeSelect = (option: PullUpSelectOption) => {
    const emp = visibleEmployees.find((e) => employeeOptionId(e) === option.id);
    if (emp) {
      pickAssignee(buildEmployeeAssignee(emp));
      return;
    }
    const team = teams.find((t) => t.id === option.id);
    if (team) {
      pickAssignee(buildTeamAssignee(team));
    }
  };

  const modelSelectedId = modelAuto
    ? "auto"
    : modelProviderId && modelId
      ? `${modelProviderId}::${modelId}`
      : undefined;

  return (
    <div
      ref={rootRef}
      className={[
        "wm-composer-toolbar flex flex-nowrap items-center gap-2 text-[12px] text-gray-500",
        showTopDivider ? "mt-3 border-t border-gray-100 pt-3" : "mt-2 pt-0",
      ].join(" ")}
    >
      <div className="wm-composer-toolbar__left relative flex min-w-0 flex-1 flex-nowrap items-center">
        <div className="wm-composer-toolbar__scroll flex min-w-0 flex-1 flex-nowrap items-center gap-1 overflow-x-auto">
          <button
            type="button"
            onClick={toggleMenu("assignee")}
            className={`wm-composer-toolbar-btn inline-flex shrink-0 cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-lg px-2 py-1 text-gray-600 hover:bg-gray-100 hover:text-gray-900 ${
              openMenu === "assignee" ? "wm-composer-toolbar-btn--open" : ""
            }`}
            aria-expanded={openMenu === "assignee"}
            aria-haspopup="listbox"
          >
            {assignee.type === "default" ? (
              <AgentDeskBrandAvatar size="sm" />
            ) : (
              <AgentAvatar
                name={
                  assignee.type === "team"
                    ? teamDisplayProfile?.name ?? getAssigneeLabel(assignee)
                    : getAssigneeLabel(assignee)
                }
                avatar={
                  assignee.type === "team"
                    ? teamDisplayProfile?.avatar ??
                      matchedTeam?.avatar ??
                      assignee.avatar
                    : assignee.avatar
                }
                description={
                  assignee.type === "team"
                    ? teamDisplayProfile?.description ?? matchedTeam?.desc ?? ""
                    : assignee.subtitle ?? ""
                }
                portraitName={
                  assignee.type === "team"
                    ? teamDisplayProfile?.portraitName
                    : undefined
                }
                portraitDescription={
                  assignee.type === "team"
                    ? teamDisplayProfile?.portraitDescription
                    : undefined
                }
                role={
                  assignee.type === "team"
                    ? teamDisplayProfile?.role ?? "team"
                    : "employee"
                }
                size="sm"
              />
            )}
            <span className="max-w-[9rem] truncate">{getAssigneeLabel(assignee)}</span>
            <ChevronDown />
          </button>

          <button
            type="button"
            onClick={toggleMenu("model")}
            className={`wm-composer-toolbar-btn inline-flex shrink-0 cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-lg px-2 py-1 text-gray-600 hover:bg-gray-100 hover:text-gray-900 ${
              openMenu === "model" ? "wm-composer-toolbar-btn--open" : ""
            }`}
            aria-expanded={openMenu === "model"}
          >
            <span className="max-w-[8rem] truncate">{modelLabel}</span>
            <ChevronDown />
          </button>

          <button
            type="button"
            onClick={toggleMenu("skills")}
            className={`wm-composer-toolbar-btn inline-flex shrink-0 cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-lg px-2 py-1 text-gray-600 hover:bg-gray-100 hover:text-gray-900 ${
              openMenu === "skills" ? "wm-composer-toolbar-btn--open" : ""
            }`}
            aria-expanded={openMenu === "skills"}
          >
            <span className="max-w-[7rem] truncate">{skillLabel}</span>
            <ChevronDown />
          </button>
        </div>

        <PullUpSelect
          open={openMenu === "assignee"}
          headerTitle="AgentDesk企伴"
          headerSubtitle={defaultAssignee.subtitle}
          headerSelected={isSameAssignee(assignee, defaultAssignee)}
          onHeaderSelect={() => setAssignee(defaultAssignee)}
          onClose={() => setOpenMenu(null)}
          sections={employeeSections}
          selectedId={assigneeSelectedId}
          onSelect={handleAssigneeSelect}
          className="left-0"
          widthClass="w-[280px]"
        />

        <PullUpSelect
          open={openMenu === "model"}
          headerTitle="模型"
          sections={[
            {
              options: [
                {
                  id: "auto",
                  label: "Auto",
                  subtitle: "跟随全局配置",
                },
              ],
            },
            ...(modelOptions.length > 0
              ? [
                  {
                    label: "已配置模型",
                    options: modelOptions.map((opt) => ({
                      id: `${opt.providerId}::${opt.modelId}`,
                      label: opt.label,
                    })),
                  },
                ]
              : []),
          ]}
          selectedId={modelSelectedId}
          onSelect={(option) => {
            if (option.id === "auto") {
              setModelAuto(true);
              setOpenMenu(null);
              return;
            }
            const opt = modelOptions.find(
              (o) => `${o.providerId}::${o.modelId}` === option.id,
            );
            if (!opt) return;
            void modelConfigApi
              .setActiveModel(opt.providerId, opt.modelId)
              .then(() => {
                setModel(opt.providerId, opt.modelId, opt.label);
                setOpenMenu(null);
              })
              .catch((err) => {
                window.alert(err instanceof Error ? err.message : String(err));
              });
          }}
          className="left-14"
          widthClass="w-[280px]"
          footer={
            modelOptions.length === 0 ? (
              <p className="px-2 py-1.5 text-[11px] text-gray-400">
                暂无已配置模型，请前往设置填写 API Key
              </p>
            ) : undefined
          }
        />

        <PullUpSelect
          open={openMenu === "skills"}
          iconMode="skill"
          headerTitle="不使用技能"
          headerSubtitle="不附加任何技能"
          headerSelected={skillNames.length === 0}
          onHeaderSelect={() => setSkillNames([])}
          onClose={() => setOpenMenu(null)}
          sections={[
            {
              label: "技能",
              options: skills.map((skill) => ({
                id: skill.name,
                label: skill.name,
                icon: skill.icon,
                description: skill.description,
                subtitle: skillNames.includes(skill.name)
                  ? "已启用"
                  : skill.description?.slice(0, 48) || undefined,
              })),
            },
          ]}
          selectedIds={skillNames}
          onSelect={(option) => toggleSkill(option.id)}
          className="left-[172px]"
          widthClass="w-[280px]"
          footer={
            skills.length === 0 ? (
              <p className="px-2 py-1.5 text-[11px] text-gray-400">暂无可用技能</p>
            ) : (
              <p className="px-2 py-1 text-[11px] text-gray-400">点击切换，可多选</p>
            )
          }
        />
      </div>

      <div className="flex shrink-0 flex-nowrap items-center gap-1.5 border-l border-gray-100 pl-2">
        <label className="inline-flex shrink-0 cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-lg px-2 py-1 text-gray-600 hover:bg-gray-100">
          <input
            type="checkbox"
            checked={planMode}
            onChange={(e) => setPlanMode(e.target.checked)}
            className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
          />
          <span>计划模式</span>
        </label>
        {taskId && onWorkspaceToggle ? (
          <button
            type="button"
            onClick={onWorkspaceToggle}
            className={`wm-composer-toolbar-btn inline-flex shrink-0 cursor-pointer items-center gap-1 whitespace-nowrap rounded-lg px-2 py-1 hover:bg-gray-100 ${
              workspaceOpen ? "bg-emerald-50 text-emerald-700" : "text-gray-600"
            }`}
            title="工作空间"
          >
            <span className="max-w-[6rem] truncate">工作空间</span>
          </button>
        ) : null}
        <button
          id={submitButtonId}
          type="button"
          onClick={handlePrimaryClick}
          disabled={disabled || (sending && !isStop)}
          className={`wm-composer-send inline-flex shrink-0 cursor-pointer items-center justify-center gap-1.5 whitespace-nowrap rounded-xl px-3.5 py-1.5 text-[13px] font-medium shadow-sm transition-colors duration-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-500 disabled:cursor-not-allowed disabled:opacity-45 ${
            isStop ? "wm-composer-send--stop" : "wm-composer-send--send"
          }`}
          aria-label={isStop ? "停止生成" : "发送消息"}
        >
          <span className="wm-composer-send__label">{isStop ? "停止" : "发送"}</span>
        </button>
      </div>
    </div>
  );
}
