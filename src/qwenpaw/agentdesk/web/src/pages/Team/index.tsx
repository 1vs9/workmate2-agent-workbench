import { useCallback, useMemo, useState } from "react";
import {
  Button,
  Col,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Segmented,
  Space,
  Tooltip,
  message,
} from "antd";
import { useNavigate } from "react-router-dom";
import AgentTeamCard from "../../components/agents/AgentTeamCard";
import PageError from "../../components/layout/PageError";
import PageHeader from "../../components/layout/PageHeader";
import { useAsyncList } from "../../hooks/useAsyncList";
import { teamsApi, type Team, type CreateTeamBody } from "../../api/teams";
import { plazaApi, type Employee } from "../../api/plaza";
import { skillsApi, type SkillItem } from "../../api/skills";
import SkillPickerField from "../../components/skills/SkillPickerField";
import { useAppStore } from "../../store/appStore";
import { useComposerStore } from "../../store/composerStore";
import { useReferenceDataStore } from "../../store/referenceDataStore";
import { buildEmployeeAssignee, buildTeamAssignee } from "../../types/assignee";
import { openDispatchTaskFlow } from "../../utils/openDispatchTaskFlow";
import MemberPickerField from "../../components/team/MemberPickerField";
import { AgentDeskSparkles } from "../../components/branding/AgentDeskIcon";
import {
  TEAM_LEADER_PROMPT_VALIDATION_MESSAGES,
  generateTeamLeaderPrompt,
} from "../../utils/generateTeamLeaderPrompt";
import {
  countTeamWorkers,
  normalizeTeamWorkers,
  splitTeamRoster,
} from "../../utils/teamForm";
import { syncEmployeeSkills } from "../../utils/employeeSkillSync";

interface TeamFormValues {
  name: string;
  teamPrompt?: string;
  members: string[];
}

interface EmployeeFormValues {
  name: string;
  desc?: string;
  skillNames?: string[];
}

export default function TeamPage() {
  const navigate = useNavigate();
  const prependTask = useAppStore((s) => s.prependTask);
  const setActiveTaskId = useAppStore((s) => s.setActiveTaskId);
  const resetForNewChat = useComposerStore((s) => s.resetForNewChat);
  const [section, setSection] = useState<"team-list" | "employee-list">(
    "team-list",
  );

  const teamsLoader = useCallback(() => teamsApi.listTeams(), []);
  const employeesLoader = useCallback(() => plazaApi.listEmployees(), []);
  const {
    data: teams,
    loading,
    error,
    reload: reloadTeams,
  } = useAsyncList<Team>(teamsLoader);
  const {
    data: employees,
    loading: employeesLoading,
    reload: reloadEmployees,
  } = useAsyncList<Employee>(employeesLoader);

  const skillsLoader = useCallback(() => skillsApi.listSkills(), []);
  const { data: poolSkills } = useAsyncList<SkillItem>(skillsLoader);
  const selectableSkills = useMemo(
    () => poolSkills.filter((skill) => skill.name.trim()),
    [poolSkills],
  );

  const [dispatching, setDispatching] = useState<string | null>(null);

  const handleDispatchTeam = async (team: Team) => {
    if (dispatching) return;
    setDispatching(`team:${team.id}`);
    try {
      await openDispatchTaskFlow({
        assignee: buildTeamAssignee(team),
        resetForNewChat,
        prependTask,
        setActiveTaskId,
        navigate,
      });
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setDispatching(null);
    }
  };

  const handleDispatchEmployee = async (emp: Employee) => {
    if (dispatching) return;
    setDispatching(`emp:${emp.name}`);
    try {
      await openDispatchTaskFlow({
        assignee: buildEmployeeAssignee(emp),
        resetForNewChat,
        prependTask,
        setActiveTaskId,
        navigate,
      });
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setDispatching(null);
    }
  };

  const [empOpen, setEmpOpen] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState<Employee | null>(null);
  const [empSaving, setEmpSaving] = useState(false);
  const [empForm] = Form.useForm<EmployeeFormValues>();

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Team | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<TeamFormValues>();

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ members: [] });
    setOpen(true);
  };

  const openEdit = (team: Team) => {
    const { workers } = splitTeamRoster(team);
    setEditing(team);
    form.setFieldsValue({
      name: team.name,
      teamPrompt: team.desc,
      members: workers,
    });
    setOpen(true);
  };

  const handleGenerateTeamPrompt = () => {
    const teamName = String(form.getFieldValue("name") ?? "").trim();
    const workers = normalizeTeamWorkers(
      undefined,
      form.getFieldValue("members"),
    );
    const memberDetails = workers.map((name) => {
      const employee = employees.find((emp) => emp.name === name);
      return { name, desc: employee?.desc };
    });

    const result = generateTeamLeaderPrompt({
      teamName,
      members: memberDetails,
    });

    if (!result.ok) {
      message.warning(TEAM_LEADER_PROMPT_VALIDATION_MESSAGES[result.reason]);
      return;
    }

    form.setFieldValue("teamPrompt", result.prompt);
    message.success("已生成团队提示词");
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    const workers = normalizeTeamWorkers(undefined, values.members);
    const body: CreateTeamBody = {
      name: values.name,
      tags: editing?.tags?.length ? editing.tags : ["AgentDesk"],
      desc: values.teamPrompt,
      members: workers,
    };
    setSaving(true);
    try {
      if (editing) {
        await teamsApi.updateTeam(editing.id, body);
        message.success("已更新");
      } else {
        await teamsApi.createTeam(body);
        message.success("已创建");
      }
      setOpen(false);
      reloadTeams();
      useReferenceDataStore.getState().invalidate();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (team: Team) => {
    try {
      await teamsApi.deleteTeam(team.id);
      message.success("已删除");
      setOpen(false);
      setEditing(null);
      reloadTeams();
      useReferenceDataStore.getState().invalidate();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    }
  };

  const openEmployeeEdit = (emp: Employee) => {
    setEditingEmployee(emp);
    empForm.setFieldsValue({
      name: emp.name,
      desc: emp.desc,
      skillNames: emp.skills ?? [],
    });
    setEmpOpen(true);
  };

  const saveEmployee = async () => {
    if (!editingEmployee || empSaving) return;
    setEmpSaving(true);
    try {
      const values = await empForm.validateFields();
      const skillNames = (values.skillNames ?? []).filter(Boolean);
      const { failed } = await syncEmployeeSkills(editingEmployee.name, skillNames, {
        desc: values.desc,
      });
      if (failed.length > 0) {
        message.warning(
          `已保存，但以下技能未能挂载：${failed.join("、")}。` +
            (failed.some((name) => name.toLowerCase() === "python")
              ? "「python」不是内置技能名，请改用 file_reader 或从技能市场安装对应技能。"
              : "请确认技能已在技能池中，或使用正式名称（excel → xlsx）。"),
        );
      } else {
        message.success("已更新员工");
      }
      setEmpOpen(false);
      reloadEmployees();
      useReferenceDataStore.getState().invalidate();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setEmpSaving(false);
    }
  };

  const deleteEmployee = async (emp: Employee) => {
    try {
      const result = await plazaApi.deleteEmployee(emp.name);
      if (!result.deleted) {
        message.error("未能删除该员工，请刷新后重试");
        return;
      }
      message.success("已删除员工");
      setEmpOpen(false);
      setEditingEmployee(null);
      reloadEmployees();
      useReferenceDataStore.getState().invalidate();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <>
      <PageHeader
        title="多智能体团队"
        subtitle="组建协作团队，或管理已加入的员工"
      />

      <div className="wm-page-toolbar">
        <Segmented
          value={section}
          onChange={(v) => setSection(v as typeof section)}
          options={[
            { label: "团队列表", value: "team-list" },
            { label: "员工列表", value: "employee-list" },
          ]}
        />
        <div className="wm-page-toolbar__actions">
          {section === "team-list" ? (
            <>
              <Button onClick={reloadTeams} loading={loading}>
                刷新
              </Button>
              <Button type="primary" onClick={openCreate}>
                新建团队
              </Button>
            </>
          ) : (
            <Button onClick={reloadEmployees} loading={employeesLoading}>
              刷新
            </Button>
          )}
        </div>
      </div>

      {error ? <PageError message={error} /> : null}

      {section === "team-list" ? (
        <Row gutter={[16, 16]} className="wm-card-grid">
          {teams.map((team) => (
            <Col key={team.id} xs={24} sm={12} lg={8} xl={6}>
              <AgentTeamCard
                name={team.name}
                avatar={team.avatar}
                avatarRole="team"
                subtitle="AgentDesk 协作团队"
                description={team.desc}
                tags={(team.tags ?? []).filter((t) => t.trim() && t !== "AgentDesk")}
                meta={`${team.leader || "（自动创建）"} · 执行者 ${countTeamWorkers(team)} 人`}
                onClick={() => openEdit(team)}
                actions={[
                  {
                    key: "dispatch",
                    label: "派发",
                    variant: "primary",
                    loading: dispatching === `team:${team.id}`,
                    onClick: () => void handleDispatchTeam(team),
                  },
                ]}
              />
            </Col>
          ))}
          {!loading && teams.length === 0 && (
            <Col span={24}>
              <Empty description="暂无团队，点击右上角「新建团队」创建。" />
            </Col>
          )}
        </Row>
      ) : (
        <Row gutter={[16, 16]} className="wm-card-grid">
          {employees.map((emp) => (
            <Col key={emp.name} xs={24} sm={12} lg={8} xl={6}>
              <AgentTeamCard
                name={emp.name}
                avatar={emp.avatar}
                subtitle="已加入员工"
                description={emp.desc}
                tags={(emp.skills ?? []).slice(0, 4)}
                onClick={() => openEmployeeEdit(emp)}
                actions={[
                  {
                    key: "dispatch",
                    label: "派发",
                    variant: "primary",
                    loading: dispatching === `emp:${emp.name}`,
                    onClick: () => void handleDispatchEmployee(emp),
                  },
                ]}
              />
            </Col>
          ))}
          {employees.length === 0 && (
            <Col span={24}>
              <Empty description="暂无员工，去「岗位智能体」加入员工。" />
            </Col>
          )}
        </Row>
      )}

      <Modal
        title={editing ? "编辑团队" : "新建团队"}
        open={open}
        onCancel={() => setOpen(false)}
        destroyOnClose
        footer={
          <div className="flex flex-wrap items-center justify-between gap-2">
            {editing ? (
              <Popconfirm
                title="确认删除该团队？"
                onConfirm={() => void handleDelete(editing)}
                okButtonProps={{ danger: true }}
              >
                <Button danger>删除</Button>
              </Popconfirm>
            ) : (
              <span />
            )}
            <Space>
              <Button onClick={() => setOpen(false)}>取消</Button>
              <Button type="primary" loading={saving} onClick={() => void handleSave()}>
                {editing ? "保存" : "创建"}
              </Button>
            </Space>
          </div>
        }
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="name"
            label="团队名称"
            rules={[{ required: true, message: "请输入团队名称" }]}
          >
            <Input placeholder="如：增长团队" />
          </Form.Item>
          <Form.Item
            name="teamPrompt"
            label={
              <div className="flex w-full items-center justify-between gap-2">
                <span>团队提示词</span>
                <Tooltip title="根据团队名称与成员一键生成">
                  <Button
                    type="text"
                    size="small"
                    className="!px-1 text-emerald-600 hover:!text-emerald-700"
                    icon={<AgentDeskSparkles size={14} />}
                    onClick={handleGenerateTeamPrompt}
                  >
                    一键生成
                  </Button>
                </Tooltip>
              </div>
            }
          >
            <Input.TextArea
              rows={4}
              placeholder="如：你是增长团队 leader，负责协调投放、内容与数据分析成员，按漏斗阶段拆解任务并汇总结论。"
            />
          </Form.Item>
          <Form.Item
            name="members"
            rules={[
              {
                validator: async (_, members: string[] | undefined) => {
                  const workers = normalizeTeamWorkers(undefined, members);
                  if (workers.length === 0) {
                    throw new Error("请至少选择一名执行者");
                  }
                },
              },
            ]}
          >
            <MemberPickerField employees={employees} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑员工"
        open={empOpen}
        onCancel={() => setEmpOpen(false)}
        destroyOnClose
        footer={
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Popconfirm
              title="确认删除该员工？"
              onConfirm={() => editingEmployee && void deleteEmployee(editingEmployee)}
              okButtonProps={{ danger: true }}
              getPopupContainer={(trigger) => trigger.parentElement ?? document.body}
            >
              <Button danger disabled={!editingEmployee}>
                删除
              </Button>
            </Popconfirm>
            <Space>
              <Button onClick={() => setEmpOpen(false)}>取消</Button>
              <Button type="primary" loading={empSaving} onClick={() => void saveEmployee()}>
                保存
              </Button>
            </Space>
          </div>
        }
      >
        <Form form={empForm} layout="vertical" preserve={false}>
          <Form.Item name="name" label="名称">
            <Input disabled />
          </Form.Item>
          <Form.Item name="desc" label="描述">
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item name="skillNames">
            <SkillPickerField skills={selectableSkills} modalTitle="选择员工技能" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
