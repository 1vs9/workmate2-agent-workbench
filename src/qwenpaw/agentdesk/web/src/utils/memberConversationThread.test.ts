import { describe, expect, it } from "vitest";
import type { ChatTurn } from "./chatStreamReducer";
import { buildMemberConversationThread } from "./memberConversationThread";
import {
  looksLikeLeaderTeamSummary,
  sanitizeMemberTurnForSession,
} from "./sanitizeMemberSession";

const team = {
  id: "t1",
  name: "深度调研团队",
  tags: [],
  desc: "",
  avatar: "",
  members: ["研究员", "审查官", "主笔", "规划者"],
  leader: "PM",
};

const employees = [
  {
    id: "e1",
    name: "研究员",
    agent_id: "emp_research",
    desc: "",
    avatar: "",
    tools: [],
    skills: [],
    mcp: [],
  },
];

function assistantTurn(name: string, text = "", extra?: Partial<ChatTurn>): ChatTurn {
  return {
    id: `a-${name}-${text.slice(0, 8)}`,
    role: "assistant",
    name,
    avatarKind: "team",
    text,
    traceEvents: [],
    streaming: false,
    ...extra,
  };
}

describe("sanitizeMemberSession", () => {
  it("detects leader team summaries mis-attributed to a member", () => {
    const text =
      "四位成员已完成自我介绍：\n- 研究员：...\n- 审查官：...\n- 主笔：...\n- 规划者：...";
    expect(looksLikeLeaderTeamSummary(text, team)).toBe(true);
  });

  it("drops leader echo text from member replies", () => {
    const leaderTurns = [assistantTurn("深度调研团队·leader", "已派出任务，让我看看各位成员的回复")];
    const memberTurn = assistantTurn("主笔", "已派出任务，让我看看各位成员的回复");
    const sanitized = sanitizeMemberTurnForSession(
      memberTurn,
      "主笔",
      ["请做自我介绍"],
      leaderTurns,
      team,
    );
    expect(sanitized).toBeNull();
  });
});

describe("buildMemberConversationThread", () => {
  it("shows leader delegation then member reply as separate items", () => {
    const turns: ChatTurn[] = [
      assistantTurn("深度调研团队·leader", "", {
        traceEvents: [
          {
            type: "trace",
            step: "tool_call_end",
            tool_name: "submit_to_agent",
            tool_call_id: "c1",
            detail: JSON.stringify({
              arguments: { to_agent: "研究员", text: "请做自我介绍" },
            }),
          },
        ],
      }),
      assistantTurn("研究员", "我是研究员，负责调研。"),
    ];

    const thread = buildMemberConversationThread(
      turns,
      "研究员",
      team,
      employees,
    );
    expect(thread).toEqual([
      { kind: "leader", id: "c1", text: "请做自我介绍" },
      {
        kind: "member",
        turn: expect.objectContaining({ text: "我是研究员，负责调研。" }),
      },
    ]);
  });

  it("interleaves multi-round delegations and replies chronologically", () => {
    function leaderWithDelegation(text: string, callId: string): ChatTurn {
      return {
        ...assistantTurn("深度调研团队·leader"),
        traceEvents: [
          {
            type: "tool_call_end",
            tool_name: "submit_to_agent",
            tool_call_id: callId,
            member_name: "研究员",
            detail: JSON.stringify({ to_agent: "研究员", text }),
          },
        ],
      };
    }
    const turns: ChatTurn[] = [
      leaderWithDelegation("请做自我介绍", "c1"),
      assistantTurn("研究员", "我是研究员。"),
      leaderWithDelegation("请深度调研股市", "c2"),
      assistantTurn("研究员", "好的，我开始检索。"),
    ];

    const thread = buildMemberConversationThread(turns, "研究员", team, employees);
    expect(thread).toEqual([
      { kind: "leader", id: "c1", text: "请做自我介绍" },
      { kind: "member", turn: expect.objectContaining({ text: "我是研究员。" }) },
      { kind: "leader", id: "c2", text: "请深度调研股市" },
      {
        kind: "member",
        turn: expect.objectContaining({ text: "好的，我开始检索。" }),
      },
    ]);
  });

  it("keeps a member reply attributed by sender and dedupes repeats", () => {
    // The leader's own summary stays under the leader (sender), while the
    // member's reply — even if it names teammates — belongs to that member.
    // Identical repeats collapse to a single bubble.
    const reply = "我是审查官，负责和研究员、主笔一起把最后一道质量关。";
    const turns: ChatTurn[] = [
      assistantTurn("深度调研团队·leader", "我已统筹安排，请各位就位。"),
      assistantTurn("审查官", reply),
      assistantTurn("审查官", reply),
    ];

    const thread = buildMemberConversationThread(
      turns,
      "审查官",
      team,
      employees,
    );
    const memberItems = thread.filter((item) => item.kind === "member");
    expect(memberItems).toHaveLength(1);
    expect(memberItems[0]).toEqual(
      expect.objectContaining({
        kind: "member",
        turn: expect.objectContaining({ text: reply }),
      }),
    );
  });

  it("matches member replies by canonical and legacy session suffix", () => {
    const asciiTeam = {
      ...team,
      members: ["Alice", "Reviewer"],
      leader: "Lead",
    };
    const turns: ChatTurn[] = [
      assistantTurn("未知成员", "新后缀回复", {
        sourceMessage: { sessionId: "task-1:team:member:Alice" },
      }),
      assistantTurn("未知成员", "旧后缀回复", {
        sourceMessage: { sessionId: "task-1:team:member-Alice" },
      }),
    ];

    const thread = buildMemberConversationThread(turns, "Alice", asciiTeam, []);
    const replies = thread
      .filter((item) => item.kind === "member")
      .map((item) =>
        item.kind === "member" ? String(item.turn.text || "") : "",
      );
    expect(replies).toContain("新后缀回复");
    expect(replies).toContain("旧后缀回复");
  });
});
