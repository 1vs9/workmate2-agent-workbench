import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import PullUpSelect from "./PullUpSelect";

describe("PullUpSelect", () => {
  it("calls onClose after header selection", () => {
    const onHeaderSelect = vi.fn();
    const onClose = vi.fn();

    render(
      <PullUpSelect
        open
        headerTitle="不使用技能"
        headerSubtitle="不附加任何技能"
        headerSelected
        onHeaderSelect={onHeaderSelect}
        onClose={onClose}
        sections={[{ label: "技能", options: [{ id: "demo", label: "demo" }] }]}
        onSelect={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /不使用技能/i }));

    expect(onHeaderSelect).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("renders tool icons instead of portrait avatars in skill mode", () => {
    const { container } = render(
      <PullUpSelect
        open
        iconMode="skill"
        headerTitle="不使用技能"
        headerSubtitle="不附加任何技能"
        onHeaderSelect={vi.fn()}
        sections={[
          {
            label: "技能",
            options: [
              { id: "employee-creator", label: "employee-creator" },
              { id: "pptx", label: "pptx" },
            ],
          },
        ]}
        onSelect={vi.fn()}
      />,
    );

    expect(container.querySelectorAll("img")).toHaveLength(0);
    expect(container.querySelectorAll(".anticon")).not.toHaveLength(0);
  });
});
