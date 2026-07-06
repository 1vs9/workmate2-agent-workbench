import { describe, expect, it } from "vitest";
import { resolveSkillIconKey, resolveMarketSourceIconKey } from "./skillIcon";

describe("resolveSkillIconKey", () => {
  it("uses explicit icon key when valid", () => {
    expect(resolveSkillIconKey({ name: "anything", icon: "table" })).toBe("table");
  });

  it("ignores legacy emoji and derives from skill name", () => {
    expect(resolveSkillIconKey({ name: "docx", emoji: "📄" })).toBe("fileText");
    expect(resolveSkillIconKey({ name: "xlsx", emoji: "📊" })).toBe("table");
  });

  it("maps known pool names to tool icons", () => {
    expect(resolveSkillIconKey({ name: "browser_visible" })).toBe("global");
    expect(resolveSkillIconKey({ name: "make-skill" })).toBe("bulb");
    expect(resolveSkillIconKey({ name: "employee-creator" })).toBe("idcard");
    expect(resolveSkillIconKey({ name: "pptx" })).toBe("presentation");
    expect(resolveSkillIconKey({ name: "stock_analyst" })).toBe("lineChart");
    expect(resolveSkillIconKey({ name: "股市分析" })).toBe("lineChart");
  });

  it("returns deterministic fallback for unknown skills", () => {
    const a = resolveSkillIconKey({ name: "custom-widget-alpha" });
    const b = resolveSkillIconKey({ name: "custom-widget-alpha" });
    expect(a).toBe(b);
    expect(a).not.toBe("🧩");
  });
});

describe("resolveMarketSourceIconKey", () => {
  it("maps hub sources to tool icons", () => {
    expect(resolveMarketSourceIconKey("clawhub")).toBe("shop");
    expect(resolveMarketSourceIconKey("modelscope")).toBe("cloud");
    expect(resolveMarketSourceIconKey("unknown")).toBe("api");
    expect(resolveMarketSourceIconKey("hub", true)).toBe("link");
  });
});
