import { useEffect, useMemo, useState } from "react";
import { Button, Col, Empty, Input, Modal, Row, Typography } from "antd";
import { CheckOutlined, SearchOutlined } from "@ant-design/icons";
import type { SkillItem } from "../../api/skills";
import { SkillIcon } from "../../utils/skillIcon";

export interface SkillPickerModalProps {
  open: boolean;
  skills: SkillItem[];
  value: string[];
  onCancel: () => void;
  onConfirm: (names: string[]) => void;
  title?: string;
  emptyHint?: string;
}

export default function SkillPickerModal({
  open,
  skills,
  value,
  onCancel,
  onConfirm,
  title = "选择技能",
  emptyHint = "暂无匹配的技能",
}: SkillPickerModalProps) {
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState<string[]>([]);

  useEffect(() => {
    if (open) {
      setDraft(value);
      setSearch("");
    }
  }, [open, value]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return skills;
    return skills.filter((skill) => {
      const haystack = [skill.name, skill.description, skill.body].join(" ").toLowerCase();
      return haystack.includes(q);
    });
  }, [skills, search]);

  const toggle = (name: string) => {
    setDraft((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
    );
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
            已选 {draft.length} 项
          </Typography.Text>
          <div className="flex gap-2">
            <Button onClick={onCancel}>取消</Button>
            <Button type="primary" onClick={() => onConfirm(draft)}>
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
          placeholder="搜索技能名称或描述"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="text-sm"
        />
      </label>

      {filtered.length === 0 ? (
        <Empty description={emptyHint} className="py-8" />
      ) : (
        <Row gutter={[12, 12]} className="max-h-[360px] overflow-y-auto pr-1">
          {filtered.map((skill) => {
            const selected = draft.includes(skill.name);
            return (
              <Col key={skill.name} xs={24} sm={12} md={8}>
                <button
                  type="button"
                  onClick={() => toggle(skill.name)}
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
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700">
                      <SkillIcon
                        name={skill.name}
                        icon={skill.icon}
                        description={skill.description}
                      />
                    </span>
                    <div className="min-w-0">
                      <div className="truncate text-[14px] font-semibold text-gray-900">
                        {skill.name}
                      </div>
                    </div>
                  </div>
                  <p className="wm-card-desc line-clamp-2 flex-1 text-[12px] leading-relaxed text-gray-500">
                    {skill.description || "—"}
                  </p>
                </button>
              </Col>
            );
          })}
        </Row>
      )}
    </Modal>
  );
}
