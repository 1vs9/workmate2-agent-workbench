import { useCallback, useState } from "react";
import {
  Badge,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Popconfirm,
  Row,
  Segmented,
  Select,
  Space,
  TimePicker,
  Typography,
  message,
} from "antd";
import type { Dayjs } from "dayjs";
import { useAsyncList } from "../../hooks/useAsyncList";
import PageError from "../../components/layout/PageError";
import PageHeader from "../../components/layout/PageHeader";
import {
  automationApi,
  type AutomationJob,
  type CreateJobBody,
  type HistoryItem,
  type Schedule,
} from "../../api/automation";

type ScheduleMode = "periodic" | "interval" | "once";

interface JobFormValues {
  name: string;
  workspace: string;
  prompt: string;
  scheduleMode: ScheduleMode;
  dailyTime?: Dayjs;
  intervalAmount?: number;
  intervalUnit?: "hours" | "minutes";
  runAt?: Dayjs;
}

function buildSchedule(values: JobFormValues): Schedule {
  if (values.scheduleMode === "interval") {
    return {
      mode: "interval",
      interval_amount: values.intervalAmount ?? 1,
      interval_unit: values.intervalUnit ?? "hours",
    };
  }
  if (values.scheduleMode === "once") {
    return {
      mode: "once",
      run_at: values.runAt?.toISOString(),
    };
  }
  // periodic → daily cron at chosen time
  const h = values.dailyTime?.hour() ?? 9;
  const m = values.dailyTime?.minute() ?? 0;
  return { mode: "cron", cron: `${m} ${h} * * *`, timezone: "Asia/Shanghai" };
}

export default function AutomationPage() {
  const jobsLoader = useCallback(() => automationApi.listJobs(), []);
  const historyLoader = useCallback(() => automationApi.listHistory(), []);
  const {
    data: jobs,
    loading,
    error,
    reload: reloadJobs,
  } = useAsyncList<AutomationJob>(jobsLoader);
  const { data: history, reload: reloadHistory } =
    useAsyncList<HistoryItem>(historyLoader);

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<AutomationJob | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<JobFormValues>();
  const scheduleMode = Form.useWatch("scheduleMode", form);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      workspace: "default",
      scheduleMode: "periodic",
      intervalUnit: "hours",
      intervalAmount: 1,
    });
    setOpen(true);
  };

  const openEdit = (job: AutomationJob) => {
    setEditing(job);
    const mode: ScheduleMode =
      job.schedule.mode === "interval"
        ? "interval"
        : job.schedule.mode === "once"
          ? "once"
          : "periodic";
    form.setFieldsValue({
      name: job.name,
      workspace: job.workspace,
      prompt: job.prompt,
      scheduleMode: mode,
      intervalAmount: job.schedule.interval_amount ?? 1,
      intervalUnit: job.schedule.interval_unit ?? "hours",
    });
    setOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    const body: CreateJobBody = {
      name: values.name,
      workspace: values.workspace || "default",
      prompt: values.prompt,
      employee_name: null,
      model_name: null,
      skill_names: [],
      chat_mode: "chat",
      schedule: buildSchedule(values),
      date_range: { start: null, end: null },
    };
    setSaving(true);
    try {
      if (editing) {
        await automationApi.updateJob(editing.id, body);
        message.success("已更新定时任务");
      } else {
        await automationApi.createJob(body);
        message.success("已创建定时任务");
      }
      setOpen(false);
      reloadJobs();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const runJob = async (job: AutomationJob) => {
    try {
      await automationApi.runJob(job.id);
      message.success("已触发运行");
      reloadHistory();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    }
  };

  const togglePause = async (job: AutomationJob) => {
    try {
      if (job.enabled) {
        await automationApi.pauseJob(job.id);
        message.success("已暂停");
      } else {
        await automationApi.resumeJob(job.id);
        message.success("已恢复");
      }
      reloadJobs();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    }
  };

  const deleteJob = async (job: AutomationJob) => {
    try {
      await automationApi.deleteJob(job.id);
      message.success("已删除");
      reloadJobs();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <>
      <PageHeader
        title="自动化"
        subtitle="定时执行任务，自动触发智能体工作流"
        actions={
          <Space>
            <Button onClick={() => { reloadJobs(); reloadHistory(); }} loading={loading}>
              刷新
            </Button>
            <Button type="primary" onClick={openCreate}>
              + 添加
            </Button>
          </Space>
        }
      />

      {error ? <PageError message={error} /> : null}

      <Row gutter={16}>
        <Col xs={24} lg={14}>
          <Card size="small" className="wm-card mb-4" title="已安排">
            <List<AutomationJob>
              dataSource={jobs}
              locale={{
                emptyText: (
                  <Empty description="暂无定时任务，点击右上角「+ 添加」创建。" />
                ),
              }}
              renderItem={(job) => (
                <List.Item
                  actions={[
                    <Button key="run" type="link" onClick={() => runJob(job)}>
                      运行
                    </Button>,
                    <Button key="edit" type="link" onClick={() => openEdit(job)}>
                      编辑
                    </Button>,
                    <Button
                      key="toggle"
                      type="link"
                      onClick={() => togglePause(job)}
                    >
                      {job.enabled ? "暂停" : "恢复"}
                    </Button>,
                    <Popconfirm
                      key="delete"
                      title="确认删除？"
                      onConfirm={() => deleteJob(job)}
                    >
                      <Button type="link" danger>
                        删除
                      </Button>
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    avatar={
                      <Badge status={job.enabled ? "processing" : "warning"} />
                    }
                    title={job.name}
                    description={
                      <Space size="small" wrap>
                        <span>{job.workspace}</span>
                        {job.frequency && <span>· {job.frequency}</span>}
                        {!job.enabled && (
                          <Typography.Text type="warning">已暂停</Typography.Text>
                        )}
                        {job.eta && (
                          <Typography.Text type="secondary">
                            · {job.eta}
                          </Typography.Text>
                        )}
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card size="small" className="wm-card" title="已完成">
            <List<HistoryItem>
              dataSource={history}
              locale={{ emptyText: <Empty description="暂无运行记录。" /> }}
              renderItem={(item) => (
                <List.Item>
                  <List.Item.Meta
                    title={item.name}
                    description={
                      <Space size="small" wrap>
                        <span>{item.workspace}</span>
                        <span>· {item.status}</span>
                        <Typography.Text type="secondary">
                          · {item.time}
                        </Typography.Text>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      <Modal
        title={editing ? "编辑定时任务" : "添加定时任务"}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        destroyOnClose
        width={560}
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="name"
            label="名称"
            rules={[{ required: true, message: "请输入名称" }]}
          >
            <Input placeholder="如：每日简报" />
          </Form.Item>
          <Form.Item name="workspace" label="工作空间">
            <Input placeholder="default" />
          </Form.Item>
          <Form.Item
            name="prompt"
            label="任务指令"
            rules={[{ required: true, message: "请输入任务指令" }]}
          >
            <Input.TextArea rows={3} placeholder="到点要执行的指令" />
          </Form.Item>
          <Form.Item name="scheduleMode" label="调度方式">
            <Segmented
              options={[
                { label: "周期（每日）", value: "periodic" },
                { label: "按间隔", value: "interval" },
                { label: "单次", value: "once" },
              ]}
            />
          </Form.Item>
          {scheduleMode === "periodic" && (
            <Form.Item
              name="dailyTime"
              label="每日执行时间"
              rules={[{ required: true, message: "请选择时间" }]}
            >
              <TimePicker format="HH:mm" style={{ width: "100%" }} />
            </Form.Item>
          )}
          {scheduleMode === "interval" && (
            <Space>
              <Form.Item
                name="intervalAmount"
                label="间隔"
                rules={[{ required: true, message: "请输入间隔" }]}
              >
                <InputNumber min={1} />
              </Form.Item>
              <Form.Item name="intervalUnit" label="单位">
                <Select
                  style={{ width: 120 }}
                  options={[
                    { value: "hours", label: "小时" },
                    { value: "minutes", label: "分钟" },
                  ]}
                />
              </Form.Item>
            </Space>
          )}
          {scheduleMode === "once" && (
            <Form.Item
              name="runAt"
              label="执行时间"
              rules={[{ required: true, message: "请选择执行时间" }]}
            >
              <DatePicker showTime style={{ width: "100%" }} />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </>
  );
}
