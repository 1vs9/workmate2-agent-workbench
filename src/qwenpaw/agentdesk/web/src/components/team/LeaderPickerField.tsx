import { useMemo, useState } from "react";
import { Button, Tag, Typography } from "antd";
import { CloseOutlined, PlusOutlined } from "@ant-design/icons";
import type { Employee } from "../../api/plaza";
import AgentAvatar from "../agents/AgentAvatar";
import MemberPickerModal from "./MemberPickerModal";

export interface LeaderPickerFieldProps {
  value?: string;
  onChange?: (name: string | undefined) => void;
  employees: Employee[];
}

export default function LeaderPickerField({
  value,
  onChange,
  employees,
}: LeaderPickerFieldProps) {
  const [pickerOpen, setPickerOpen] = useState(false);

  const employeeMap = useMemo(
    () => new Map(employees.map((e) => [e.name, e])),
    [employees],
  );

  const leader = value?.trim() || "";
  const emp = leader ? employeeMap.get(leader) : undefined;

  return (
    <>
      <div className="mb-2 flex items-center justify-between gap-3">
        <Typography.Text className="text-sm text-gray-700">
          Leader
        </Typography.Text>
        <Button
          type="link"
          size="small"
          icon={<PlusOutlined />}
          className="px-0 text-emerald-600"
          onClick={() => setPickerOpen(true)}
        >
          {leader ? "更换" : "选择"}
        </Button>
      </div>

      {!leader ? (
        <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50/60 px-3 py-4 text-center text-[13px] text-gray-400">
          点击「选择」指定团队 leader
        </div>
      ) : (
        <div className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-white py-1 pl-1 pr-2 shadow-sm">
          <AgentAvatar
            name={leader}
            avatar={emp?.avatar}
            description={emp?.desc}
            size="sm"
          />
          <span className="max-w-[160px] truncate text-[13px] text-gray-800">
            {leader}
          </span>
          <Tag color="green" className="m-0 mr-0.5 border-0 text-[10px] leading-4">
            leader
          </Tag>
          <button
            type="button"
            aria-label={`移除 ${leader}`}
            className="flex h-5 w-5 items-center justify-center rounded-full text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600"
            onClick={() => onChange?.(undefined)}
          >
            <CloseOutlined className="text-[10px]" />
          </button>
        </div>
      )}

      <MemberPickerModal
        open={pickerOpen}
        employees={employees}
        value={leader ? [leader] : []}
        mode="single"
        title="选择 Leader"
        emptyHint="点击卡片选择一名员工作为 leader"
        onCancel={() => setPickerOpen(false)}
        onConfirm={(names) => {
          onChange?.(names[0]);
          setPickerOpen(false);
        }}
      />
    </>
  );
}
