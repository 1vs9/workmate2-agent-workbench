/** Curated Skill Market catalog — local stub when live hub search is empty. */

import type { SkillIconKey } from "../utils/skillIcon";

export const SKILL_CATEGORIES = [
  "全部",
  "开发工具",
  "办公协同",
  "效率工具",
  "内容创作",
  "信息资讯",
  "教育学习",
  "生活服务",
  "商业运营",
] as const;

export type SkillCategory = (typeof SKILL_CATEGORIES)[number];

export interface CuratedSkill {
  id: string;
  name: string;
  description: string;
  icon: SkillIconKey;
  iconTone: string;
  category: SkillCategory;
  /** Pool / workspace skill name used by mount API. */
  poolName?: string;
  /** Remote hub URL for pool import (ClawHub, ModelScope, etc.). */
  sourceUrl?: string;
  featured?: boolean;
  provider?: string;
}

export const CURATED_SKILLS: CuratedSkill[] = [
  {
    id: "docx-zh",
    name: "Word 文档",
    description: "创建与编辑 Word 文档，支持模板、批注与格式整理。",
    icon: "fileText",
    iconTone: "bg-blue-50 text-blue-600",
    category: "办公协同",
    poolName: "docx",
    featured: true,
    provider: "AgentDesk",
  },
  {
    id: "xlsx-zh",
    name: "Excel 表格",
    description: "读写 Excel，支持公式、透视与数据清洗导出。",
    icon: "table",
    iconTone: "bg-emerald-50 text-emerald-600",
    category: "办公协同",
    poolName: "xlsx",
    featured: true,
    provider: "AgentDesk",
  },
  {
    id: "pptx-zh",
    name: "PPT 演示",
    description: "生成与修改演示文稿，排版幻灯片与演讲备注。",
    icon: "presentation",
    iconTone: "bg-orange-50 text-orange-600",
    category: "内容创作",
    poolName: "pptx",
    featured: true,
    provider: "AgentDesk",
  },
  {
    id: "pdf-zh",
    name: "PDF 处理",
    description: "解析、合并、拆分 PDF，提取文本与页面结构。",
    icon: "filePdf",
    iconTone: "bg-rose-50 text-rose-600",
    category: "办公协同",
    poolName: "pdf",
    featured: true,
    provider: "AgentDesk",
  },
  {
    id: "browser_visible-zh",
    name: "可见浏览器",
    description: "可视化浏览器自动化，完成网页操作与信息采集。",
    icon: "global",
    iconTone: "bg-sky-50 text-sky-600",
    category: "开发工具",
    poolName: "browser_visible",
    featured: true,
    provider: "AgentDesk",
  },
  {
    id: "news-zh",
    name: "新闻资讯",
    description: "检索与汇总新闻热点，输出结构化资讯摘要。",
    icon: "read",
    iconTone: "bg-amber-50 text-amber-600",
    category: "信息资讯",
    poolName: "news",
    featured: true,
    provider: "AgentDesk",
  },
  {
    id: "make_plan-zh",
    name: "计划制定",
    description: "将复杂目标拆解为可执行步骤与里程碑计划。",
    icon: "calendar",
    iconTone: "bg-indigo-50 text-indigo-600",
    category: "效率工具",
    poolName: "make_plan",
    featured: true,
    provider: "AgentDesk",
  },
  {
    id: "file_reader-zh",
    name: "文件阅读",
    description: "读取本地与云端文件，提取关键信息供对话使用。",
    icon: "folder",
    iconTone: "bg-slate-100 text-slate-600",
    category: "效率工具",
    poolName: "file_reader",
    provider: "AgentDesk",
  },
  {
    id: "make-skill-zh",
    name: "技能创作",
    description: "引导创建符合规范的 SKILL.md 与可复用技能包。",
    icon: "bulb",
    iconTone: "bg-purple-50 text-purple-600",
    category: "开发工具",
    poolName: "make-skill",
    provider: "AgentDesk",
  },
  {
    id: "multi_agent_collaboration-zh",
    name: "多智能体协作",
    description: "编排多个智能体分工协作完成复杂任务。",
    icon: "team",
    iconTone: "bg-cyan-50 text-cyan-600",
    category: "商业运营",
    poolName: "multi_agent_collaboration",
    provider: "AgentDesk",
  },
  {
    id: "employee-creator-zh",
    name: "员工创建",
    description: "引导创建 AgentDesk 数字员工（岗位智能体）并加入团队。",
    icon: "idcard",
    iconTone: "bg-teal-50 text-teal-700",
    category: "商业运营",
    poolName: "employee-creator",
    featured: true,
    provider: "AgentDesk",
  },
  {
    id: "clawhub-word-docx",
    name: "Word 文档（ClawHub）",
    description: "ClawHub 社区版 Word 文档处理技能。",
    icon: "fileText",
    iconTone: "bg-cyan-50 text-cyan-600",
    category: "办公协同",
    sourceUrl: "https://clawhub.ai/ivangdavila/word-docx",
    provider: "clawhub",
  },
  {
    id: "clawhub-excel-xlsx",
    name: "Excel 表格（ClawHub）",
    description: "ClawHub 社区版 Excel 读写与表格处理。",
    icon: "table",
    iconTone: "bg-lime-50 text-lime-600",
    category: "办公协同",
    sourceUrl: "https://clawhub.ai/ivangdavila/excel-xlsx",
    provider: "clawhub",
  },
  {
    id: "ms-skill-creator",
    name: "Skill Creator",
    description: "ModelScope 技能创作模板，快速生成可安装技能。",
    icon: "bulb",
    iconTone: "bg-violet-50 text-violet-600",
    category: "开发工具",
    sourceUrl: "https://modelscope.cn/skills/@anthropics/skill-creator",
    provider: "modelscope",
  },
];

export function filterCuratedSkills(options: {
  category?: SkillCategory;
  query?: string;
  featuredOnly?: boolean;
}): CuratedSkill[] {
  const q = (options.query ?? "").trim().toLowerCase();
  return CURATED_SKILLS.filter((skill) => {
    if (options.featuredOnly && !skill.featured) return false;
    if (options.category && options.category !== "全部" && skill.category !== options.category) {
      return false;
    }
    if (!q) return true;
    return (
      skill.name.toLowerCase().includes(q) ||
      skill.description.toLowerCase().includes(q) ||
      (skill.poolName ?? "").toLowerCase().includes(q)
    );
  });
}

/** SkillHub cloud search categories (client-side keyword classification). */
export const HUB_CATEGORIES = [
  "全部",
  "AI 智能",
  "开发工具",
  "效率提升",
  "数据分析",
  "内容创作",
  "安全合规",
  "通讯协作",
] as const;

export type HubCategory = (typeof HUB_CATEGORIES)[number];

type HubCategoryRule = Exclude<HubCategory, "全部">;

const HUB_CATEGORY_KEYWORDS: Record<HubCategoryRule, readonly string[]> = {
  "AI 智能": [
    "ai",
    "agent",
    "llm",
    "gpt",
    "claude",
    "model",
    "intelligent",
    "agentic",
    "智能",
    "大模型",
  ],
  开发工具: [
    "code",
    "git",
    "api",
    "docker",
    "dev",
    "python",
    "script",
    "编程",
    "代码",
    "开发",
  ],
  效率提升: [
    "automation",
    "workflow",
    "cron",
    "schedule",
    "productivity",
    "效率",
    "自动化",
    "计划",
  ],
  数据分析: [
    "data",
    "analytics",
    "excel",
    "chart",
    "sql",
    "database",
    "数据",
    "分析",
    "统计",
  ],
  内容创作: [
    "doc",
    "word",
    "ppt",
    "pdf",
    "write",
    "content",
    "media",
    "文档",
    "创作",
    "写作",
  ],
  安全合规: [
    "security",
    "auth",
    "encrypt",
    "compliance",
    "audit",
    "vet",
    "安全",
    "合规",
    "加密",
  ],
  通讯协作: [
    "email",
    "slack",
    "wechat",
    "dingtalk",
    "whatsapp",
    "message",
    "channel",
    "邮件",
    "消息",
    "协作",
    "通讯",
  ],
};

const HUB_CATEGORY_ORDER: HubCategoryRule[] = [
  "AI 智能",
  "开发工具",
  "效率提升",
  "数据分析",
  "内容创作",
  "安全合规",
  "通讯协作",
];

function hubSkillText(result: {
  name: string;
  description?: string | null;
  slug?: string;
}): string {
  return [result.name, result.description ?? "", result.slug ?? ""]
    .join(" ")
    .toLowerCase();
}

/** Classify a SkillHub search result by name, description, and slug keywords. */
export function classifyHubSkill(result: {
  name: string;
  description?: string | null;
  slug?: string;
}): HubCategoryRule | null {
  const text = hubSkillText(result);
  for (const category of HUB_CATEGORY_ORDER) {
    if (HUB_CATEGORY_KEYWORDS[category].some((kw) => text.includes(kw))) {
      return category;
    }
  }
  return null;
}

export function filterHubResults<T extends { name: string; description?: string | null; slug?: string }>(
  results: T[],
  category: HubCategory,
): T[] {
  if (category === "全部") return results;
  return results.filter((result) => classifyHubSkill(result) === category);
}

/** Client-side keyword match for skill name, description, slug, or pool name. */
export function matchesSkillSearchQuery(
  query: string,
  fields: {
    name?: string;
    description?: string | null;
    slug?: string;
    poolName?: string;
  },
): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const text = [
    fields.name ?? "",
    fields.description ?? "",
    fields.slug ?? "",
    fields.poolName ?? "",
  ]
    .join(" ")
    .toLowerCase();
  return text.includes(q);
}
