import { useEffect, useMemo, useState } from "react";
import { Button, Col, Empty, Input, Modal, Row, Typography } from "antd";
import { CheckOutlined, SearchOutlined } from "@ant-design/icons";
import type { Employee } from "../../api/plaza";
import AgentAvatar from "../agents/AgentAvatar";
const ALL_CATEGORY = "全部";

export interface MemberPickerModalProps {
  open: boolean;
  employees: Employee[];
  value: string[];
  onCancel: () => void;
  onConfirm: (names: string[]) => void;
  mode?: "single" | "multiple";
  title?: string;
  emptyHint?: string;
}

function employeeAvatar(emp: Employee): string {
  return emp.avatar?.trim() || "";
}
export default function MemberPickerModal({
  open,
  employees,
  value,
  onCancel,
  onConfirm,
  mode = "multiple",
  title = "选择成员",
  emptyHint = "暂无匹配的成员",
}: MemberPickerModalProps) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState(ALL_CATEGORY);
  const [draft, setDraft] = useState<string[]>([]);

  useEffect(() => {
    if (open) {
      setDraft(value);
      setSearch("");
      setCategory(ALL_CATEGORY);
    }
  }, [open, value]);

  const categories = useMemo(() => {
    const tags = new Set<string>();
    for (const emp of employees) {
      for (const skill of emp.skills ?? []) {
        const t = skill.trim();
        if (t) tags.add(t);
      }
    }
    return [ALL_CATEGORY, ...Array.from(tags).sort()];
  }, [employees]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return employees.filter((emp) => {
      if (category !== ALL_CATEGORY && !(emp.skills ?? []).includes(category)) {
        return false;
      }
      if (!q) return true;
      const haystack = [
        emp.name,
        emp.desc,
        ...(emp.skills ?? []),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [employees, search, category]);

  const toggle = (name: string) => {
    if (mode === "single") {
      setDraft((prev) => (prev.includes(name) ? [] : [name]));
      return;
    }
    setDraft((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
    );
  };

  const handleConfirm = () => {
    onConfirm(draft);
  };

  return (
    <Modal
      title={title}
      open={open}
      onCancel={onCancel}
      width={720}
      destroyOnClose
      footer={
        <div className="flex items-center justify-between gap-3">
          <Typography.Text type="secondary" className="text-sm">
            {mode === "single"
              ? draft[0]
                ? `已选：${draft[0]}`
                : "请选择 1 位"
              : `已选 ${draft.length} 位`}
          </Typography.Text>
          <div className="flex gap-2">
            <Button onClick={onCancel}>取消</Button>
            <Button type="primary" onClick={handleConfirm}>
              确认
            </Button>
          </div>
        </div>
      }
    >
      <label className="mb-4 flex h-9 items-center rounded-lg border border-gray-200/80 bg-white px-3 shadow-sm">
        <SearchOutlined className="text-gray-400" />
        <Input
          bordered={false}
          placeholder="搜索成员名称或描述"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="text-sm"
        />
      </label>

      {categories.length > 1 ? (
        <div className="scrollbar-hide mb-4 flex gap-2 overflow-x-auto pb-1">
          {categories.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setCategory(item)}
              className={`shrink-0 rounded-full px-3 py-1.5 text-[13px] transition-colors ${
                category === item
                  ? "wm-chip-active"
                  : "border border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
              }`}
            >
              {item}
            </button>
          ))}
        </div>
      ) : null}

      {filtered.length === 0 ? (
        <Empty description={emptyHint} className="py-8" />
      ) : (
        <Row gutter={[12, 12]} className="max-h-[360px] overflow-y-auto pr-1">
          {filtered.map((emp) => {
            const selected = draft.includes(emp.name);
            return (
              <Col key={emp.name} xs={24} sm={12} md={8}>
                <button
                  type="button"
                  onClick={() => toggle(emp.name)}
                  className={`wm-card relative flex h-full w-full flex-col p-3 text-left transition-all duration-200 ${
                    selected
                      ? "border-emerald-400 ring-2 ring-emerald-100"
                      : "hover:border-emerald-200 hover:shadow-sm"
                  }`}
                >
                  {selected ? (
                    <span className="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full bg-emerald-600 text-[10px] text-white">
                      <CheckOutlined />
                    </span>
                  ) : null}
                  <div className="mb-2 flex items-start gap-2 pr-5">
                    <AgentAvatar
                      name={emp.name}
                      avatar={employeeAvatar(emp)}
                      size="sm"
                      className="shrink-0"
                    />                    <div className="min-w-0">
                      <div className="truncate text-[14px] font-semibold text-gray-900">
                        {emp.name}
                      </div>
                    </div>
                  </div>
                  <p className="wm-card-desc mb-2 line-clamp-2 flex-1 text-[12px] leading-relaxed text-gray-500">
                    {emp.desc || "—"}
                  </p>
                  {(emp.skills ?? []).length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {(emp.skills ?? []).slice(0, 3).map((t) => (
                        <span key={t} className="wm-expert-card__tag text-[10px]">
                          {t}
                        </span>
                      ))}
                    </div>
                  ) : null}                </button>
              </Col>
            );
          })}
        </Row>
      )}
    </Modal>
  );
}
