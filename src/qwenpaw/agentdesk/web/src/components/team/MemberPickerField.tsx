import { useMemo, useState } from "react";
import { Button, Tag, Typography } from "antd";
import { CloseOutlined, PlusOutlined } from "@ant-design/icons";
import type { Employee } from "../../api/plaza";
import AgentAvatar from "../agents/AgentAvatar";
import MemberPickerModal from "./MemberPickerModal";

export interface MemberPickerFieldProps {
  value?: string[];
  onChange?: (names: string[]) => void;
  employees: Employee[];
  label?: string;
  excludeNames?: string[];
  emptyHint?: string;
  modalTitle?: string;
}

export default function MemberPickerField({
  value = [],
  onChange,
  employees,
  label = "成员 / Workers（执行者）",
  excludeNames = [],
  emptyHint = "点击「添加」选择团队执行者",
  modalTitle = "选择执行者",
}: MemberPickerFieldProps) {
  const [pickerOpen, setPickerOpen] = useState(false);

  const employeeMap = useMemo(
    () => new Map(employees.map((e) => [e.name, e])),
    [employees],
  );

  const excluded = useMemo(
    () => new Set(excludeNames.map((name) => name.trim()).filter(Boolean)),
    [excludeNames],
  );

  const visibleEmployees = useMemo(
    () => employees.filter((emp) => !excluded.has(emp.name)),
    [employees, excluded],
  );

  const removeMember = (name: string) => {
    onChange?.(value.filter((n) => n !== name));
  };

  return (
    <>
      <div className="mb-2 flex items-center justify-between gap-3">
        <Typography.Text className="text-sm text-gray-700">{label}</Typography.Text>
        <Button
          type="link"
          size="small"
          icon={<PlusOutlined />}
          className="px-0 text-emerald-600"
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
            const emp = employeeMap.get(name);
            return (
              <div
                key={name}
                className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white py-1 pl-1 pr-2 shadow-sm"
              >
                <AgentAvatar
                  name={name}
                  avatar={emp?.avatar}
                  description={emp?.desc}
                  size="sm"
                />
                <span className="max-w-[120px] truncate text-[13px] text-gray-800">
                  {name}
                </span>
                <Tag color="blue" className="m-0 mr-0.5 border-0 text-[10px] leading-4">
                  执行者
                </Tag>
                <button
                  type="button"
                  aria-label={`移除 ${name}`}
                  className="flex h-5 w-5 items-center justify-center rounded-full text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
                  onClick={() => removeMember(name)}
                >
                  <CloseOutlined className="text-[10px]" />
                </button>
              </div>
            );
          })}
        </div>
      )}

      <MemberPickerModal
        open={pickerOpen}
        employees={visibleEmployees}
        value={value}
        title={modalTitle}
        onCancel={() => setPickerOpen(false)}
        onConfirm={(names) => {
          onChange?.(names.filter((name) => !excluded.has(name)));
          setPickerOpen(false);
        }}
      />
    </>
  );
}
