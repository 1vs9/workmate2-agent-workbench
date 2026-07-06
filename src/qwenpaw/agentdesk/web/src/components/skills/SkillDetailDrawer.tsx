import { useCallback, useEffect, useMemo, useState } from "react";
import { Drawer, Spin, message } from "antd";
import AssistantMarkdown from "../chat/AssistantMarkdown";
import {
  skillsApi,
  type SkillFileContent,
  type SkillFileEntry,
  type SkillItem,
} from "../../api/skills";
import { SkillFileTreeIcon, SkillIcon } from "../../utils/skillIcon";

interface SkillDetailDrawerProps {
  open: boolean;
  skill: SkillItem | null;
  onClose: () => void;
}

function FileTreeNode({
  entry,
  selectedPath,
  onSelect,
  depth = 0,
}: {
  entry: SkillFileEntry;
  selectedPath: string | null;
  onSelect: (path: string) => void;
  depth?: number;
}) {
  const isSelected = entry.type === "file" && entry.path === selectedPath;
  const isMarkdown = entry.type === "file" && entry.name.toLowerCase().endsWith(".md");

  if (entry.type === "directory") {
    return (
      <div className="select-none">
        <div
          className="truncate py-1 text-[12px] font-medium text-gray-500"
          style={{ paddingLeft: depth * 12 }}
        >
          {entry.name}
        </div>
        {(entry.children ?? []).map((child) => (
          <FileTreeNode
            key={child.path}
            entry={child}
            selectedPath={selectedPath}
            onSelect={onSelect}
            depth={depth + 1}
          />
        ))}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onSelect(entry.path)}
      className={`block w-full truncate rounded-md px-2 py-1.5 text-left text-[13px] transition-colors ${
        isSelected
          ? "bg-emerald-50 font-medium text-emerald-800"
          : "text-gray-700 hover:bg-gray-50"
      }`}
      style={{ paddingLeft: 8 + depth * 12 }}
      title={entry.path}
    >
      {isMarkdown ? <SkillFileTreeIcon isMarkdown /> : <SkillFileTreeIcon isMarkdown={false} />}
      {entry.name}
    </button>
  );
}

function findFirstMarkdown(entries: SkillFileEntry[]): string | null {
  for (const entry of entries) {
    if (entry.type === "file" && entry.name.toLowerCase().endsWith(".md")) {
      return entry.path;
    }
    if (entry.type === "directory") {
      const nested = findFirstMarkdown(entry.children ?? []);
      if (nested) return nested;
    }
  }
  return null;
}

function locationLabel(location: string | undefined): string {
  if (location === "workspace") return "工作区";
  if (location === "pool") return "技能库";
  return location ?? "—";
}

export default function SkillDetailDrawer({
  open,
  skill,
  onClose,
}: SkillDetailDrawerProps) {
  const [treeLoading, setTreeLoading] = useState(false);
  const [contentLoading, setContentLoading] = useState(false);
  const [entries, setEntries] = useState<SkillFileEntry[]>([]);
  const [location, setLocation] = useState<string>("");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<SkillFileContent | null>(null);

  const loadFile = useCallback(async (skillName: string, path: string) => {
    setContentLoading(true);
    try {
      const content = await skillsApi.readSkillFile(skillName, path);
      setFileContent(content);
      setSelectedPath(path);
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setContentLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open || !skill) {
      setEntries([]);
      setLocation("");
      setSelectedPath(null);
      setFileContent(null);
      return;
    }

    let cancelled = false;
    setTreeLoading(true);
    setEntries([]);
    setLocation("");
    setSelectedPath(null);
    setFileContent(null);

    void (async () => {
      try {
        const tree = await skillsApi.listSkillFiles(skill.name);
        if (cancelled) return;
        setEntries(tree.entries);
        setLocation(tree.location);
        const defaultPath = findFirstMarkdown(tree.entries);
        if (defaultPath) {
          await loadFile(skill.name, defaultPath);
        }
      } catch (err) {
        if (!cancelled) {
          message.error(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) setTreeLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [open, skill, loadFile]);

  const preview = useMemo(() => {
    if (!fileContent) {
      return (
        <p className="text-[13px] text-gray-400">
          选择左侧文件查看内容
        </p>
      );
    }
    if (fileContent.is_markdown) {
      return <AssistantMarkdown content={fileContent.content} />;
    }
    return (
      <pre className="overflow-x-auto rounded-lg bg-gray-50 p-4 text-[12px] leading-relaxed text-gray-800">
        {fileContent.content}
      </pre>
    );
  }, [fileContent]);

  return (
    <Drawer
      title={skill?.name ?? "技能详情"}
      placement="right"
      width={Math.min(920, typeof window !== "undefined" ? window.innerWidth - 24 : 920)}
      open={open}
      onClose={onClose}
      destroyOnClose
    >
      {skill ? (
        <div className="flex h-full min-h-0 flex-col gap-4">
          <div className="rounded-lg border border-gray-100 bg-gray-50/80 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700">
                <SkillIcon
                  name={skill.name}
                  icon={skill.icon}
                  description={skill.description}
                />
              </span>
              <h3 className="text-[15px] font-semibold text-gray-900">{skill.name}</h3>
              {skill.source ? (
                <span className="rounded border border-gray-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-gray-500">
                  {skill.source}
                </span>
              ) : null}
              {location ? (
                <span className="rounded border border-emerald-100 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">
                  {locationLabel(location)}
                </span>
              ) : null}
            </div>
            <p className="mt-2 text-[13px] leading-relaxed text-gray-600">
              {skill.description || "—"}
            </p>
            {skill.version_text ? (
              <p className="mt-1 text-[12px] text-gray-400">版本 {skill.version_text}</p>
            ) : null}
          </div>

          <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 md:grid-cols-[220px_minmax(0,1fr)]">
            <div className="flex min-h-[240px] flex-col rounded-lg border border-gray-100 bg-white p-3">
              <h4 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-gray-400">
                目录结构
              </h4>
              <div className="min-h-0 flex-1 overflow-y-auto">
                {treeLoading ? (
                  <div className="flex justify-center py-8">
                    <Spin size="small" />
                  </div>
                ) : entries.length === 0 ? (
                  <p className="text-[13px] text-gray-400">暂无文件</p>
                ) : (
                  entries.map((entry) => (
                    <FileTreeNode
                      key={entry.path}
                      entry={entry}
                      selectedPath={selectedPath}
                      onSelect={(path) => void loadFile(skill.name, path)}
                    />
                  ))
                )}
              </div>
            </div>

            <div className="flex min-h-[240px] flex-col rounded-lg border border-gray-100 bg-white p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <h4 className="truncate text-[13px] font-medium text-gray-700">
                  {selectedPath ?? "文件预览"}
                </h4>
                {contentLoading ? <Spin size="small" /> : null}
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto">{preview}</div>
            </div>
          </div>
        </div>
      ) : null}
    </Drawer>
  );
}
