import { describe, expect, it } from "vitest";

import {

  EMPLOYEE_CREATE_DRAFT,

  EMPLOYEE_CREATE_MARKER,

  EMPLOYEE_CREATOR_SKILL,

  EMPLOYEE_CREATOR_TAG,

  EMPLOYEE_WIZARD_STEPS,

  buildEmployeeCreateMessage,

  buildEmployeeDesc,

  containsPlaceholder,

  deriveEmployeeTags,

  parseEmployeeTags,

  suggestEmployeeSkills,

  validateEmployeeCreateValues,

} from "./employeeCreate";



describe("employeeCreate", () => {

  it("exports stable skill id and draft template", () => {

    expect(EMPLOYEE_CREATOR_SKILL).toBe("employee-creator");

    expect(EMPLOYEE_CREATOR_TAG).toBe("专家创建");

    expect(EMPLOYEE_CREATE_DRAFT).toContain("XXX");

    expect(EMPLOYEE_CREATE_DRAFT).toContain(EMPLOYEE_CREATE_MARKER);

  });



  it("defines three wizard steps matching skill workflow", () => {

    expect(EMPLOYEE_WIZARD_STEPS).toHaveLength(3);

    expect(EMPLOYEE_WIZARD_STEPS.map((s) => s.title)).toEqual([

      "基本信息",

      "技能",

      "确认创建",

    ]);

  });



  it("detects placeholder values", () => {

    expect(containsPlaceholder("XXX")).toBe(true);

    expect(containsPlaceholder("[请补充行业背景]")).toBe(true);

    expect(containsPlaceholder("销售助理")).toBe(false);

  });



  it("validates required fields and rejects placeholders", () => {

    expect(

      validateEmployeeCreateValues({

        name: "舆情分析专家",

        specialty: "社媒监测",

        background: "5 年 PR",

      }),

    ).toBeNull();

    expect(validateEmployeeCreateValues({ name: "XXX", specialty: "a", background: "b" })).toMatch(

      /占位符/,

    );

    expect(validateEmployeeCreateValues({ name: "", specialty: "a", background: "b" })).toMatch(

      /名称/,

    );

  });



  it("builds desc and natural-language create message", () => {

    const values = {

      name: "舆情分析专家",

      specialty: "社媒监测与日报撰写",

      background: "5 年 PR 经验",

    };

    expect(buildEmployeeDesc(values)).toContain("社媒监测");

    expect(buildEmployeeDesc(values)).toContain("5 年 PR");

    expect(buildEmployeeCreateMessage(values)).toContain("舆情分析专家");

    expect(buildEmployeeCreateMessage(values)).not.toContain("XXX");

    expect(buildEmployeeCreateMessage(values)).toContain("挂载技能");

  });



  it("suggests skills from specialty keywords", () => {

    expect(suggestEmployeeSkills("Excel 数据分析")).toContain("xlsx");

    expect(suggestEmployeeSkills("撰写 Word 报告")).toContain("docx");

    expect(suggestEmployeeSkills("通用助手")).toEqual(["make_plan", "file_reader"]);

  });



  it("defaults tags to AgentDesk when empty", () => {

    expect(parseEmployeeTags("")).toEqual(["AgentDesk"]);

    expect(parseEmployeeTags("销售, 客服")).toEqual(["销售", "客服"]);

  });



  it("derives tags from specialty for auto-tagging on create", () => {

    expect(deriveEmployeeTags("客户跟进与日报")).toEqual(["AgentDesk", "客户跟进与日报"]);

    expect(deriveEmployeeTags("")).toEqual(["AgentDesk"]);

  });

});


