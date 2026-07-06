import type { ReactNode } from "react";
import {
  ApiOutlined,
  BulbOutlined,
  CalendarOutlined,
  CloudOutlined,
  CodeOutlined,
  FilePdfOutlined,
  FilePptOutlined,
  FileTextOutlined,
  FolderOutlined,
  GlobalOutlined,
  IdcardOutlined,
  LineChartOutlined,
  LinkOutlined,
  MailOutlined,
  MessageOutlined,
  PaperClipOutlined,
  ReadOutlined,
  SafetyOutlined,
  SearchOutlined,
  ShopOutlined,
  TableOutlined,
  TeamOutlined,
  ToolOutlined,
} from "@ant-design/icons";

/** Stable tool-style icon keys for skills (no emoji / personification). */
export const SKILL_ICON_KEYS = [
  "fileText",
  "table",
  "presentation",
  "filePdf",
  "global",
  "read",
  "folder",
  "bulb",
  "team",
  "idcard",
  "calendar",
  "lineChart",
  "message",
  "mail",
  "code",
  "search",
  "cloud",
  "shop",
  "link",
  "api",
  "security",
  "tool",
] as const;

export type SkillIconKey = (typeof SKILL_ICON_KEYS)[number];

const ICON_COMPONENTS: Record<SkillIconKey, typeof FileTextOutlined> = {
  fileText: FileTextOutlined,
  table: TableOutlined,
  presentation: FilePptOutlined,
  filePdf: FilePdfOutlined,
  global: GlobalOutlined,
  read: ReadOutlined,
  folder: FolderOutlined,
  bulb: BulbOutlined,
  team: TeamOutlined,
  idcard: IdcardOutlined,
  calendar: CalendarOutlined,
  lineChart: LineChartOutlined,
  message: MessageOutlined,
  mail: MailOutlined,
  code: CodeOutlined,
  search: SearchOutlined,
  cloud: CloudOutlined,
  shop: ShopOutlined,
  link: LinkOutlined,
  api: ApiOutlined,
  security: SafetyOutlined,
  tool: ToolOutlined,
};

/** Explicit pool / skill name → icon (longest match wins in resolver). */
const SKILL_NAME_ICON_RULES: Array<{ pattern: RegExp; icon: SkillIconKey }> = [
  { pattern: /^docx$|^word/i, icon: "fileText" },
  { pattern: /^xlsx$|^excel/i, icon: "table" },
  { pattern: /^pptx$|^ppt/i, icon: "presentation" },
  { pattern: /^pdf$/i, icon: "filePdf" },
  { pattern: /browser|web|crawl/i, icon: "global" },
  { pattern: /^news$|资讯|舆情/i, icon: "read" },
  { pattern: /make[_-]?plan|计划|规划/i, icon: "calendar" },
  { pattern: /file[_-]?reader|文件阅读/i, icon: "read" },
  { pattern: /make[_-]?skill|skill[_-]?creator|技能创作/i, icon: "bulb" },
  { pattern: /multi[_-]?agent|协作/i, icon: "team" },
  { pattern: /employee[_-]?creator|员工创建/i, icon: "idcard" },
  { pattern: /stock|finance|chart|分析|数据/i, icon: "lineChart" },
  { pattern: /channel[_-]?message|消息|飞书|slack|dingtalk/i, icon: "message" },
  { pattern: /himalaya|mail|email|邮件/i, icon: "mail" },
  { pattern: /cron|schedule|定时/i, icon: "calendar" },
  { pattern: /guidance|qa|index/i, icon: "search" },
  { pattern: /chat[_-]?with/i, icon: "message" },
  { pattern: /cdp|browser_cdp/i, icon: "api" },
  { pattern: /security|auth|encrypt|合规/i, icon: "security" },
  { pattern: /code|git|dev|script|编程/i, icon: "code" },
];

const FALLBACK_ICON_KEYS: SkillIconKey[] = [
  "tool",
  "api",
  "code",
  "search",
  "folder",
  "fileText",
  "read",
  "bulb",
];

const VALID_ICON_KEY = new Set<string>(SKILL_ICON_KEYS);

export function isSkillIconKey(value: string | undefined | null): value is SkillIconKey {
  return Boolean(value && VALID_ICON_KEY.has(value));
}

function normalizeSkillToken(value: string): string {
  return value.trim().toLowerCase().replace(/[\s_]+/g, "-");
}

function matchSkillNameIcon(name: string, description = ""): SkillIconKey | null {
  const text = `${normalizeSkillToken(name)} ${description}`.trim();
  for (const rule of SKILL_NAME_ICON_RULES) {
    if (rule.pattern.test(text)) return rule.icon;
  }
  return null;
}

function hashSkillIconKey(seed: string): SkillIconKey {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return FALLBACK_ICON_KEYS[hash % FALLBACK_ICON_KEYS.length];
}

export interface ResolveSkillIconInput {
  name?: string;
  poolName?: string;
  description?: string;
  category?: string;
  /** Preferred explicit icon key from catalog or API metadata. */
  icon?: string | null;
  /** Legacy metadata — ignored for display; name/category used instead. */
  emoji?: string | null;
}

/** Resolve a deterministic tool icon key for a skill. Never returns emoji. */
export function resolveSkillIconKey(input: ResolveSkillIconInput): SkillIconKey {
  const explicit = input.icon?.trim();
  if (isSkillIconKey(explicit)) {
    return explicit;
  }

  const candidates = [input.poolName, input.name].filter(Boolean) as string[];
  for (const candidate of candidates) {
    const matched = matchSkillNameIcon(candidate, input.description ?? "");
    if (matched) return matched;
  }

  if (input.category) {
    const cat = input.category.toLowerCase();
    if (cat.includes("办公") || cat.includes("文档") || cat.includes("content")) return "fileText";
    if (cat.includes("数据") || cat.includes("data")) return "lineChart";
    if (cat.includes("开发") || cat.includes("dev")) return "code";
    if (cat.includes("资讯") || cat.includes("news")) return "read";
    if (cat.includes("协作") || cat.includes("通讯")) return "message";
    if (cat.includes("安全")) return "security";
    if (cat.includes("效率")) return "calendar";
  }

  const seed = candidates.join("|") || "skill";
  return hashSkillIconKey(seed);
}

export interface SkillIconProps {
  iconKey?: SkillIconKey | string | null;
  name?: string;
  poolName?: string;
  description?: string;
  category?: string;
  icon?: string | null;
  emoji?: string | null;
  className?: string;
  /** Ant Design icon font-size style */
  style?: React.CSSProperties;
}

export function SkillIcon({
  iconKey,
  name,
  poolName,
  description,
  category,
  icon,
  emoji,
  className = "text-base",
  style,
}: SkillIconProps): ReactNode {
  let resolved: SkillIconKey;
  if (isSkillIconKey(iconKey ?? undefined)) {
    resolved = iconKey as SkillIconKey;
  } else {
    resolved = resolveSkillIconKey({ name, poolName, description, category, icon, emoji });
  }
  const IconComponent = ICON_COMPONENTS[resolved];
  return <IconComponent className={className} style={style} aria-hidden />;
}

/** File-tree attachment icons (non-emoji). */
export function SkillFileTreeIcon({ isMarkdown }: { isMarkdown: boolean }): ReactNode {
  if (isMarkdown) {
    return <FileTextOutlined className="mr-1 text-[12px] text-gray-500" aria-hidden />;
  }
  return <PaperClipOutlined className="mr-1 text-[12px] text-gray-500" aria-hidden />;
}

/** Hub market source → tool icon (replaces emoji market badges). */
export function resolveMarketSourceIconKey(source: string, hasIconUrl = false): SkillIconKey {
  if (hasIconUrl) return "link";
  const normalized = source.toLowerCase();
  if (normalized.includes("claw")) return "shop";
  if (normalized.includes("model")) return "cloud";
  if (normalized.includes("aliyun")) return "cloud";
  if (normalized.includes("skillsmp")) return "shop";
  return "api";
}
