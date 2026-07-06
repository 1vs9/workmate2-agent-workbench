import { describe, expect, it } from "vitest";

import {
  buildLeaderConversationView,
  buildLeaderTimelineView,
  buildMemberTimelineView,
  compareTimelineEntries,
  isLeaderOrchestrationNarration,
  mergeStreamTextDelta,
  reduceTeamTimeline,
  type TeamTimelineEntry,
} from "./teamTimeline";

const leader = "深度调研团队·leader";

function delegation(
  seq: number,
  target: string,
  text: string,
  delegationId?: string,
): TeamTimelineEntry {
  return {
    kind: "delegation",
    actor: leader,
    seq,
    ts: seq,
    target,
    text,
    delegation_id: delegationId,
  };
}

function workerText(seq: number, actor: string, text: string): TeamTimelineEntry {
  return {
    kind: "worker_text",
    actor,
    seq,
    ts: seq,
    text,
  };
}

describe("teamTimeline", () => {
  it("interleaves delegations and worker replies chronologically by seq", () => {
    const entries: TeamTimelineEntry[] = [
      delegation(1, "研究员", "请做自我介绍", "d1"),
      workerText(2, "研究员", "我是研究员。"),
      delegation(3, "研究员", "请深度调研股市", "d2"),
      workerText(4, "研究员", "好的，我开始检索。"),
    ];

    const view = buildMemberTimelineView(entries, "研究员");
    expect(view.map((i) => i.kind)).toEqual([
      "leader",
      "member",
      "leader",
      "member",
    ]);
    expect(view[0].kind === "leader" ? view[0].text : "").toBe("请做自我介绍");
    expect(view[1].kind === "member" ? view[1].text : "").toBe("我是研究员。");
  });

  it("merges leader text deltas into one segment in leader view", () => {
    const entries: TeamTimelineEntry[] = [
      { kind: "leader_text", actor: leader, seq: 1, ts: 1, text: "第一段", delta: true },
      { kind: "round_boundary", actor: leader, seq: 2, ts: 2 },
      { kind: "leader_text", actor: leader, seq: 3, ts: 3, text: "第二段", delta: true },
    ];
    const view = buildLeaderTimelineView(entries);
    expect(view.filter((e) => e.kind === "leader_text").map((e) => e.text)).toEqual([
      "第一段",
      "第二段",
    ]);
  });

  it("appends incremental timeline_entry deltas in reducer", () => {
    let entries: TeamTimelineEntry[] = [];
    entries = reduceTeamTimeline(entries, {
      type: "timeline_entry",
      kind: "worker_text",
      actor: "研究员",
      seq: 10,
      ts: 10,
      text: "你好",
      delta: true,
    });
    entries = reduceTeamTimeline(entries, {
      type: "timeline_entry",
      kind: "worker_text",
      actor: "研究员",
      seq: 11,
      ts: 11,
      text: "世界",
      delta: true,
    });
    expect(entries).toHaveLength(1);
    expect(entries[0].text).toBe("你好世界");
  });

  it("coalesces worker_status phase updates for the same target", () => {
    let entries: TeamTimelineEntry[] = [];
    entries = reduceTeamTimeline(entries, {
      type: "timeline_entry",
      kind: "phase",
      actor: "团队·leader",
      seq: 1,
      ts: 1,
      target: "研究员",
      phase: "worker_status",
      label: "研究员正在搜索中...",
    });
    entries = reduceTeamTimeline(entries, {
      type: "timeline_entry",
      kind: "phase",
      actor: "团队·leader",
      seq: 2,
      ts: 2,
      target: "研究员",
      phase: "worker_status",
      label: "研究员终于搜索完了...",
    });
    expect(entries).toHaveLength(1);
    expect(entries[0].label).toBe("研究员终于搜索完了...");
  });

  it("builds leader conversation view with user and delegation items", () => {
    const items = buildLeaderConversationView([
      {
        kind: "user_message",
        actor: "user",
        seq: 0,
        ts: 0,
        text: "分析一下",
      },
      {
        kind: "delegation",
        actor: "团队·leader",
        seq: 1,
        ts: 1,
        target: "研究员",
        text: "请检索资料",
      },
      {
        kind: "worker_text",
        actor: "研究员",
        seq: 2,
        ts: 2,
        text: "好的",
      },
    ]);
    expect(items.map((i) => i.kind)).toEqual(["user", "delegation"]);
  });

  it("excludes worker replies from leader conversation view", () => {
    const items = buildLeaderConversationView([
      {
        kind: "leader_text",
        actor: "团队·leader",
        seq: 0,
        ts: 0,
        text: "我来调度团队",
      },
      {
        kind: "worker_text",
        actor: "规划者",
        seq: 1,
        ts: 1,
        text: "Planner internal reasoning",
      },
    ]);
    expect(items.map((i) => i.kind)).toEqual(["leader_text"]);
  });

  it("shows only the latest operational phase until round done", () => {
    const items = buildLeaderConversationView([
      {
        kind: "phase",
        actor: leader,
        seq: 1,
        ts: 1,
        phase: "planning",
        label: "规划中",
      },
      {
        kind: "phase",
        actor: leader,
        seq: 2,
        ts: 2,
        phase: "waiting_workers",
        label: "研究员 仍在执行…",
      },
      {
        kind: "phase",
        actor: leader,
        seq: 3,
        ts: 3,
        phase: "synthesizing",
        label: "Leader 正在汇总…",
      },
    ]);
    expect(items.filter((i) => i.kind === "phase")).toHaveLength(1);
    expect(items.find((i) => i.kind === "phase")?.label).toBe("Leader 正在汇总…");
  });

  it("clears operational phases after timeline done entry", () => {
    const items = buildLeaderConversationView([
      {
        kind: "phase",
        actor: leader,
        seq: 1,
        ts: 1,
        phase: "waiting_workers",
        label: "研究员 仍在执行…",
      },
      {
        kind: "phase",
        actor: leader,
        seq: 2,
        ts: 2,
        phase: "done",
        label: "团队响应完成",
      },
    ]);
    expect(items.filter((i) => i.kind === "phase")).toEqual([
      expect.objectContaining({ label: "团队响应完成" }),
    ]);
  });

  it("keeps substantive leader synthesis visible", () => {
    const report =
      "## 未来一周大事件综览\n\n规划者拆题完成，研究员收集了多条线索，审查官把关后主笔成稿。";
    expect(isLeaderOrchestrationNarration(report)).toBe(false);
  });

  it("detects leader orchestration narration", () => {
    expect(isLeaderOrchestrationNarration("研究员正在搜索中...")).toBe(true);
    expect(
      isLeaderOrchestrationNarration("已安排研究员与审查官并行调研。"),
    ).toBe(false);
    expect(
      isLeaderOrchestrationNarration(
        "📋 本轮进度：✅ @规划者已收到任务；@研究员 检索；@审查官 把关；@主笔 成稿。",
      ),
    ).toBe(true);
  });

  it("coalesces cumulative same-seq timeline_entry deltas in reducer", () => {
    let entries: TeamTimelineEntry[] = [];
    entries = reduceTeamTimeline(entries, {
      type: "timeline_entry",
      kind: "leader_text",
      actor: leader,
      seq: 5,
      ts: 10,
      text: "团队",
      delta: true,
    });
    entries = reduceTeamTimeline(entries, {
      type: "timeline_entry",
      kind: "leader_text",
      actor: leader,
      seq: 5,
      ts: 11,
      text: "团队都在线，开始派工！",
      delta: true,
    });
    expect(entries).toHaveLength(1);
    expect(entries[0]?.text).toBe("团队都在线，开始派工！");
  });

  it("mergeStreamTextDelta replaces cumulative rewrites", () => {
    const a = "📋 本轮进度：✅ @规划者已派工";
    const b = "📋 本轮进度：✅ @规划者已派工。@主笔成稿。";
    expect(mergeStreamTextDelta(a, b)).toBe(b);
  });

  it("coalesces round_progress phase labels in reduceTeamTimeline", () => {
    const first = {
      kind: "phase" as const,
      actor: leader,
      seq: 1,
      ts: 1,
      phase: "round_progress",
      label: "📋 本轮进度：✅ @规划者已派工",
    };
    const second = {
      type: "timeline_entry",
      kind: "phase",
      actor: leader,
      seq: 2,
      ts: 2,
      phase: "round_progress",
      label: "📋 本轮进度：✅ @规划者已派工。@主笔成稿。",
    };
    const merged = reduceTeamTimeline([first], second);
    expect(merged).toHaveLength(1);
    expect(merged[0]?.label).toBe(second.label);
  });

  it("orders multi-round entries by ts when seq resets each round", () => {
    const round1User: TeamTimelineEntry = {
      kind: "user_message",
      actor: "user",
      seq: 0,
      ts: 100,
      text: "first question",
    };
    const round1Leader: TeamTimelineEntry = {
      kind: "leader_text",
      actor: leader,
      seq: 1,
      ts: 200,
      text: "first answer",
    };
    const round2User: TeamTimelineEntry = {
      kind: "user_message",
      actor: "user",
      seq: 0,
      ts: 300,
      text: "follow up",
    };
    const round2Leader: TeamTimelineEntry = {
      kind: "leader_text",
      actor: leader,
      seq: 1,
      ts: 400,
      text: "second answer",
    };
    const items = buildLeaderConversationView([
      round2User,
      round2Leader,
      round1User,
      round1Leader,
    ]);
    expect(items.map((i) => (i.kind === "user" || i.kind === "leader_text" ? i.text : i.kind))).toEqual([
      "first question",
      "first answer",
      "follow up",
      "second answer",
    ]);
  });

  it("compareTimelineEntries prefers ts over duplicate seq", () => {
    const a: TeamTimelineEntry = {
      kind: "user_message",
      actor: "user",
      seq: 0,
      ts: 50,
      text: "a",
    };
    const b: TeamTimelineEntry = {
      kind: "leader_text",
      actor: leader,
      seq: 0,
      ts: 100,
      text: "b",
    };
    expect(compareTimelineEntries(a, b)).toBeLessThan(0);
  });
});
