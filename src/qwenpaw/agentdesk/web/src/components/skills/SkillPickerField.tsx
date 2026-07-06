import { useMemo, useState } from "react";
import { Button, Tag, Typography } from "antd";
import { CloseOutlined, PlusOutlined } from "@ant-design/icons";
import type { SkillItem } from "../../api/skills";
import { SkillIcon } from "../../utils/skillIcon";
import SkillPickerModal from "./SkillPickerModal";

export interface SkillPickerFieldProps {
  value?: string[];
  onChange?: (names: string[]) => void;
  skills: SkillItem[];
  label?: string;
  /** When false, omit the inline label (e.g. when wrapped in Form.Item). */
  showLabel?: boolean;
  emptyHint?: string;
  modalTitle?: string;
}

export default function SkillPickerField({
  value = [],
  onChange,
  skills,
  label = "挂载技能",
  showLabel = true,
  emptyHint = "点击「添加」选择要挂载的技能",
  modalTitle = "选择技能",
}: SkillPickerFieldProps) {
  const [pickerOpen, setPickerOpen] = useState(false);

  const skillMap = useMemo(
    () => new Map(skills.map((skill) => [skill.name, skill])),
    [skills],
  );

  const removeSkill = (name: string) => {
    onChange?.(value.filter((n) => n !== name));
  };

  return (
    <>
      <div
        className={`mb-2 flex items-center gap-3 ${showLabel ? "justify-between" : "justify-end"}`}
      >
        {showLabel ? (
          <Typography.Text className="m-0 shrink-0 text-sm leading-none text-gray-700">
            {label}
          </Typography.Text>
        ) : null}
        <Button
          type="link"
          size="small"
          icon={<PlusOutlined />}
          className="inline-flex h-auto shrink-0 items-center px-0 leading-none text-emerald-600 [&_.anticon]:inline-flex [&_.anticon]:items-center"
          onClick={() => setPickerOpen(true)}
        >
          添加
        </Button>
      </div>

      {value.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50/60 px-3 py-4 text-center text-[13px] text-gray-400">
          {emptyHint}
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {value.map((name) => {
            const skill = skillMap.get(name);
            return (
              <div
                key={name}
                className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white py-1 pl-2 pr-1.5 shadow-sm"
              >
                <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center text-emerald-700">
                  <SkillIcon
                    name={name}
                    icon={skill?.icon}
                    description={skill?.description}
                    className="text-sm"
                  />
                </span>
                <span className="max-w-[140px] truncate text-[13px] text-gray-800">{name}</span>
                <Tag color="green" className="m-0 border-0 text-[10px] leading-4">
                  技能
                </Tag>
                <button
                  type="button"
                  aria-label={`移除 ${name}`}
                  className="flex h-5 w-5 items-center justify-center rounded-full text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                  onClick={() => removeSkill(name)}
                >
                  <CloseOutlined className="text-[10px]" />
                </button>
              </div>
            );
          })}
        </div>
      )}

      <SkillPickerModal
        open={pickerOpen}
        skills={skills}
        value={value}
        title={modalTitle}
        onCancel={() => setPickerOpen(false)}
        onConfirm={(names) => {
          onChange?.(names);
          setPickerOpen(false);
        }}
      />
    </>
  );
}
