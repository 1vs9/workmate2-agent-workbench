import { useCallback, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";
import {
  CodeOutlined,
  EyeOutlined,
  FileTextOutlined,
  GlobalOutlined,
  RightOutlined,
  SearchOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import type { StreamEvent } from "../../api/chatStream";
import {
  aggregateTraceEvents,
  countTraceSteps,
  summarizeTraceSteps,
  type ToolStep,
  type TraceStep,
} from "../../utils/aggregateTraceEvents";
import { useProcessPanelExpanded } from "./useProcessPanelExpanded";

export interface ProcessObservabilityProps {
  events: StreamEvent[];
  isStreaming: boolean;
  className?: string;
}

function truncate(text: string, max = 200): string {
  const trimmed = text.trim();
  if (trimmed.length <= max) return trimmed;
  return `${trimmed.slice(0, max)}…`;
}

function toolIconForName(name: string) {
  const n = name.toLowerCase();
  if (n === "read_file" || n === "read") return EyeOutlined;
  if (n.includes("shell") || n === "bash" || n === "execute_shell_command") {
    return CodeOutlined;
  }
  if (n === "web_fetch" || n.includes("fetch")) return GlobalOutlined;
  if (
    n === "glob_search" ||
    n === "glob" ||
    n === "grep_search" ||
    n === "grep" ||
    n.includes("search")
  ) {
    return SearchOutlined;
  }
  if (n.includes("write") || n.includes("edit")) return FileTextOutlined;
  return ToolOutlined;
}

function pathFromToolArgs(args?: string): string {
  if (!args) return "";
  const trimmed = args.trim();
  if (!trimmed) return "";
  try {
    const parsed = JSON.parse(trimmed) as Record<string, unknown>;
    for (const key of ["path", "file_path", "file", "target", "query"]) {
      const value = parsed[key];
      if (typeof value === "string" && value.trim()) return value.trim();
    }
  } catch {
    /* fall through */
  }
  const oneLine = trimmed.replace(/\s+/g, " ");
  return oneLine.length > 120 ? `${oneLine.slice(0, 120)}…` : oneLine;
}

function formatToolRowLabel(step: ToolStep): string {
  const actionMap: Record<string, string> = {
    read_file: "读取",
    write_file: "写入",
    edit_file: "编辑",
    execute_shell_command: "执行命令",
    glob_search: "搜索文件",
    grep_search: "搜索内容",
    web_fetch: "获取网页",
  };
  const action = actionMap[step.name] || step.name.replace(/_/g, " ");
  const path = pathFromToolArgs(step.args);
  return path ? `${action} ${path}` : action;
}

function humanToolName(name: string): string {
  const labels: Record<string, string> = {
    conversation_search: "Conversation Search",
    chat_with_agent: "Agent 对话",
    submit_to_agent: "派工提交",
    check_agent_task: "任务状态",
  };
  return labels[name] || name.replace(/_/g, " ");
}

function Chevron({
  open,
  className = "",
}: {
  open: boolean;
  className?: string;
}) {
  return (
    <RightOutlined
      aria-hidden
      className={`wm-trace-chevron text-[10px] text-slate-400 transition-transform duration-200 motion-reduce:transition-none ${
        open ? "wm-trace-chevron--open" : ""
      } ${className}`.trim()}
    />
  );
}

function CollapsibleSection({
  label,
  expanded,
  onToggle,
  children,
  className = "",
}: {
  label: string;
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
  className?: string;
}) {
  const handleKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onToggle();
    }
  };

  return (
    <div className={className}>
      <button
        type="button"
        onClick={onToggle}
        onKeyDown={handleKeyDown}
        aria-expanded={expanded}
        className="wm-trace-nested-toggle flex min-h-[28px] w-full cursor-pointer items-center gap-1.5 rounded-md px-0.5 py-1 text-left text-[12px] font-medium text-slate-600 transition-colors duration-200 hover:text-slate-800 motion-reduce:transition-none"
      >
        <Chevron open={expanded} />
        <span>{label}</span>
      </button>
      <div
        className={`wm-trace-nested-body ${expanded ? "wm-trace-nested-body--expanded" : ""}`}
        aria-hidden={!expanded}
      >
        <div className="wm-trace-nested-body-inner">{children}</div>
      </div>
    </div>
  );
}

function ThinkingBlock({ steps }: { steps: TraceStep[] }) {
  const thinkingSteps = steps.filter((s) => s.kind === "thinking");
  const merged = thinkingSteps
    .map((s) => (s.kind === "thinking" ? s.content : ""))
    .filter(Boolean)
    .join("\n\n")
    .trim();
  const hasRunning = thinkingSteps.some(
    (s) => s.kind === "thinking" && s.status === "running",
  );
  const [expanded, setExpanded] = useState(hasRunning || Boolean(merged));

  if (!merged && !hasRunning) return null;

  return (
    <CollapsibleSection
      label="深度思考"
      expanded={expanded}
      onToggle={() => setExpanded((v) => !v)}
      className="wm-trace-thinking"
    >
      <pre className="wm-trace-thinking-text mt-1 max-h-36 overflow-y-auto whitespace-pre-wrap rounded-lg border border-slate-200/80 bg-slate-50 px-2.5 py-2 text-[12px] leading-relaxed text-slate-500">
        {merged || (hasRunning ? "思考中…" : "（无内容）")}
      </pre>
    </CollapsibleSection>
  );
}

function ToolRow({ step }: { step: ToolStep }) {
  const Icon = toolIconForName(step.name);
  const label = formatToolRowLabel(step);
  const hasDetail = Boolean(step.output || (step.args && !pathFromToolArgs(step.args)));
  const [expanded, setExpanded] = useState(false);
  const running = step.status === "running";

  const handleKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (hasDetail) setExpanded((v) => !v);
    }
  };

  return (
    <div className="wm-trace-tool-row">
      <button
        type="button"
        onClick={() => hasDetail && setExpanded((v) => !v)}
        onKeyDown={handleKeyDown}
        aria-expanded={hasDetail ? expanded : undefined}
        disabled={!hasDetail}
        className={`flex min-h-[28px] w-full items-start gap-2 rounded-md px-0.5 py-1 text-left transition-colors duration-200 motion-reduce:transition-none ${
          hasDetail ? "cursor-pointer hover:bg-slate-100/80" : "cursor-default"
        }`}
      >
        {hasDetail ? (
          <Chevron open={expanded} className="mt-1" />
        ) : (
          <span className="inline-flex w-[10px] shrink-0" aria-hidden />
        )}
        <Icon
          aria-hidden
          className={`mt-0.5 shrink-0 text-[13px] ${
            running ? "text-emerald-600" : "text-slate-500"
          }`}
        />
        <span className="min-w-0 flex-1 text-[12px] leading-snug text-slate-600">
          <span className="font-medium text-slate-700">
            {humanToolName(step.name)}
          </span>
          {label !== humanToolName(step.name) ? (
            <span className="mt-0.5 block break-all font-normal text-slate-500">
              {label}
            </span>
          ) : null}
        </span>
      </button>
      {hasDetail ? (
        <div
          className={`wm-trace-tool-detail ${expanded ? "wm-trace-tool-detail--expanded" : ""}`}
          aria-hidden={!expanded}
        >
          <div className="wm-trace-tool-detail-inner ml-[22px] pl-4">
            {step.output ? (
              <pre className="max-h-32 overflow-y-auto whitespace-pre-wrap rounded-md border border-slate-200/70 bg-white px-2 py-1.5 text-[11px] leading-relaxed text-slate-500">
                {truncate(step.output, 1200)}
              </pre>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function OtherStepRow({ step }: { step: TraceStep }) {
  if (step.kind === "thinking" || step.kind === "tool") return null;

  let label = "";
  let detail = "";
  switch (step.kind) {
    case "skills":
      label = step.label;
      detail = step.skills.join("、");
      break;
    case "info": {
      label = step.label;
      detail = step.detail ?? "";
      const count = step.repeatCount ?? 1;
      if (count > 1) {
        label = `${label} ×${count}`;
      }
      break;
    }
    case "generic":
      label = step.label;
      detail = step.detail ?? "";
      break;
    default:
      return null;
  }

  return (
    <div className="flex min-h-[28px] items-start gap-2 px-0.5 py-1 text-[12px] text-slate-600">
      <ToolOutlined aria-hidden className="mt-0.5 shrink-0 text-[13px] text-slate-500" />
      <div className="min-w-0 flex-1">
        <div className="font-medium text-slate-700">{label}</div>
        {detail ? (
          <div className="mt-0.5 break-words text-slate-500">{truncate(detail, 240)}</div>
        ) : null}
      </div>
    </div>
  );
}

export default function ProcessObservability({
  events,
  isStreaming,
  className = "",
}: ProcessObservabilityProps) {
  const steps = useMemo(
    () =>
      aggregateTraceEvents(events, {
        finalizeOpenTools: !isStreaming,
        finalizeOpenThinking: !isStreaming,
      }),
    [events, isStreaming],
  );
  const summary = useMemo(() => summarizeTraceSteps(steps), [steps]);
  const counts = useMemo(() => countTraceSteps(steps), [steps]);
  const [expanded, toggle] = useProcessPanelExpanded(isStreaming);

  const handleSummaryKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLButtonElement>) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggle();
      }
    },
    [toggle],
  );

  const toolSteps = steps.filter((s): s is ToolStep => s.kind === "tool");
  const otherSteps = steps.filter(
    (s) => s.kind !== "tool" && s.kind !== "thinking",
  );

  if (!steps.length) {
    if (!isStreaming) return null;
    return (
      <div className={`wm-trace-panel ${className}`.trim()}>
        <div className="wm-trace-summary flex min-h-[32px] w-full items-center gap-1.5 rounded-lg px-1 py-1.5 text-[12px] text-slate-600">
          <span className="min-w-0 flex-1 truncate">执行中…</span>
          <span className="relative flex h-2 w-2 shrink-0" aria-hidden>
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60 motion-reduce:animate-none" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
          </span>
        </div>
      </div>
    );
  }

  const summaryLabel =
    summary ||
    (isStreaming
      ? `工具调用 ${counts.toolCalls}，过程消息 ${counts.processMessages}`
      : "执行过程");

  return (
    <div className={`wm-trace-panel ${className}`.trim()}>
      <button
        type="button"
        onClick={toggle}
        onKeyDown={handleSummaryKeyDown}
        aria-expanded={expanded}
        className="wm-trace-summary flex min-h-[32px] w-full cursor-pointer items-center gap-1.5 rounded-lg px-1 py-1.5 text-left text-[12px] text-slate-600 transition-colors duration-200 hover:text-slate-800 motion-reduce:transition-none"
      >
        <Chevron open={expanded} />
        <span className="min-w-0 flex-1 truncate">
          {isStreaming ? `执行中 · ${summaryLabel}` : summaryLabel}
        </span>
        {isStreaming ? (
          <span className="relative flex h-2 w-2 shrink-0" aria-hidden>
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60 motion-reduce:animate-none" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
          </span>
        ) : null}
      </button>

      <div
        className={`wm-trace-body ${expanded ? "wm-trace-body--expanded" : ""}`}
        aria-hidden={!expanded}
      >
        <div className="wm-trace-body-inner">
          <div className="wm-trace-detail mt-1 rounded-lg border border-slate-200/80 bg-slate-50/90 px-2.5 py-2">
            <ThinkingBlock steps={steps} />
            {toolSteps.length ? (
              <div
                className={`wm-trace-tool-list space-y-0.5 ${
                  steps.some((s) => s.kind === "thinking") ? "mt-2 border-t border-slate-200/70 pt-2" : ""
                }`}
              >
                {toolSteps.map((step) => (
                  <ToolRow key={step.id} step={step} />
                ))}
              </div>
            ) : null}
            {otherSteps.length ? (
              <div
                className={`space-y-0.5 ${
                  toolSteps.length || steps.some((s) => s.kind === "thinking")
                    ? "mt-2 border-t border-slate-200/70 pt-2"
                    : ""
                }`}
              >
                {otherSteps.map((step) => (
                  <OtherStepRow key={step.id} step={step} />
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
