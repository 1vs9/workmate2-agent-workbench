import { useCallback, useEffect, useMemo, useState } from "react";
import {
  tasksApi,
  type WorkspaceFilePreview,
} from "../../api/tasks";
import type { ArtifactItem } from "../../utils/artifacts";
import { isExplicitWorkspaceRelPath, normalizeArtifactReadPath } from "../../utils/artifacts";

export type ArtifactPanelTab = "products" | "files" | "changes";

interface ArtifactPanelProps {
  taskId: string;
  open: boolean;
  tab: ArtifactPanelTab;
  selectedPath: string | null;
  productArtifacts: ArtifactItem[];
  onTabChange: (tab: ArtifactPanelTab) => void;
  onSelectPath: (path: string) => void;
  onClose: () => void;
  onFileContextMenu: (path: string, event: React.MouseEvent) => void;
}

const TABS: { id: ArtifactPanelTab; label: string }[] = [
  { id: "products", label: "产物" },
  { id: "files", label: "全部文件" },
  { id: "changes", label: "变更" },
];

export default function ArtifactPanel({
  taskId,
  open,
  tab,
  selectedPath,
  productArtifacts,
  onTabChange,
  onSelectPath,
  onClose,
  onFileContextMenu,
}: ArtifactPanelProps) {
  const [workspaceFiles, setWorkspaceFiles] = useState<string[]>([]);
  const [preview, setPreview] = useState<WorkspaceFilePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadWorkspaceFiles = useCallback(async () => {
    if (!taskId) return;
    try {
      const files = await tasksApi.getWorkspaceFiles(taskId);
      setWorkspaceFiles(files);
    } catch {
      setWorkspaceFiles([]);
    }
  }, [taskId]);

  const loadPreview = useCallback(
    async (path: string) => {
      if (!taskId || !path) return;
      setLoading(true);
      setError(null);
      try {
        const data = await tasksApi.getWorkspaceFile(taskId, path);
        setPreview(data);
      } catch (err) {
        setPreview(null);
        const message = err instanceof Error ? err.message : String(err);
        setError(
          message === "Workspace not found"
            ? "未找到任务工作区，请先发送一条消息后再试"
            : message === "File not found"
              ? "文件不存在或尚未写入工作区（可在「全部文件」查看已生成文件）"
              : message,
        );
      } finally {
        setLoading(false);
      }
    },
    [taskId],
  );

  const resolveListedPath = useCallback(
    (path: string) => {
      const normalized = normalizeArtifactReadPath(path);
      if (workspaceFiles.includes(normalized)) return normalized;
      if (isExplicitWorkspaceRelPath(normalized)) return normalized;
      const basename = normalized.split("/").pop()?.toLowerCase() ?? "";
      const matches = workspaceFiles.filter(
        (entry) => entry.split("/").pop()?.toLowerCase() === basename,
      );
      return matches.length === 1 ? matches[0] : normalized;
    },
    [workspaceFiles],
  );

  useEffect(() => {
    if (!open) return;
    void loadWorkspaceFiles();
  }, [open, loadWorkspaceFiles]);

  useEffect(() => {
    if (!open || !selectedPath) {
      setPreview(null);
      return;
    }
    void loadPreview(resolveListedPath(selectedPath));
  }, [open, selectedPath, loadPreview, resolveListedPath, workspaceFiles]);

  const listItems = useMemo(() => {
    if (tab === "products") {
      const paths = productArtifacts.map((item) => resolveListedPath(item.path));
      const extras = workspaceFiles.filter((path) =>
        productArtifacts.some(
          (item) =>
            item.path === path ||
            item.name.toLowerCase() === path.split("/").pop()?.toLowerCase(),
        ),
      );
      return [...new Set([...paths, ...extras])];
    }
    if (tab === "files") return workspaceFiles;
    if (selectedPath) return [resolveListedPath(selectedPath)];
    return workspaceFiles.slice(0, 1);
  }, [tab, productArtifacts, workspaceFiles, selectedPath, resolveListedPath]);

  if (!open) return null;

  const pathLabel = selectedPath
    ? `${selectedPath}${preview?.lines?.length ? ` · ${preview.lines.length} 行` : ""}`
    : "选择左侧文件查看内容";

  return (
    <aside id="artifactPanel" className="wm-artifact-panel">
      <div className="wm-artifact-panel__header">
        <div className="flex gap-1">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`wm-artifact-tab${tab === item.id ? " is-active" : ""}`}
              onClick={() => onTabChange(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="cursor-pointer rounded-lg px-2 py-1 text-[12px] text-gray-500 transition-colors hover:bg-gray-100"
          onClick={onClose}
          aria-label="关闭预览"
        >
          关闭
        </button>
      </div>

      <div className="wm-artifact-panel__path">{pathLabel}</div>

      <div className="wm-artifact-panel__body">
        <div className="wm-artifact-panel__list">
          {listItems.length ? (
            listItems.map((path) => (
              <button
                key={path}
                type="button"
                className={`wm-artifact-file-item${
                  selectedPath === path ? " is-selected" : ""
                }`}
                onClick={() => onSelectPath(path)}
                onContextMenu={(event) => onFileContextMenu(path, event)}
                title={path}
              >
                {path.split("/").pop() || path}
              </button>
            ))
          ) : (
            <div className="p-3 text-[12px] text-gray-400">
              {tab === "products" ? "暂无产物文件" : "工作区暂无文件"}
            </div>
          )}
        </div>

        <div className="wm-artifact-panel__preview">
          {loading ? (
            <div className="text-[12px] text-gray-400">加载中…</div>
          ) : error ? (
            <div className="text-[12px] text-red-600">{error}</div>
          ) : preview?.binary ? (
            <div className="text-[12px] text-gray-500">二进制文件，暂不支持预览</div>
          ) : preview?.content ? (
            <pre className="wm-artifact-preview">{preview.content}</pre>
          ) : (
            <div className="text-[12px] text-gray-400">
              点击消息中的文件或左侧列表查看内容
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
