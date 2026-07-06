import { useCallback, useEffect, useState } from "react";
import { tasksApi, type WorkspaceNode } from "../../api/tasks";

interface TaskWorkspacePanelProps {
  taskId: string;
  open: boolean;
  onClose: () => void;
}

function TreeNode({
  node,
  depth,
  onReveal,
}: {
  node: WorkspaceNode;
  depth: number;
  onReveal: (path: string) => void;
}) {
  const [expanded, setExpanded] = useState(depth < 2);
  const isDir = node.type === "dir";
  return (
    <div style={{ paddingLeft: depth * 12 }}>
      <button
        type="button"
        onClick={() => {
          if (isDir) setExpanded((v) => !v);
          else void onReveal(node.path);
        }}
        className="block w-full truncate rounded px-1 py-0.5 text-left text-[12px] text-gray-700 hover:bg-gray-100"
        title={node.path}
      >
        {isDir ? (expanded ? "📁 " : "📂 ") : "📄 "}
        {node.name}
      </button>
      {isDir && expanded
        ? (node.children ?? []).map((child) => (
            <TreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              onReveal={onReveal}
            />
          ))
        : null}
    </div>
  );
}

export default function TaskWorkspacePanel({
  taskId,
  open,
  onClose,
}: TaskWorkspacePanelProps) {
  const [tree, setTree] = useState<WorkspaceNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadTree = useCallback(async () => {
    if (!taskId) return;
    setLoading(true);
    setError(null);
    try {
      const nodes = await tasksApi.getWorkspaceTree(taskId);
      setTree(Array.isArray(nodes) ? nodes : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setTree([]);
    } finally {
      setLoading(false);
    }
  }, [taskId]);

  useEffect(() => {
    if (open) void loadTree();
  }, [open, loadTree]);

  const reveal = async (path: string) => {
    try {
      await tasksApi.revealWorkspacePath(taskId, path);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : String(err));
    }
  };

  if (!open) return null;

  return (
    <aside className="flex w-[280px] shrink-0 flex-col border-l border-gray-200/80 bg-white">
      <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2">
        <span className="text-[13px] font-medium text-gray-800">工作空间</span>
        <div className="flex gap-1">
          <button
            type="button"
            onClick={() => void loadTree()}
            className="rounded px-2 py-1 text-[11px] text-gray-500 hover:bg-gray-100"
          >
            刷新
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded px-2 py-1 text-[11px] text-gray-500 hover:bg-gray-100"
          >
            关闭
          </button>
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-2">
        {loading ? (
          <div className="text-[12px] text-gray-400">加载中…</div>
        ) : error ? (
          <div className="text-[12px] text-red-600">{error}</div>
        ) : tree.length === 0 ? (
          <div className="text-[12px] text-gray-400">暂无文件</div>
        ) : (
          tree.map((node) => (
            <TreeNode key={node.path} node={node} depth={0} onReveal={reveal} />
          ))
        )}
      </div>
    </aside>
  );
}
