/** AgentDesk「添加员工」引导流程（对齐 employee-creator 技能工作流）。 */



export const EMPLOYEE_CREATOR_SKILL = "employee-creator";



export const EMPLOYEE_CREATE_DRAFT =

  "帮我创建一个 XXX 专家，擅长 XXXXX。TA 的经验背景是：[请补充行业背景、相关经验]";



export const EMPLOYEE_CREATE_MARKER = "[请补充行业背景、相关经验]";



export const EMPLOYEE_CREATOR_TAG = "专家创建";



export const EMPLOYEE_WIZARD_STEPS = [

  { title: "基本信息", description: "名称与职责" },

  { title: "技能", description: "挂载技能（可选）" },

  { title: "确认创建", description: "核对摘要" },

] as const;



export interface EmployeeCreateFormValues {

  name: string;

  specialty: string;

  background: string;

  skillNames?: string[];

}



const PLACEHOLDER_RE = /XXX+|\[请补充[^\]]*\]|…{2,}/i;



export function containsPlaceholder(text: string): boolean {

  const t = String(text || "").trim();

  if (!t) return true;

  return PLACEHOLDER_RE.test(t);

}



export function parseEmployeeTags(tagsText?: string): string[] {

  const tags = (tagsText ?? "")

    .split(",")

    .map((t) => t.trim())

    .filter(Boolean);

  return tags.length ? tags : ["AgentDesk"];

}



/** Auto tags for new employees: AgentDesk plus optional specialty hint. */

export function deriveEmployeeTags(specialty?: string): string[] {

  const tags = ["AgentDesk"];

  const firstPart = (specialty ?? "")

    .trim()

    .split(/[，,、；;。.]/)[0]

    ?.trim();

  if (firstPart && firstPart.length <= 12 && !tags.includes(firstPart)) {

    tags.push(firstPart);

  }

  return tags;

}



/** 将表单字段合成为岗位卡片的职责描述。 */

export function buildEmployeeDesc(values: Pick<EmployeeCreateFormValues, "specialty" | "background">): string {

  const specialty = values.specialty.trim();

  const background = values.background.trim();

  return `专长：${specialty}。经验背景：${background}`;

}



const SKILL_SUGGESTION_RULES: Array<{ pattern: RegExp; skills: string[] }> = [
  { pattern: /word|文档|报告|docx/i, skills: ["docx", "make_plan"] },
  { pattern: /excel|表格|数据|xlsx|分析/i, skills: ["xlsx", "make_plan"] },
  { pattern: /ppt|演示|幻灯|汇报/i, skills: ["pptx", "make_plan"] },
  { pattern: /pdf/i, skills: ["pdf", "file_reader"] },
  { pattern: /消息|飞书|通知|沟通|channel/i, skills: ["channel_message", "make_plan"] },
  { pattern: /新闻|资讯|舆情|监测/i, skills: ["news", "file_reader"] },
  { pattern: /计划|规划|方案|sop|流程/i, skills: ["make_plan", "docx"] },
  { pattern: /代码|开发|编程|debug/i, skills: ["make_plan", "file_reader"] },
];

const DEFAULT_EMPLOYEE_SKILLS = ["make_plan", "file_reader"];

/** 根据专长关键词推荐 2–4 个 pool 技能名（供向导默认选中与对话式创建）。 */
export function suggestEmployeeSkills(specialty: string, background = ""): string[] {
  const text = `${specialty} ${background}`.trim();
  const picked: string[] = [];
  for (const rule of SKILL_SUGGESTION_RULES) {
    if (rule.pattern.test(text)) {
      for (const skill of rule.skills) {
        if (!picked.includes(skill)) picked.push(skill);
      }
    }
  }
  if (picked.length === 0) {
    return [...DEFAULT_EMPLOYEE_SKILLS];
  }
  return picked.slice(0, 4);
}

/** 生成与 composer 模板一致的自然语言消息（供对话式创建复用）。 */
export function buildEmployeeCreateMessage(values: EmployeeCreateFormValues): string {
  const name = values.name.trim();
  const specialty = values.specialty.trim();
  const background = values.background.trim();
  const explicitSkills = (values.skillNames ?? []).filter(Boolean);
  const skills =
    explicitSkills.length > 0
      ? explicitSkills
      : suggestEmployeeSkills(specialty, background);
  const skillHint =
    skills.length > 0
      ? ` 请为该员工自动挂载技能：${skills.join("、")}。`
      : "";
  return `帮我创建一个 ${name} 专家，擅长 ${specialty}。TA 的经验背景是：${background}。${skillHint}`;
}



export function validateEmployeeCreateValues(

  values: Partial<EmployeeCreateFormValues>,

): string | null {

  const name = String(values.name ?? "").trim();

  const specialty = String(values.specialty ?? "").trim();

  const background = String(values.background ?? "").trim();



  if (!name) return "请输入员工名称";

  if (containsPlaceholder(name)) return "请填写真实的员工名称，不要使用占位符";

  if (!specialty) return "请填写擅长领域";

  if (containsPlaceholder(specialty)) return "请填写真实的擅长领域，不要使用占位符";

  if (!background) return "请填写经验背景";

  if (containsPlaceholder(background)) return "请填写真实的经验背景，不要使用占位符";

  return null;

}


