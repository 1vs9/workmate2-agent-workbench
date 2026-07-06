import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Form,
  Input,
  Select,
  Space,
  Tag,
  Typography,
  Alert,
  message,
} from "antd";
import {
  modelConfigApi,
  type AgentDeskConfig,
  type Provider,
} from "../../api/modelConfig";
import PageError from "../../components/layout/PageError";
import PageHeader from "../../components/layout/PageHeader";

function isLegacyQwenpawDefault(dir: string | null | undefined): boolean {
  if (!dir) return false;
  const normalized = dir.replace(/\\/g, "/").replace(/\/+$/, "");
  return /\/qwenpaw$/i.test(normalized);
}

function pickDir(saved: string | null | undefined, suggested: string): string {
  return saved && !isLegacyQwenpawDefault(saved) ? saved : suggested;
}

export default function SettingsPage() {
  const [config, setConfig] = useState<AgentDeskConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [savingModel, setSavingModel] = useState(false);
  const [savingProvider, setSavingProvider] = useState(false);
  const [savingDirs, setSavingDirs] = useState(false);

  const [workingDir, setWorkingDir] = useState("");
  const [secretDir, setSecretDir] = useState("");

  const [activeModelKey, setActiveModelKey] = useState<string>();
  const [providerId, setProviderId] = useState<string>();
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");

  const load = () => {
    setLoading(true);
    setError(null);
    modelConfigApi
      .getConfig()
      .then((cfg) => {
        setConfig(cfg);
        setWorkingDir(pickDir(cfg.saved_working_dir, cfg.suggested_working_dir));
        setSecretDir(pickDir(cfg.saved_secret_dir, cfg.suggested_secret_dir));
        if (cfg.active_model) {
          setActiveModelKey(
            `${cfg.active_model.provider_id}::${cfg.active_model.model}`,
          );
        }
        const first = cfg.providers[0];
        if (first) {
          setProviderId(first.id);
          setBaseUrl(first.base_url);
        }
      })
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : String(err)),
      )
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const modelOptions = useMemo(() => {
    if (!config) return [];
    return config.providers.flatMap((p) =>
      p.models.map((m) => ({
        value: `${p.id}::${m.id}`,
        label: `${p.name} / ${m.name}`,
      })),
    );
  }, [config]);

  const currentProvider: Provider | undefined = useMemo(
    () => config?.providers.find((p) => p.id === providerId),
    [config, providerId],
  );

  const handleProviderSelect = (id: string) => {
    setProviderId(id);
    const p = config?.providers.find((x) => x.id === id);
    setBaseUrl(p?.base_url ?? "");
    setApiKey("");
  };

  const handleSaveModel = async () => {
    if (!activeModelKey) return;
    const [pid, model] = activeModelKey.split("::");
    setSavingModel(true);
    try {
      await modelConfigApi.setActiveModel(pid, model);
      message.success("已设置当前模型");
      load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingModel(false);
    }
  };

  const handleSaveProvider = async () => {
    if (!providerId) return;
    setSavingProvider(true);
    try {
      const body: { api_key?: string; base_url?: string } = {};
      if (apiKey) body.api_key = apiKey;
      if (!currentProvider?.freeze_url) body.base_url = baseUrl;
      await modelConfigApi.updateProvider(providerId, body);
      message.success("已保存 Provider 配置");
      setApiKey("");
      load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingProvider(false);
    }
  };

  const handleUseSuggestedDirs = () => {
    if (!config) return;
    setWorkingDir(config.suggested_working_dir);
    setSecretDir(config.suggested_secret_dir);
  };

  const handleSaveDataDirs = async () => {
    if (!workingDir.trim()) {
      message.warning("请填写数据目录");
      return;
    }
    setSavingDirs(true);
    try {
      const result = await modelConfigApi.updateDataDirs({
        working_dir: workingDir.trim(),
        secret_dir: secretDir.trim(),
      });
      message.success(result.message || "已保存数据目录");
      load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setSavingDirs(false);
    }
  };

  return (
    <>
      <PageHeader
        title="配置"
        subtitle="管理模型提供商与 API Key"
      />

      {error ? <PageError message={error} /> : null}

      <Card size="small" className="wm-card mb-4" title="数据目录" loading={loading}>
        <Space direction="vertical" className="w-full" size="middle">
          <Alert
            type="info"
            showIcon
            message="修改后需完全退出 AgentDesk 进程并重新启动。界面保存的配置优先于旧的环境变量。"
          />
          <div>
            <Typography.Text type="secondary">当前运行中：</Typography.Text>
            <div className="mt-1 space-y-1">
              <Typography.Paragraph code className="!mb-0">
                {config?.working_dir || "—"}
              </Typography.Paragraph>
              <Typography.Paragraph code className="!mb-0">
                {config?.secret_dir || "—"}
              </Typography.Paragraph>
            </div>
          </div>
          <Form layout="vertical">
            <Form.Item label="数据目录 (working_dir)">
              <Input
                value={workingDir}
                onChange={(e) => setWorkingDir(e.target.value)}
                placeholder={config?.suggested_working_dir}
              />
            </Form.Item>
            <Form.Item label="密钥目录 (secret_dir)">
              <Input
                value={secretDir}
                onChange={(e) => setSecretDir(e.target.value)}
                placeholder={config?.suggested_secret_dir}
              />
            </Form.Item>
          </Form>
          <Space wrap>
            <Button onClick={handleUseSuggestedDirs} disabled={!config}>
              使用推荐路径（agentdesk）
            </Button>
            <Button
              type="primary"
              onClick={handleSaveDataDirs}
              loading={savingDirs}
            >
              保存并下次启动生效
            </Button>
          </Space>
          {config?.paths_saved ? (
            <Typography.Text type="secondary">
              已保存待生效：{config.saved_working_dir} / {config.saved_secret_dir}
            </Typography.Text>
          ) : null}
        </Space>
      </Card>

      <Card size="small" className="wm-card mb-4" title="当前模型" loading={loading}>
        <Space direction="vertical" className="w-full">
          <div>
            {config?.model_ready ? (
              <Tag color="green">模型就绪</Tag>
            ) : (
              <Tag color="orange">未配置模型</Tag>
            )}
            {config?.active_model_label && (
              <Typography.Text type="secondary" className="ml-2">
                {config.active_model_label}
              </Typography.Text>
            )}
          </div>
          <Select
            className="w-full"
            placeholder="选择 Provider / 模型"
            value={activeModelKey}
            onChange={setActiveModelKey}
            options={modelOptions}
            showSearch
            optionFilterProp="label"
          />
          <Button
            type="primary"
            onClick={handleSaveModel}
            loading={savingModel}
            disabled={!activeModelKey}
          >
            设为当前模型
          </Button>
        </Space>
      </Card>

      <Card size="small" className="wm-card" title="Provider 配置" loading={loading}>
        <Form layout="vertical">
          <Form.Item label="Provider">
            <Select
              value={providerId}
              onChange={handleProviderSelect}
              options={config?.providers.map((p) => ({
                value: p.id,
                label: p.name,
              }))}
            />
          </Form.Item>
          <Form.Item
            label="API Key"
            extra={
              currentProvider?.api_key_configured
                ? `已配置（${currentProvider.api_key_prefix}…）`
                : undefined
            }
          >
            <Input.Password
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                currentProvider?.require_api_key ? "输入 API Key" : "可留空"
              }
            />
          </Form.Item>
          <Form.Item label="Base URL">
            <Input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              disabled={currentProvider?.freeze_url}
            />
          </Form.Item>
          <Button
            type="primary"
            onClick={handleSaveProvider}
            loading={savingProvider}
          >
            保存
          </Button>
        </Form>
      </Card>
    </>
  );
}

