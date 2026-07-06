import { useCallback, useEffect, useMemo, useState } from "react";
import { Dropdown, Input, message } from "antd";
import { DownOutlined, PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import PageError from "../../components/layout/PageError";
import PageHeader from "../../components/layout/PageHeader";
import SkillDetailDrawer from "../../components/skills/SkillDetailDrawer";
import SkillMarketCard from "../../components/skills/SkillMarketCard";
import UploadSkillModal from "../../components/skills/UploadSkillModal";
import { useAsyncList } from "../../hooks/useAsyncList";
import marketApi, { type MarketResult } from "../../api/market";
import { skillsApi, type SkillItem } from "../../api/skills";
import {
  CURATED_SKILLS,
  HUB_CATEGORIES,
  classifyHubSkill,
  filterCuratedSkills,
  filterHubResults,
  matchesSkillSearchQuery,
  type CuratedSkill,
  type HubCategory,
} from "../../constants/skillCatalog";
import { useAppStore } from "../../store/appStore";
import { useComposerStore } from "../../store/composerStore";
import { useSkillsStore } from "../../store/skillsStore";
import { openChatWithSkill } from "../../utils/openChatWithSkill";
import { openSkillTaskFlow } from "../../utils/openSkillTaskFlow";
import {
  resolveInstalledSkillChatName,
  resolveMarketSkillChatName,
} from "../../utils/resolveSkillChatName";
import { resolveMarketSourceIconKey } from "../../utils/skillIcon";

type MainTab = "market" | "installed";

/** How many results to request per cloud provider. */
const HUB_FETCH_LIMIT = 30;

/** Empty search uses browse mode (ClawHub/SkillsMP ignore blank `q`). */
const HUB_BROWSE_QUERY = "skill";

function marketTone(result: MarketResult): string {
  const source = result.source.toLowerCase();
  if (source.includes("claw")) return "bg-orange-50 text-orange-600";
  if (source.includes("model")) return "bg-blue-50 text-blue-600";
  if (source.includes("aliyun")) return "bg-sky-50 text-sky-600";
  if (source.includes("skillsmp")) return "bg-violet-50 text-violet-600";
  return "bg-emerald-50 text-emerald-600";
}

function isGenericHubSkillName(name: string): boolean {
  const normalized = name.trim().toLowerCase();
  return !normalized || normalized === "skill" || normalized === "skills";
}

function humanizeHubSlug(slug: string): string {
  let base = slug.trim();
  if (base.endsWith("-skill")) base = base.slice(0, -"-skill".length);
  else if (base.endsWith("_skill")) base = base.slice(0, -"_skill".length);
  const parts = base.split(/[-_]+/).filter(Boolean);
  if (parts.length === 0) return slug;
  return parts.map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function titleFromHubDescription(description: string): string {
  const text = description.trim();
  if (!text) return "";
  for (const sep of [" — ", " – ", " - "]) {
    const idx = text.indexOf(sep);
    if (idx >= 0) {
      const head = text.slice(0, idx).trim();
      if (head) return head;
    }
  }
  const dot = text.indexOf(".");
  if (dot > 0 && dot <= 120) return text.slice(0, dot).trim();
  if (text.length <= 80) return text;
  const truncated = text.slice(0, 80).replace(/\s+\S*$/, "").trim();
  return truncated || text.slice(0, 80).trim();
}

function resolveMarketDisplayName(result: MarketResult): string {
  if (!isGenericHubSkillName(result.name)) return result.name;
  const description = (result.description ?? "").trim();
  if (description) {
    const title = titleFromHubDescription(description);
    if (title) return title;
  }
  if (result.slug) return humanizeHubSlug(result.slug);
  return result.name || "Skill";
}

function marketResultKey(result: MarketResult): string {
  return `${result.source}:${result.slug}`;
}

function sourceUrlTail(url: string): string {
  const trimmed = url.trim().replace(/\/+$/, "");
  const tail = trimmed.split("/").pop() ?? "";
  return tail.toLowerCase();
}

/** Keys for deduping hub hits against curated remote install links only. */
function buildCuratedRemoteKeys(): Set<string> {
  const keys = new Set<string>();
  for (const skill of CURATED_SKILLS) {
    if (!skill.sourceUrl) continue;
    keys.add(skill.id.toLowerCase());
    keys.add(skill.name.trim().toLowerCase());
    const tail = sourceUrlTail(skill.sourceUrl);
    if (tail) keys.add(tail);
  }
  return keys;
}

function isValidMarketResult(result: MarketResult): boolean {
  const slug = (result.slug ?? "").trim();
  const name = (result.name ?? "").trim();
  return Boolean(slug || name);
}

function isDuplicateCuratedRemote(
  result: MarketResult,
  remoteKeys: Set<string>,
): boolean {
  const slug = (result.slug ?? "").trim().toLowerCase();
  const name = (result.name ?? "").trim().toLowerCase();
  const tail = sourceUrlTail(result.source_url ?? "");
  return (
    (slug.length > 0 && remoteKeys.has(slug)) ||
    (name.length > 0 && remoteKeys.has(name)) ||
    (tail.length > 0 && remoteKeys.has(tail))
  );
}

function formatProviderLabel(source: string): string {
  const normalized = source.toLowerCase();
  if (normalized === "builtin" || normalized === "agentdesk") return "AgentDesk";
  if (normalized.includes("claw")) return "ClawHub";
  if (normalized.includes("model")) return "ModelScope";
  if (normalized.includes("aliyun") || normalized.includes("ali")) return "阿里云";
  if (normalized.includes("skillsmp")) return "SkillsMP";
  return source;
}

function resolveMarketInstalled(
  result: MarketResult,
  installedIds: Set<string>,
  installedByName: Map<string, SkillItem>,
): boolean {
  const key = marketResultKey(result);
  if (installedIds.has(key)) return true;
  if (result.slug && installedByName.has(result.slug)) return true;
  return false;
}

export default function SkillsPage() {
  const navigate = useNavigate();
  const resetForNewChat = useComposerStore((s) => s.resetForNewChat);
  const prependTask = useAppStore((s) => s.prependTask);
  const setActiveTaskId = useAppStore((s) => s.setActiveTaskId);

  const loader = useCallback(() => skillsApi.listSkills(), []);
  const { data: installedList, loading, error, reload } = useAsyncList<SkillItem>(loader);
  const skillsRevision = useSkillsStore((s) => s.revision);

  useEffect(() => {
    if (skillsRevision > 0) {
      void reload();
    }
  }, [skillsRevision, reload]);

  const [mainTab, setMainTab] = useState<MainTab>("market");
  const [category, setCategory] = useState<HubCategory>("全部");
  const [search, setSearch] = useState("");
  const [installingId, setInstallingId] = useState<string | null>(null);
  const [installedIds, setInstalledIds] = useState<Set<string>>(new Set());
  const [installedNameByKey, setInstalledNameByKey] = useState<Map<string, string>>(
    new Map(),
  );
  const [hubLoading, setHubLoading] = useState(false);
  const [hubResults, setHubResults] = useState<MarketResult[]>([]);
  const [hubError, setHubError] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [detailSkill, setDetailSkill] = useState<SkillItem | null>(null);

  const poolNames = useMemo(
    () => new Set(installedList.map((s) => s.name)),
    [installedList],
  );

  const installedByName = useMemo(() => {
    const map = new Map<string, SkillItem>();
    for (const skill of installedList) {
      if (skill.installed) map.set(skill.name, skill);
    }
    return map;
  }, [installedList]);

  const installedCount = useMemo(
    () => installedList.filter((s) => s.installed).length,
    [installedList],
  );

  const curatedVisible = useMemo(() => {
    const bySearch = filterCuratedSkills({ query: search });
    if (category === "全部") return bySearch;
    return bySearch.filter(
      (skill) =>
        classifyHubSkill({
          name: skill.name,
          description: skill.description,
          slug: skill.poolName,
        }) === category,
    );
  }, [category, search]);

  const curatedRemoteKeys = useMemo(() => buildCuratedRemoteKeys(), []);

  const hubVisible = useMemo(
    () =>
      filterHubResults(hubResults, category).filter((result) => {
        if (!isValidMarketResult(result)) return false;
        if (isDuplicateCuratedRemote(result, curatedRemoteKeys)) return false;
        return matchesSkillSearchQuery(search, {
          name: result.name,
          description: result.description,
          slug: result.slug,
        });
      }),
    [hubResults, category, curatedRemoteKeys, search],
  );

  const installedSkills = useMemo(
    () =>
      installedList
        .filter((s) => s.installed)
        .filter((s) =>
          matchesSkillSearchQuery(search, {
            name: s.name,
            description: s.description,
          }),
        ),
    [installedList, search],
  );

  const resolveInstalled = useCallback(
    (id: string, names: string[]): boolean => {
      if (installedIds.has(id)) return true;
      return names.some((name) => name && installedByName.has(name));
    },
    [installedByName, installedIds],
  );

  const resolveChatName = useCallback(
    (candidates: string[], options?: { sourceUrl?: string; id?: string }) => {
      const mapped = options?.id ? installedNameByKey.get(options.id) : undefined;
      const resolved = resolveInstalledSkillChatName({
        installedSkills: installedList,
        installedNameHint: mapped ?? candidates.find(Boolean),
        sourceUrl: options?.sourceUrl,
        displayName: candidates.find(Boolean),
      });
      if (resolved) return resolved;
      for (const name of candidates) {
        if (name && installedByName.has(name)) return name;
      }
      return candidates.find(Boolean) ?? "";
    },
    [installedByName, installedList, installedNameByKey],
  );

  const handleInstallCurated = async (skill: CuratedSkill) => {
    const key = skill.id;
    setInstallingId(key);
    try {
      const name = await skillsApi.installAndMount({
        poolName: skill.poolName,
        sourceUrl: skill.sourceUrl,
        knownPoolNames: poolNames,
      });
      setInstalledIds((prev) => new Set([...prev, skill.id, name]));
      setInstalledNameByKey((prev) => new Map(prev).set(skill.id, name));
      message.success(`已安装「${name}」`);
      await reload();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setInstallingId(null);
    }
  };

  const handleInstallMarket = async (result: MarketResult) => {
    const key = marketResultKey(result);
    setInstallingId(key);
    try {
      const targetName = isGenericHubSkillName(result.name) ? undefined : result.name;
      const name = await skillsApi.installAndMount({
        sourceUrl: result.source_url,
        targetName,
        knownPoolNames: poolNames,
      });
      setInstalledIds((prev) => new Set([...prev, key, name]));
      setInstalledNameByKey((prev) => new Map(prev).set(key, name));
      message.success(`已安装「${resolveMarketDisplayName(result)}」`);
      await reload();
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setInstallingId(null);
    }
  };

  const handleChat = async (skillName: string, displayName?: string) => {
    try {
      await openChatWithSkill({
        skillName,
        displayName,
        resetForNewChat,
        prependTask,
        setActiveTaskId,
        navigate,
      });
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    }
  };

  const handleAddSkill = async (action: "find" | "upload" | "create") => {
    if (action === "upload") {
      setUploadOpen(true);
      return;
    }
    try {
      await openSkillTaskFlow({
        kind: action === "create" ? "create" : "find",
        resetForNewChat,
        prependTask,
        setActiveTaskId,
        navigate,
      });
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    }
  };

  const searchHub = useCallback(async (query: string) => {
    setHubLoading(true);
    setHubError(null);
    try {
      const providers = await marketApi.listProviders();
      const enabled = providers.filter((p) => p.available);
      if (enabled.length === 0) {
        setHubResults([]);
        setHubError("云端技能源暂不可用，请稍后重试。");
        return;
      }
      const provider_pages = Object.fromEntries(
        enabled.map((p) => [p.key, 1]),
      );
      const resp = await marketApi.search({
        query: query.trim() || HUB_BROWSE_QUERY,
        provider_pages,
        limit: HUB_FETCH_LIMIT,
        lang: "zh",
      });
      setHubResults(resp.results);
      if (resp.errors.length && resp.results.length === 0) {
        setHubError(resp.errors.map((e) => e.message).join("；"));
      }
    } catch (err) {
      setHubResults([]);
      setHubError(err instanceof Error ? err.message : String(err));
    } finally {
      setHubLoading(false);
    }
  }, []);

  useEffect(() => {
    if (mainTab !== "market") return;
    const handle = setTimeout(() => {
      void searchHub(search);
    }, 350);
    return () => clearTimeout(handle);
  }, [mainTab, search, searchHub]);

  const categoryChips = (
    <div className="scrollbar-hide mb-5 flex gap-2 overflow-x-auto pb-1">
      {HUB_CATEGORIES.map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => setCategory(item)}
          className={`shrink-0 rounded-full px-3 py-1.5 text-[13px] transition-colors ${
            category === item
              ? "wm-chip-active"
              : "border border-gray-200 bg-white text-gray-600 hover:bg-gray-50"
          }`}
        >
          {item}
        </button>
      ))}
    </div>
  );

  return (
    <>
      <PageHeader
        title="技能市场"
        subtitle="浏览云端技能库，安装后在对话中挂载使用"
        actions={
          <>
            <label className="flex h-9 w-full max-w-[240px] items-center rounded-lg border border-gray-200/80 bg-white px-3 shadow-sm sm:w-[240px]">
              <SearchOutlined className="text-gray-400" />
              <Input
                bordered={false}
                placeholder="搜索技能"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="text-sm"
              />
            </label>
            <Dropdown
              menu={{
                items: [
                  { key: "find", label: "查找技能" },
                  { key: "upload", label: "上传技能" },
                  { key: "create", label: "创建技能" },
                ],
                onClick: ({ key }) => {
                  void handleAddSkill(key as "find" | "upload" | "create");
                },
              }}
              trigger={["click"]}
              placement="bottomRight"
            >
              <button
                type="button"
                className="inline-flex h-9 items-center gap-1.5 rounded-lg wm-btn-primary px-4 text-sm"
              >
                <PlusOutlined />
                添加技能
                <DownOutlined className="text-[10px] opacity-80" />
              </button>
            </Dropdown>
          </>
        }
      />

      {error ? <PageError message={error} /> : null}

      <div className="mb-5 flex items-center gap-6 border-b border-gray-100 text-sm">
        <button
          type="button"
          onClick={() => setMainTab("market")}
          className={`pb-2 transition-colors ${
            mainTab === "market"
              ? "border-b-2 border-emerald-600 font-medium text-gray-900"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          技能市场
        </button>
        <button
          type="button"
          onClick={() => setMainTab("installed")}
          className={`inline-flex items-center gap-2 pb-2 transition-colors ${
            mainTab === "installed"
              ? "border-b-2 border-emerald-600 font-medium text-gray-900"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          已安装
          <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
            {installedCount}
          </span>
        </button>
      </div>

      {mainTab === "market" ? (
        <>
          {categoryChips}

          {hubError ? (
            <p className="mb-4 text-[13px] text-amber-700">{hubError}</p>
          ) : null}

          <div className="grid grid-cols-1 gap-3 pb-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {curatedVisible.map((skill) => {
              const installed = resolveInstalled(skill.id, [
                skill.poolName ?? "",
                skill.name,
              ]);
              const chatName = resolveChatName([skill.poolName ?? "", skill.name], {
                id: skill.id,
                sourceUrl: skill.sourceUrl,
              });
              return (
                <SkillMarketCard
                  key={skill.id}
                  iconKey={skill.icon}
                  iconTone={skill.iconTone}
                  name={skill.name}
                  description={skill.description}
                  provider={
                    skill.provider ? formatProviderLabel(skill.provider) : undefined
                  }
                  installed={installed}
                  installing={installingId === skill.id}
                  onInstall={() => void handleInstallCurated(skill)}
                  onChat={() => void handleChat(chatName, skill.name)}
                />
              );
            })}

            {hubVisible.map((result) => {
              const key = marketResultKey(result);
              const displayName = resolveMarketDisplayName(result);
              const installed = resolveMarketInstalled(
                result,
                installedIds,
                installedByName,
              );
              const chatName = resolveMarketSkillChatName(
                result,
                installedList,
                installedNameByKey.get(marketResultKey(result)),
              );
              return (
                <SkillMarketCard
                  key={key}
                  iconKey={resolveMarketSourceIconKey(result.source, Boolean(result.icon_url))}
                  iconTone={marketTone(result)}
                  name={displayName}
                  description={result.description ?? ""}
                  provider={formatProviderLabel(result.source)}
                  installed={installed}
                  installing={installingId === key}
                  onInstall={() => void handleInstallMarket(result)}
                  onChat={() => void handleChat(chatName, displayName)}
                />
              );
            })}

            {hubLoading ? (
              <p className="col-span-full text-[13px] text-gray-400">
                正在搜索云端技能库…
              </p>
            ) : null}

            {!loading &&
            !hubLoading &&
            curatedVisible.length === 0 &&
            hubVisible.length === 0 ? (
              <p className="col-span-full text-[13px] text-gray-400">
                没有匹配的技能，试试其他分类或关键词。
              </p>
            ) : null}
          </div>
        </>
      ) : (
        <div className="grid grid-cols-1 gap-3 pb-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {installedSkills.map((skill) => (
            <SkillMarketCard
              key={skill.name}
              name={skill.name}
              description={skill.description}
              iconKey={skill.icon}
              installed
              onClick={() => setDetailSkill(skill)}
              onChat={() => void handleChat(skill.name)}
            />
          ))}
          {!loading && installedCount === 0 ? (
            <p className="col-span-full text-[13px] text-gray-400">
              暂无已安装技能。在「技能市场」点击 + 安装后即可在此管理。
            </p>
          ) : !loading && installedSkills.length === 0 ? (
            <p className="col-span-full text-[13px] text-gray-400">
              没有匹配的技能，试试其他关键词。
            </p>
          ) : null}
        </div>
      )}
      <UploadSkillModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onUploaded={(result) => {
          useSkillsStore.getState().bumpSkillsRevision();
          void reload();
          if (
            result.skills.some((skill) => skill.installed) ||
            (result.recovered?.length ?? 0) > 0
          ) {
            setMainTab("installed");
          }
        }}
      />
      <SkillDetailDrawer
        open={detailSkill !== null}
        skill={detailSkill}
        onClose={() => setDetailSkill(null)}
      />
    </>
  );
}
