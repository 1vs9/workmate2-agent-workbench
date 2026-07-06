import { useCallback, useState } from "react";
import {
  Badge,
  Button,
  Card,
  Col,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
  message,
} from "antd";
import { useAsyncList } from "../../hooks/useAsyncList";
import PageError from "../../components/layout/PageError";
import PageHeader from "../../components/layout/PageHeader";
import { mcpApi, type McpClient, type McpPreset, type McpUpsertBody } from "../../api/mcp";

interface McpFormValues {
  name: string;
  description?: string;
  transport: string;
  url?: string;
  command?: string;
  argsText?: string;
  enabled: boolean;
}

export default function McpPage() {
  const loader = useCallback(() => mcpApi.listMcp(), []);
  const { data, loading, error, reload } = useAsyncList<McpClient>(loader);

  const presetLoader = useCallback(() => mcpApi.listPresets(), []);
  const {
    data: presets,
    loading: presetsLoading,
    error: presetsError,
    reload: reloadPresets,
  } = useAsyncList<McpPreset>(presetLoader);

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<McpClient | null>(null);
  const [saving, setSaving] = useState(false);
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [form] = Form.useForm<McpFormValues>();

  const transport = Form.useWatch("transport", form);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ transport: "stdio", enabled: true });
    setOpen(true);
  };

  const openEdit = (item: McpClient) => {
    setEditing(item);
    form.setFieldsValue({
      name: item.name,
      description: item.description,
      transport: item.transport || "stdio",
      url: item.url,
      command: item.command,
      argsText: (item.args ?? []).join(" "),
      enabled: item.enabled,
    });
    setOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    const body: McpUpsertBody = {
      name: values.name,
      description: values.description,
      transport: values.transport,
      url: values.url,
      command: values.command,
      args: (values.argsText ?? "").split(/\s+/).filter(Boolean),
      enabled: values.enabled,
    };
    setSaving(true);
    try {
      await mcpApi.upsertMcp(body);
      message.success(editing ? "已更新" : "已添加");
      setOpen(false);
      reload();
      reloadPresets();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (item: McpClient) => {
    try {
      await mcpApi.deleteMcp(item.key || item.name);
      message.success("已删除");
      reload();
      reloadPresets();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    }
  };

  const handleInstallPreset = async (preset: McpPreset) => {
    setInstallingId(preset.id);
    try {
      await mcpApi.installPreset(preset.id);
      message.success(`已添加 ${preset.name}`);
      reload();
      reloadPresets();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setInstallingId(null);
    }
  };

  const handleRefresh = () => {
    reload();
    reloadPresets();
  };

  return (
    <>
      <PageHeader
        title="MCP 工具"
        subtitle="连接外部工具与服务，扩展智能体执行能力"
        actions={
          <Space>
            <Button onClick={handleRefresh} loading={loading || presetsLoading}>
              刷新
            </Button>
            <Button type="primary" onClick={openCreate}>
              自定义 MCP 工具
            </Button>
          </Space>
        }
      />

      {error ? <PageError message={error} /> : null}
      {presetsError ? <PageError message={presetsError} /> : null}

      <Typography.Title level={5} className="!mb-3 !mt-0">
        内置 MCP
      </Typography.Title>
      <Typography.Paragraph type="secondary" className="!mb-4 text-[13px]">
        一键添加 QwenPaw 官方推荐的 MCP 服务。部分服务需要配置 API Key（如 Tavily 需设置环境变量{" "}
        <Typography.Text code>TAVILY_API_KEY</Typography.Text>）。
      </Typography.Paragraph>

      <Row gutter={[16, 16]} className="wm-card-grid">
        {presets.map((preset) => (
          <Col key={preset.id} xs={24} md={12} xl={8}>
            <Card
              size="small"
              className="wm-card h-full"
              title={
                <Space>
                  <Badge status={preset.installed ? "success" : "default"} />
                  {preset.name}
                </Space>
              }
              extra={
                preset.installed ? (
                  <Tag color="green">已添加</Tag>
                ) : (
                  <Button
                    type="primary"
                    size="small"
                    loading={installingId === preset.id}
                    onClick={() => void handleInstallPreset(preset)}
                  >
                    添加
                  </Button>
                )
              }
            >
              <p className="wm-card-desc line-clamp-3 mb-2 text-[13px] leading-relaxed text-gray-500">
                {preset.description}
              </p>
              {preset.requiresApiKey ? (
                <Typography.Text type="warning" className="text-xs">
                  需要 API Key：{preset.requiresApiKey}
                </Typography.Text>
              ) : null}
            </Card>
          </Col>
        ))}
      </Row>

      <Typography.Title level={5} className="!mb-3 !mt-8">
        已配置的 MCP
      </Typography.Title>

      {!loading && data.length === 0 && !error ? (
        <Typography.Text type="secondary">
          暂无 MCP 服务，可从上方内置列表添加，或点击右上角「自定义 MCP 工具」。
        </Typography.Text>
      ) : null}

      <Row gutter={[16, 16]} className="wm-card-grid mt-4">
        {data.map((item) => (
          <Col key={item.key || item.name} xs={24} md={12} xl={8}>
            <Card
              size="small"
              className="wm-card h-full"
              title={
                <Space>
                  <Badge status={item.enabled ? "success" : "default"} />
                  {item.name}
                </Space>
              }
              extra={
                <Space>
                  <Button size="small" type="text" onClick={() => openEdit(item)}>
                    编辑
                  </Button>
                  <Popconfirm
                    title="确认删除？"
                    onConfirm={() => handleDelete(item)}
                  >
                    <Button size="small" type="text" danger>
                      删除
                    </Button>
                  </Popconfirm>
                </Space>
              }
            >
              <p className="wm-card-desc line-clamp-2 mb-2 text-[13px] leading-relaxed text-gray-500">
                {item.description || "—"}
              </p>
              <Typography.Text code className="text-xs">
                {item.transport === "stdio"
                  ? `stdio · ${item.command || "—"}`
                  : `${item.transport || "http"} · ${item.url || "—"}`}
              </Typography.Text>
            </Card>
          </Col>
        ))}
      </Row>

      <Modal
        title={editing ? "编辑 MCP 工具" : "添加 MCP 工具"}
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
            <Input placeholder="如：filesystem" disabled={!!editing} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input placeholder="简要描述" />
          </Form.Item>
          <Form.Item name="transport" label="传输方式">
            <Select
              options={[
                { value: "stdio", label: "stdio（本地命令）" },
                { value: "sse", label: "sse（HTTP）" },
                { value: "streamable_http", label: "streamable_http" },
              ]}
            />
          </Form.Item>
          {transport === "stdio" ? (
            <>
              <Form.Item name="command" label="启动命令">
                <Input placeholder="如：npx" />
              </Form.Item>
              <Form.Item name="argsText" label="参数（空格分隔）">
                <Input placeholder="如：-y @modelcontextprotocol/server-filesystem" />
              </Form.Item>
            </>
          ) : (
            <Form.Item name="url" label="服务地址">
              <Input placeholder="https://..." />
            </Form.Item>
          )}
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
