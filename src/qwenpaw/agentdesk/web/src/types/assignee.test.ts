import { describe, expect, it } from "vitest";
import { dedupeEmployees } from "./assignee";

describe("dedupeEmployees", () => {
  it("drops store row when agent profile already represents the employee", () => {
    const employees = [
      {
        name: "舆情分析师",
        id: "emp_abc123",
        agent_id: "emp_abc123",
        desc: "from profile",
      },
      {
        name: "舆情分析师",
        desc: "from store",
      },
    ];

    const deduped = dedupeEmployees(employees);

    expect(deduped).toHaveLength(1);
    expect(deduped[0].agent_id).toBe("emp_abc123");
  });

  it("drops rows with the same stable id", () => {
    const employees = [
      { name: "321321", id: "emp_dup", agent_id: "emp_dup", desc: "a" },
      { name: "321321", id: "emp_dup", agent_id: "emp_dup", desc: "b" },
    ];

    expect(dedupeEmployees(employees)).toHaveLength(1);
  });

  it("keeps distinct employees with different ids", () => {
    const employees = [
      { name: "Alice", id: "emp_a", agent_id: "emp_a", desc: "" },
      { name: "Bob", id: "emp_b", agent_id: "emp_b", desc: "" },
    ];

    expect(dedupeEmployees(employees)).toHaveLength(2);
  });
});
