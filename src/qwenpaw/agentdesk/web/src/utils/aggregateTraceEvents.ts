import type { StreamEvent } from "../api/chatStream";

export type TraceStepKind = "thinking" | "tool" | "skills" | "info" | "generic";

export interface TraceStepBase {
  id: string;
  kind: TraceStepKind;
}

export interface ThinkingStep extends TraceStepBase {
  kind: "thinking";
  content: string;
  status: "running" | "done";
}

export interface ToolStep extends TraceStepBase {
  kind: "tool";
  name: string;
  callId: string;
  args?: string;
  output?: string;
  state?: string;
  status: "running" | "success" | "error";
}

export interface SkillsStep extends TraceStepBase {
  kind: "skills";
  label: string;
  skills: string[];
}

export interface InfoStep extends TraceStepBase {
  kind: "info";
  label: string;
  detail?: string;
  /** When >1, consecutive identical info events were collapsed. */
  repeatCount?: number;
}

export interface GenericStep extends TraceStepBase {
  kind: "generic";
  label: string;
  detail?: string;
}

export type TraceStep =
  | ThinkingStep
  | ToolStep
  | SkillsStep
  | InfoStep
  | GenericStep;

export interface AggregateTraceOptions {
  /** Mark still-running tools complete when the stream has ended. */
  finalizeOpenTools?: boolean;
  /** Mark still-running thinking steps done when the stream has ended. */
  finalizeOpenThinking?: boolean;
}

function stepId(prefix: string, index: number): string {
  return `${prefix}-${index}`;
}

function eventStep(evt: StreamEvent): string {
  const type = String(evt.type || "");
  if (type === "trace") return String(evt.step || "");
  return type;
}

function lastThinking(steps: TraceStep[]): ThinkingStep | undefined {
  for (let i = steps.length - 1; i >= 0; i -= 1) {
    const step = steps[i];
    if (step.kind === "thinking") return step;
  }
  return undefined;
}

function upsertTool(
  steps: TraceStep[],
  toolIndex: Map<string, ToolStep>,
  callId: string,
  name: string,
): ToolStep {
  const existing = callId ? toolIndex.get(callId) : undefined;
  if (existing) {
    if (name) existing.name = name;
    return existing;
  }
  const tool: ToolStep = {
    id: stepId("tool", steps.length),
    kind: "tool",
    name: name || "工具",
    callId,
    status: "running",
  };
  steps.push(tool);
  if (callId) toolIndex.set(callId, tool);
  return tool;
}

function toolStatusFromState(state?: string): ToolStep["status"] {
  const normalized = (state || "").toLowerCase();
  if (normalized.includes("fail") || normalized.includes("error")) return "error";
  if (normalized) return "success";
  return "success";
}

function upsertInfoStep(steps: TraceStep[], label: string, detail?: string): void {
  const last = steps[steps.length - 1];
  if (
    last?.kind === "info" &&
    last.label === label &&
    (last.detail ?? "") === (detail ?? "")
  ) {
    last.repeatCount = (last.repeatCount ?? 1) + 1;
    return;
  }
  steps.push({
    id: stepId("info", steps.length),
    kind: "info",
    label,
    detail,
  });
}

/** Collapse raw SSE trace events into structured observability steps. */
export function aggregateTraceEvents(
  events: StreamEvent[],
  options: AggregateTraceOptions = {},
): TraceStep[] {
  const steps: TraceStep[] = [];
  const toolIndex = new Map<string, ToolStep>();
  let thinkingSeq = 0;
  let lastOpenTool: ToolStep | undefined;

  const resolveTool = (
    callId: string,
    name: string,
    step: string,
  ): ToolStep => {
    if (callId) {
      const tool = upsertTool(steps, toolIndex, callId, name);
      lastOpenTool = tool;
      return tool;
    }
    if (step === "tool_call_end") {
      const tool = upsertTool(steps, toolIndex, `seq-${steps.length}`, name);
      lastOpenTool = tool;
      return tool;
    }
    if (step === "tool_result_end" && lastOpenTool?.status === "running") {
      return lastOpenTool;
    }
    const fallback = upsertTool(steps, toolIndex, callId, name);
    lastOpenTool = fallback;
    return fallback;
  };

  for (const evt of events) {
    const step = eventStep(evt);
    if (!step || step === "reply_start" || step === "reply_end") continue;

    switch (step) {
      case "thinking_start": {
        steps.push({
          id: stepId("thinking", thinkingSeq++),
          kind: "thinking",
          content: "",
          status: "running",
        });
        break;
      }
      case "thinking_delta": {
        const piece = String(evt.detail ?? "");
        if (!piece) break;
        const active = lastThinking(steps);
        if (active?.status === "running") {
          active.content += piece;
        } else {
          steps.push({
            id: stepId("thinking", thinkingSeq++),
            kind: "thinking",
            content: piece,
            status: "running",
          });
        }
        break;
      }
      case "thinking_end": {
        const detail = String(evt.detail ?? "");
        const active = lastThinking(steps);
        if (active) {
          if (detail && detail.length >= active.content.length) {
            active.content = detail;
          }
          active.status = "done";
        } else if (detail) {
          steps.push({
            id: stepId("thinking", thinkingSeq++),
            kind: "thinking",
            content: detail,
            status: "done",
          });
        }
        break;
      }
      case "thinking_retract": {
        for (let i = steps.length - 1; i >= 0; i -= 1) {
          if (steps[i].kind === "thinking") {
            steps.splice(i, 1);
            break;
          }
        }
        break;
      }
      case "tool_call_start": {
        const callId = String(evt.tool_call_id ?? "");
        const name = String(evt.tool_name ?? evt.label ?? "");
        resolveTool(callId, name.replace(/^调用\s*/, ""), "tool_call_start");
        break;
      }
      case "tool_call_end": {
        const callId = String(evt.tool_call_id ?? "");
        const name = String(evt.tool_name ?? evt.label ?? "");
        const tool = resolveTool(
          callId,
          name.replace(/^调用\s*/, ""),
          "tool_call_end",
        );
        const args = String(evt.detail ?? "");
        if (args) tool.args = args;
        break;
      }
      case "tool_result_start": {
        const callId = String(evt.tool_call_id ?? "");
        const name = String(evt.tool_name ?? "");
        resolveTool(callId, name, "tool_result_start");
        break;
      }
      case "tool_result_delta": {
        const callId = String(evt.tool_call_id ?? "");
        const name = String(evt.tool_name ?? evt.label ?? "");
        const tool = resolveTool(
          callId,
          name.replace(/^(完成|调用)\s*/, ""),
          "tool_result_delta",
        );
        const piece = String(evt.detail ?? "");
        if (piece) {
          tool.output = `${tool.output ?? ""}${piece}`;
          tool.status = "running";
        }
        break;
      }
      case "tool_result_end": {
        const callId = String(evt.tool_call_id ?? "");
        const name = String(evt.tool_name ?? evt.label ?? "");
        const tool = resolveTool(
          callId,
          name.replace(/^(完成|调用)\s*/, ""),
          "tool_result_end",
        );
        const output = String(evt.detail ?? "");
        if (output) {
          const prev = tool.output ?? "";
          if (!prev || output.startsWith(prev)) {
            tool.output = output;
          } else if (!prev.includes(output)) {
            tool.output = `${prev}${output}`;
          }
        }
        tool.state = String(evt.state ?? "");
        tool.status = toolStatusFromState(tool.state);
        if (tool.status !== "running") {
          lastOpenTool = undefined;
        }
        break;
      }
      case "skills_active": {
        const skills = Array.isArray(evt.skills)
          ? evt.skills.map((s) => String(s))
          : [];
        steps.push({
          id: stepId("skills", steps.length),
          kind: "skills",
          label: String(evt.label ?? "已加载技能"),
          skills,
        });
        break;
      }
      case "skill_create": {
        steps.push({
          id: stepId("generic", steps.length),
          kind: "generic",
          label: String(evt.label ?? "技能编排"),
        });
        break;
      }
      case "info": {
        upsertInfoStep(
          steps,
          String(evt.label ?? evt.content ?? "提示"),
          evt.detail ? String(evt.detail) : undefined,
        );
        break;
      }
      default: {
        const label = String(evt.label ?? step);
        if (label) {
          steps.push({
            id: stepId("generic", steps.length),
            kind: "generic",
            label,
            detail: evt.detail ? String(evt.detail) : undefined,
          });
        }
        break;
      }
    }
  }

  if (options.finalizeOpenTools) {
    for (const step of steps) {
      if (step.kind === "tool" && step.status === "running") {
        step.status = "success";
        step.state = step.state || "success";
      }
    }
  }

  if (options.finalizeOpenThinking) {
    for (const step of steps) {
      if (step.kind === "thinking" && step.status === "running") {
        step.status = "done";
      }
    }
  }

  return steps;
}

export interface TraceStepCounts {
  toolCalls: number;
  processMessages: number;
}

export function countTraceSteps(steps: TraceStep[]): TraceStepCounts {
  let toolCalls = 0;
  let processMessages = 0;
  for (const step of steps) {
    if (step.kind === "tool") toolCalls += 1;
    else processMessages += 1;
  }
  return { toolCalls, processMessages };
}

export function summarizeTraceSteps(steps: TraceStep[]): string {
  if (!steps.length) return "";
  const { toolCalls, processMessages } = countTraceSteps(steps);
  const parts: string[] = [];
  if (toolCalls) parts.push(`工具调用 ${toolCalls}`);
  if (processMessages) parts.push(`过程消息 ${processMessages}`);
  return parts.join("，") || `${steps.length} 个步骤`;
}
