import { useCallback, useMemo, useState } from "react";
import {
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Space,
  Table,
  Typography,
  message,
} from "antd";
import { useAsyncList } from "../../hooks/useAsyncList";
import PageError from "../../components/layout/PageError";
import PageHeader from "../../components/layout/PageHeader";
import { createDocsApi, type Doc, type DocInput, type DocKind } from "../../api/docs";

const { TextArea } = Input;

interface DocLibraryProps {
  kind: DocKind;
  title: string;
  subtitle?: string;
}

function snippet(content: string, max = 120): string {
  const text = (content ?? "").replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function formatTime(value?: number): string {
  if (!value) return "—";
  const ms = value < 1e12 ? value * 1000 : value;
  return new Date(ms).toLocaleString();
}

/** Generic CRUD library page shared by Case Library and Knowledge Library. */
export default function DocLibrary({ kind, title, subtitle }: DocLibraryProps) {
  const api = useMemo(() => createDocsApi(kind), [kind]);
  const loader = useCallback(() => api.list(), [api]);
  const { data, loading, error, reload, setData } = useAsyncList<Doc>(loader);

  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Doc | null>(null);
  const [saving, setSaving] = useState(false);
  const [form] = Form.useForm<DocInput & { tagsText?: string }>();

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    setOpen(true);
  };

  const openEdit = (doc: Doc) => {
    setEditing(doc);
    form.setFieldsValue({
      title: doc.title,
      content: doc.content,
      author: doc.author,
      tagsText: (doc.tags ?? []).join(", "),
    });
    setOpen(true);
  };

  const handleSave = async () => {
    const values = await form.validateFields();
    const payload: DocInput = {
      title: values.title,
      content: values.content,
      author: values.author,
      tags: (values.tagsText ?? "")
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
    };
    setSaving(true);
    try {
      if (editing) {
        const updated = await api.update(editing.id, payload);
        setData((prev) => prev.map((d) => (d.id === editing.id ? updated : d)));
        message.success("已更新");
      } else {
        const created = await api.create(payload);
        setData((prev) => [created, ...prev]);
        message.success("已创建");
      }
      setOpen(false);
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (doc: Doc) => {
    try {
      await api.remove(doc.id);
      setData((prev) => prev.filter((d) => d.id !== doc.id));
      message.success("已删除");
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    }
  };

  const columns = [
    {
      title: "标题",
      dataIndex: "title",
      key: "title",
      width: 240,
      render: (_: unknown, doc: Doc) => (
        <div>
          <Typography.Text strong>{doc.title || "(无标题)"}</Typography.Text>
          <div className="text-xs text-gray-400">
            {snippet(doc.content)}
          </div>
        </div>
      ),
    },
    {
      title: "标签",
      dataIndex: "tags",
      key: "tags",
      width: 160,
      render: (tags: string[]) => (tags ?? []).join(" / ") || "—",
    },
    { title: "作者", dataIndex: "author", key: "author", width: 120 },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      key: "updated_at",
      width: 180,
      render: (v: number) => formatTime(v),
    },
    {
      title: "操作",
      key: "actions",
      width: 140,
      render: (_: unknown, doc: Doc) => (
        <Space>
          <Button size="small" onClick={() => openEdit(doc)}>
            编辑
          </Button>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(doc)}>
            <Button size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title={title}
        subtitle={subtitle}
        actions={
          <Space>
            <Button onClick={reload}>刷新</Button>
            <Button type="primary" onClick={openCreate}>
              新建
            </Button>
          </Space>
        }
      />

      {error ? <PageError message={error} /> : null}

      <Table<Doc>
        rowKey="id"
        loading={loading}
        dataSource={data}
        columns={columns}
        className="wm-card overflow-hidden"
        locale={{ emptyText: "暂无数据，点击「新建」创建首条内容" }}
        pagination={{ pageSize: 12, hideOnSinglePage: true }}
      />

      <Modal
        title={editing ? "编辑" : "新建"}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        destroyOnClose
        width={640}
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="title"
            label="标题"
            rules={[{ required: true, message: "请输入标题" }]}
          >
            <Input placeholder="标题" />
          </Form.Item>
          <Form.Item
            name="content"
            label="内容"
            rules={[{ required: true, message: "请输入内容" }]}
          >
            <TextArea rows={8} placeholder="内容" />
          </Form.Item>
          <Form.Item name="tagsText" label="标签（逗号分隔）">
            <Input placeholder="如：销售, 客服" />
          </Form.Item>
          <Form.Item name="author" label="作者">
            <Input placeholder="作者" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
