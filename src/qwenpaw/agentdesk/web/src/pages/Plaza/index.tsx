import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Col,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Space,
  Spin,
  message,
} from "antd";
import { useNavigate } from "react-router-dom";
import AgentTeamCard from "../../components/agents/AgentTeamCard";
import CategoryFilterTabs from "../../components/agents/CategoryFilterTabs";
import PageError from "../../components/layout/PageError";
import PageHeader from "../../components/layout/PageHeader";
import SkillPickerField from "../../components/skills/SkillPickerField";
import {
  plazaApi,
  type PlazaCard,
} from "../../api/plaza";
import { skillsApi, type SkillItem } from "../../api/skills";
import { useAppStore } from "../../store/appStore";
import { useComposerStore } from "../../store/composerStore";
import { useReferenceDataStore } from "../../store/referenceDataStore";
import { buildEmployeeAssignee } from "../../types/assignee";
import { openDispatchTaskFlow } from "../../utils/openDispatchTaskFlow";
import { openEmployeeCreateFlow } from "../../utils/openEmployeeCreateFlow";
import { syncEmployeeSkills } from "../../utils/employeeSkillSync";

const HIDDEN = new Set([
  "default",
  "AgentDesk企伴",
  "AgentDesk",
  "Default Agent",
]);

const ALL_CATEGORY = "全部";

function plazaSubtitle(card: PlazaCard): string {
  if (card.author?.trim()) return card.author.trim();
  const tag = card.tags?.find((t) => t.trim() && t !== "AgentDesk");
  return tag?.trim() || "AgentDesk 岗位";
}

function isFeaturedCard(card: PlazaCard): boolean {
  if (card.author?.trim()) return true;
  return (card.tags ?? []).some((tag) => /特邀|专家|推荐/.test(tag));
}

interface PlazaFormValues {
  name: string;
  desc: string;
  skillNames: string[];
}

export default function PlazaPage() {
  const navigate = useNavigate();
  const prependTask = useAppStore((s) => s.prependTask);
  const setActiveTaskId = useAppStore((s) => s.setActiveTaskId);
  const resetForNewChat = useComposerStore((s) => s.resetForNewChat);

  const cards = useReferenceDataStore((s) => s.plazaCards);
  const employees = useReferenceDataStore((s) => s.employees);
  const refLoading = useReferenceDataStore((s) => s.loading);
  const ensureLoaded = useReferenceDataStore((s) => s.ensureLoaded);
  const refreshPlaza = useReferenceDataStore((s) => s.refreshPlaza);
  const refreshEmployees = useReferenceDataStore((s) => s.refreshEmployees);

  const [plazaRefreshing, setPlazaRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void ensureLoaded().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : String(err));
    });
  }, [ensureLoaded]);

  const reloadPlaza = useCallback(() => {
    setPlazaRefreshing(true);
    setError(null);
    void refreshPlaza()
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => setPlazaRefreshing(false));
  }, [refreshPlaza]);

  const reloadEmployees = useCallback(() => {
    void refreshEmployees();
  }, [refreshEmployees]);

  const [poolSkills, setPoolSkills] = useState<SkillItem[]>([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  const ensureSkillsLoaded = useCallback(async () => {
    if (poolSkills.length > 0 || skillsLoading) return;
    setSkillsLoading(true);
    try {
      const skills = await skillsApi.listSkills();
      setPoolSkills(skills ?? []);
    } catch {
      // Edit modal can still save without the picker list.
    } finally {
      setSkillsLoading(false);
    }
  }, [poolSkills.length, skillsLoading]);

  const selectableSkills = useMemo(
    () => poolSkills.filter((s) => s.name.trim()),
    [poolSkills],
  );

  const joinedNames = useMemo(
    () => new Set(employees.map((e) => e.name)),
    [employees],
  );

  const visibleCards = useMemo(
    () => cards.filter((c) => !HIDDEN.has(c.name)),
    [cards],
  );

  const categories = useMemo(() => {
    const tags = new Set<string>();
    for (const card of visibleCards) {
      for (const tag of card.tags ?? []) {
        const trimmed = tag.trim();
        if (trimmed && trimmed !== "AgentDesk") tags.add(trimmed);
      }
    }
    return [ALL_CATEGORY, ...Array.from(tags).sort()];
  }, [visibleCards]);

  const [category, setCategory] = useState(ALL_CATEGORY);
  const filteredCards = useMemo(() => {
    if (category === ALL_CATEGORY) return visibleCards;
    return visibleCards.filter((card) => (card.tags ?? []).includes(category));
  }, [visibleCards, category]);

  const [open, setOpen] = useState(false);
  const [editCard, setEditCard] = useState<PlazaCard | null>(null);
  const [saving, setSaving] = useState(false);
  const [creatingEmployee, setCreatingEmployee] = useState(false);
  const [dispatching, setDispatching] = useState<string | null>(null);
  const [form] = Form.useForm<PlazaFormValues>();

  const plazaLoading = refLoading && visibleCards.length === 0;

  const isJoined = (card: PlazaCard) => joinedNames.has(card.name);

  const handleJoin = async (card: PlazaCard) => {
    try {
      await plazaApi.joinPlaza(card.name);
      message.success(`已将「${card.name}」加入员工列表`);
      reloadEmployees();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    }
  };

  const handleDispatch = async (card: PlazaCard) => {
    if (dispatching) return;
    setDispatching(card.name);
    try {
      await openDispatchTaskFlow({
        assignee: buildEmployeeAssignee(card),
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

  const openEdit = (card: PlazaCard) => {
    void ensureSkillsLoaded();
    const employee = employees.find((e) => e.name === card.name);
    setEditCard(card);
    form.setFieldsValue({
      name: card.name || employee?.name || "",
      desc: card.desc || employee?.desc || "",
      skillNames: employee?.skills?.length
        ? employee.skills
        : (card.skills ?? []),
    });
    setOpen(true);
  };

  const handleAddEmployee = async () => {
    if (creatingEmployee) return;
    setCreatingEmployee(true);
    try {
      await openEmployeeCreateFlow({
        resetForNewChat,
        prependTask,
        setActiveTaskId,
        navigate,
      });
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setCreatingEmployee(false);
    }
  };

  const handleSave = async () => {
    if (saving) return;
    let values: PlazaFormValues;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    const skillNames = (values.skillNames ?? []).filter(Boolean);
    const body = {
      name: values.name,
      desc: values.desc,
      tags: editCard!.tags?.length ? editCard!.tags : ["AgentDesk"],
      skills: skillNames,
    };
    setSaving(true);
    try {
      if (joinedNames.has(editCard!.name)) {
        const { failed } = await syncEmployeeSkills(editCard!.name, skillNames, {
          desc: values.desc,
          tags: body.tags,
        });
        if (failed.length > 0) {
          message.warning(
            `已保存，但以下技能未能挂载：${failed.join("、")}。` +
              (failed.some((name) => name.toLowerCase() === "python")
                ? "「python」不是内置技能名，请改用 file_reader 或从技能市场安装对应技能。"
                : "请确认技能已在技能池中，或使用正式名称（excel → xlsx）。"),
          );
        } else {
          message.success("已更新");
        }
      } else {
        await plazaApi.updatePlaza(editCard!.name, body);
        message.success("已更新");
      }
      setOpen(false);
      reloadPlaza();
      reloadEmployees();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (card: PlazaCard) => {
    try {
      const result = await plazaApi.deletePlazaCard(card.name);
      if (!result.deleted) {
        message.error("未能删除该岗位，请刷新后重试");
        return;
      }
      message.success("已删除");
      setOpen(false);
      setEditCard(null);
      reloadPlaza();
      reloadEmployees();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <>
      <PageHeader
        title="岗位智能体"
        subtitle="招募数字员工，派发任务到指定岗位"
        actions={
          <Space>
            <Button onClick={reloadPlaza} loading={plazaRefreshing}>
              刷新
            </Button>
            <Button
              type="primary"
              loading={creatingEmployee}
              onClick={() => void handleAddEmployee()}
            >
              添加员工
            </Button>
          </Space>
        }
      />

      {error ? <PageError message={error} /> : null}

      {plazaLoading ? (
        <div className="wm-page-loading">
          <Spin tip="加载岗位智能体…" />
        </div>
      ) : null}

      <CategoryFilterTabs
        categories={categories}
        value={category}
        onChange={setCategory}
      />

      <Row gutter={[16, 16]} className="wm-card-grid">
        {filteredCards.map((card) => {
          const joined = isJoined(card);
          const featured = isFeaturedCard(card);
          return (
            <Col key={card.name} xs={24} sm={12} lg={8} xl={6}>
              <AgentTeamCard
                name={card.name}
                avatar={card.avatar}
                subtitle={plazaSubtitle(card)}
                description={card.desc}
                tags={(card.tags ?? []).filter((t) => t.trim() && t !== "AgentDesk")}
                badge={
                  !joined && featured
                    ? { label: "特邀专家", variant: "featured" }
                    : undefined
                }
                onClick={() => openEdit(card)}
                actions={[
                  joined
                    ? {
                        key: "joined",
                        label: "已加入",
                        variant: "muted",
                        onClick: () => {},
                      }
                    : {
                        key: "join",
                        label: "加入",
                        variant: "secondary",
                        onClick: () => void handleJoin(card),
                      },
                  {
                    key: "dispatch",
                    label: "派发",
                    variant: "primary",
                    loading: dispatching === card.name,
                    onClick: () => void handleDispatch(card),
                  },
                ]}
              />
            </Col>
          );
        })}
      </Row>

      <Modal
        title="编辑员工"
        open={open}
        onCancel={() => setOpen(false)}
        destroyOnClose
        footer={
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Popconfirm
              title="确认删除该岗位？"
              onConfirm={() => editCard && void handleDelete(editCard)}
              okButtonProps={{ danger: true }}
              getPopupContainer={(trigger) => trigger.parentElement ?? document.body}
            >
              <Button danger disabled={!editCard}>
                删除
              </Button>
            </Popconfirm>
            <Space>
              <Button onClick={() => setOpen(false)}>取消</Button>
              <Button type="primary" loading={saving} onClick={() => void handleSave()}>
                保存
              </Button>
            </Space>
          </div>
        }
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: "请输入名称" }]}
          >
            <Input placeholder="如：销售助理" disabled={Boolean(editCard)} />
          </Form.Item>
          <Form.Item
            name="desc"
            label="职责描述 / 提示词"
            rules={[{ required: true, message: "请输入职责描述" }]}
          >
            <Input.TextArea rows={4} placeholder="该员工的职责与能力" />
          </Form.Item>
          <Form.Item name="skillNames">
            <SkillPickerField
              skills={selectableSkills}
              modalTitle="选择员工技能"
            />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
