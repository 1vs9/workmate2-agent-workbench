import { describe, expect, it } from "vitest";
import type { ChatTurn } from "./chatStreamReducer";
import {
  extractMemberDelegations,
  latestDelegationForMember,
} from "./extractMemberDelegations";
import {
  dedupeMemberTurnsAgainstDelegation,
  memberSessionStatus,
  partitionTeamConversation,
} from "./partitionTeamConversation";

const team = {
  id: "t1",
  name: "分析团队",
  tags: [],
  desc: "",
  avatar: "",
  members: ["研究员", "写手"],
  leader: "PM",
};

function assistantTurn(name: string, text = "", streaming = false): ChatTurn {
  return {
    id: `a-${name}`,
    role: "assistant",
    name,
    avatarKind: "team",
    text,
    traceEvents: [],
    streaming,
  };
}

describe("partitionTeamConversation", () => {
  it("routes user and leader turns to the leader session", () => {
    const turns: ChatTurn[] = [
      { id: "u1", role: "user", name: "用户", avatarKind: "user", text: "hi", traceEvents: [], streaming: false },
      assistantTurn("分析团队·leader", "plan"),
      assistantTurn("研究员", "research"),
    ];
    const partition = partitionTeamConversation(turns, team);
    expect(partition.leaderTurns.map((t) => t.name)).toEqual([
      "用户",
      "分析团队·leader",
    ]);
    expect(partition.memberTurnsByName.get("研究员")?.[0].text).toBe("research");
    expect(partition.memberNames).toEqual(["研究员", "写手"]);
  });

  it("lists every configured worker for 深度调研团队 even before they reply", () => {
    const researchTeam = {
      id: "5051d9f4b3074362bb7c402b40402694",
      name: "深度调研团队",
      tags: ["AgentDesk"],
      desc: "",
      avatar: "",
      leader: "深度调研团队·leader",
      members: ["主笔", "研究员", "规划者", "审查官"],
    };
    const partition = partitionTeamConversation([], researchTeam);
    expect(partition.memberNames).toEqual([
      "主笔",
      "研究员",
      "规划者",
      "审查官",
    ]);
  });

  it("does not duplicate the leader tab when leader content is mis-tagged", () => {
    const researchTeam = {
      id: "team-dup",
      name: "深度调研团队",
      tags: ["AgentDesk"],
      desc: "",
      avatar: "",
      leader: "深度调研团队·leader",
      members: ["主笔", "研究员", "规划者", "审查官"],
    };
    const turns: ChatTurn[] = [
      {
        ...assistantTurn("深度调研团队·leader", "团队汇总"),
        sourceMessage: { sessionId: "task-1:team:member:主笔" },
      },
    ];
    const partition = partitionTeamConversation(turns, researchTeam);
    expect(partition.memberNames).toEqual([
      "主笔",
      "研究员",
      "规划者",
      "审查官",
    ]);
    expect(partition.leaderTurns.some((t) => t.text.includes("团队汇总"))).toBe(
      true,
    );
  });

  it("drops orphan leader snippets when a substantive leader turn exists", () => {
    const team = {
      id: "team-snippet",
      name: "深度调研团队",
      tags: ["AgentDesk"],
      desc: "",
      avatar: "",
      leader: "深度调研团队·leader",
      members: ["主笔"],
    };
    const turns: ChatTurn[] = [
      assistantTurn(
        "深度调研团队·leader",
        "我负责拆解任务、派工、跟进、汇总，会协调大家各司其职。",
      ),
      assistantTurn("深度调研团队·leader", "成员"),
    ];
    const partition = partitionTeamConversation(turns, team);
    expect(partition.leaderTurns).toHaveLength(1);
    expect(partition.leaderTurns[0].text).toContain("拆解任务");
  });

  it("derives member session status from turns", () => {
    expect(memberSessionStatus(undefined)).toBe("idle");
    expect(memberSessionStatus([assistantTurn("研究员")])).toBe("idle");
    expect(memberSessionStatus([assistantTurn("研究员", "done")])).toBe("done");
    expect(memberSessionStatus([assistantTurn("研究员", "", true)])).toBe("working");
  });

  it("recognizes canonical and legacy member session suffixes", () => {
    const asciiTeam = {
      ...team,
      members: ["Alice", "Bob"],
    };
    const turns: ChatTurn[] = [
      {
        ...assistantTurn("未知成员", "新格式"),
        sourceMessage: { sessionId: "task-1:team:member:Alice" },
      },
      {
        ...assistantTurn("未知成员", "旧格式"),
        sourceMessage: { sessionId: "task-1:team:member-Bob" },
      },
    ];
    const partition = partitionTeamConversation(turns, asciiTeam);
    expect(partition.memberTurnsByName.get("Alice")?.map((t) => t.text)).toContain(
      "新格式",
    );
    expect(partition.memberTurnsByName.get("Bob")?.map((t) => t.text)).toContain(
      "旧格式",
    );
  });

  it("dedupes member turns that repeat the delegation brief", () => {
    const turns: ChatTurn[] = [
      assistantTurn("研究员", "请做自我介绍"),
    ];
    const filtered = dedupeMemberTurnsAgainstDelegation(turns, "请做自我介绍");
    expect(filtered).toHaveLength(0);
  });
});

describe("extractMemberDelegations", () => {
  it("reads submit_to_agent prompts from leader traces", () => {
    const leaderTurns: ChatTurn[] = [
      {
        ...assistantTurn("分析团队·leader"),
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
      },
    ];
    const delegations = extractMemberDelegations(leaderTurns, team, []);
    expect(delegations).toHaveLength(1);
    expect(delegations[0].memberName).toBe("研究员");
  });

  it("reads chat_with_agent prompts from leader traces", () => {
    const leaderTurns: ChatTurn[] = [
      {
        ...assistantTurn("分析团队·leader"),
        traceEvents: [
          {
            type: "trace",
            step: "tool_call_end",
            tool_name: "chat_with_agent",
            tool_call_id: "c1",
            detail: JSON.stringify({
              arguments: { to_agent: "研究员", text: "请做自我介绍" },
            }),
          },
        ],
      },
    ];
    const delegations = extractMemberDelegations(leaderTurns, team, []);
    expect(delegations).toHaveLength(1);
    expect(delegations[0].memberName).toBe("研究员");
    expect(delegations[0].text).toBe("请做自我介绍");
    expect(latestDelegationForMember(delegations, "研究员")?.text).toBe(
      "请做自我介绍",
    );
  });

  it("reads delegations from normalized trace events (type is the step)", () => {
    // Trace events stored on turns are normalized: ``type`` becomes the step
    // name, not "trace". Extraction must still pick them up. detail also uses
    // the flat (non-nested) shape produced by native submit_to_agent calls.
    const leaderTurns: ChatTurn[] = [
      {
        ...assistantTurn("分析团队·leader"),
        traceEvents: [
          {
            type: "tool_call_end",
            step: "tool_call_end",
            tool_name: "submit_to_agent",
            tool_call_id: "c1",
            detail: JSON.stringify({ to_agent: "研究员", text: "请做自我介绍" }),
          },
        ],
      },
    ];
    const delegations = extractMemberDelegations(leaderTurns, team, []);
    expect(delegations).toHaveLength(1);
    expect(delegations[0].memberName).toBe("研究员");
    expect(delegations[0].text).toBe("请做自我介绍");
  });

  it("reads delegations from LIVE events (type set, no step field)", () => {
    // Live SSE trace events carry the step name on ``type`` and have no
    // ``step`` field at all (step is only added during disk persistence).
    const leaderTurns: ChatTurn[] = [
      {
        ...assistantTurn("分析团队·leader"),
        traceEvents: [
          {
            type: "tool_call_end",
            tool_name: "submit_to_agent",
            tool_call_id: "c1",
            member_name: "研究员",
            detail: JSON.stringify({
              to_agent: "emp_fb2f4efd84",
              text: "请做自我介绍",
            }),
          },
        ],
      },
    ];
    const delegations = extractMemberDelegations(leaderTurns, team, []);
    expect(delegations).toHaveLength(1);
    expect(delegations[0].memberName).toBe("研究员");
    expect(delegations[0].text).toBe("请做自我介绍");
  });

  it("resolves the member via backend-tagged member_name (no employee map)", () => {
    // The backend tags the delegation with the resolved roster name, so an
    // agent-id ``to_agent`` still maps to the right member tab without any
    // employee ↔ roster lookup table on the frontend.
    const leaderTurns: ChatTurn[] = [
      {
        ...assistantTurn("分析团队·leader"),
        traceEvents: [
          {
            type: "tool_call_end",
            step: "tool_call_end",
            tool_name: "submit_to_agent",
            tool_call_id: "c1",
            member_name: "研究员",
            detail: JSON.stringify({
              to_agent: "emp_fb2f4efd84",
              text: "请做自我介绍",
            }),
          },
        ],
      },
    ];
    const delegations = extractMemberDelegations(leaderTurns, team, []);
    expect(delegations).toHaveLength(1);
    expect(delegations[0].memberName).toBe("研究员");
    expect(delegations[0].text).toBe("请做自我介绍");
  });
});
