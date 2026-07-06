import { describe, expect, it } from "vitest";
import type { ChatTurn } from "./chatStreamReducer";
import { partitionTeamConversation } from "./partitionTeamConversation";

const team = {
  id: "t1",
  name: "深度调研团队",
  tags: [],
  desc: "",
  avatar: "",
  members: ["研究员", "审查官", "主笔"],
  leader: "PM",
};

function assistantTurn(name: string, text = ""): ChatTurn {
  return {
    id: `a-${name}`,
    role: "assistant",
    name,
    avatarKind: "team",
    text,
    traceEvents: [],
    streaming: false,
  };
}

describe("partitionTeamConversation attribution", () => {
  it("keeps a member reply in its own bucket even if it names teammates", () => {
    // Regression: a member self-introduction that mentions other members must
    // stay attributed to that member (sender is authoritative), not reassigned
    // to the leader session.
    const mentionsOthers =
      "你好，我是规划者，我会把任务拆解后分发给研究员去执行。";
    const turns: ChatTurn[] = [
      assistantTurn("研究员", "我是研究员，负责检索。"),
      assistantTurn("审查官", mentionsOthers),
    ];
    const partition = partitionTeamConversation(turns, team);
    expect(partition.leaderTurns.some((turn) => turn.text === mentionsOthers)).toBe(
      false,
    );
    expect(partition.memberTurnsByName.get("审查官")).toEqual([
      expect.objectContaining({ text: mentionsOthers }),
    ]);
    expect(partition.memberTurnsByName.get("研究员")).toEqual([
      expect.objectContaining({ text: "我是研究员，负责检索。" }),
    ]);
  });
});
