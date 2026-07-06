import { useCallback, useMemo, useRef, useState } from "react";
import { tasksApi, type TaskMessage } from "../api/tasks";
import type { ArtifactPanelTab } from "../components/task/ArtifactPanel";
import type { ArtifactItem } from "../utils/artifacts";
import {
  artifactFromStreamEvent,
  extractFileRefsFromText,
  isExplicitWorkspaceRelPath,
  mergeArtifactLists,
  normalizeArtifactReadPath,
  readArtifactsFromMessage,
  resolveWorkspacePath,
} from "../utils/artifacts";

interface ContextMenuState {
  open: boolean;
  x: number;
  y: number;
  path: string;
}

const EMPTY_MENU: ContextMenuState = {
  open: false,
  x: 0,
  y: 0,
  path: "",
};

export function useArtifactInteractions(taskId: string) {
  const [panelOpen, setPanelOpen] = useState(false);
  const [panelTab, setPanelTab] = useState<ArtifactPanelTab>("changes");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuState>(EMPTY_MENU);
  const liveArtifactsRef = useRef<ArtifactItem[]>([]);
  const [liveArtifacts, setLiveArtifacts] = useState<ArtifactItem[]>([]);
  const workspaceFilesRef = useRef<string[]>([]);

  const refreshWorkspaceFiles = useCallback(async () => {
    if (!taskId) {
      workspaceFilesRef.current = [];
      return [];
    }
    try {
      const files = await tasksApi.getWorkspaceFiles(taskId);
      workspaceFilesRef.current = files;
      return files;
    } catch {
      workspaceFilesRef.current = [];
      return [];
    }
  }, [taskId]);

  const resolvePath = useCallback(
    (nameOrPath: string) => {
      const normalized = normalizeArtifactReadPath(nameOrPath);
      if (isExplicitWorkspaceRelPath(normalized)) {
        return normalized;
      }
      return resolveWorkspacePath(nameOrPath, workspaceFilesRef.current);
    },
    [],
  );

  const openPanel = useCallback(
    async (options: { path?: string; tab?: ArtifactPanelTab } = {}) => {
      setPanelOpen(true);
      if (options.tab) setPanelTab(options.tab);
      if (options.path) {
        const resolved = resolvePath(options.path);
        setSelectedPath(resolved);
        setPanelTab(options.tab ?? "products");
      }
      void refreshWorkspaceFiles();
    },
    [refreshWorkspaceFiles, resolvePath],
  );

  const closePanel = useCallback(() => {
    setPanelOpen(false);
  }, []);

  const openArtifact = useCallback(
    async (artifact: ArtifactItem) => {
      await openPanel({
        path: artifact.path,
        tab: artifact.role === "product" ? "products" : "changes",
      });
    },
    [openPanel],
  );

  const openFileRef = useCallback(
    async (nameOrPath: string) => {
      await openPanel({
        path: nameOrPath,
        tab: "changes",
      });
    },
    [openPanel],
  );

  const showContextMenu = useCallback((path: string, event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    setContextMenu({
      open: true,
      x: event.clientX,
      y: event.clientY,
      path,
    });
  }, []);

  const closeContextMenu = useCallback(() => {
    setContextMenu(EMPTY_MENU);
  }, []);

  const pushLiveArtifact = useCallback((evt: Record<string, unknown>) => {
    const artifact = artifactFromStreamEvent(evt);
    if (!artifact) return;
    liveArtifactsRef.current = mergeArtifactLists(liveArtifactsRef.current, [artifact]);
    setLiveArtifacts([...liveArtifactsRef.current]);
  }, []);

  const resetLiveArtifacts = useCallback(() => {
    liveArtifactsRef.current = [];
    setLiveArtifacts([]);
  }, []);

  const takeLiveArtifacts = useCallback(() => {
    const items = [...liveArtifactsRef.current];
    liveArtifactsRef.current = [];
    return items;
  }, []);

  const buildTurnArtifacts = useCallback(
    (message: Record<string, unknown>, text: string) => {
      const formal = readArtifactsFromMessage(message);
      const existing = new Set(formal.map((item) => item.path.toLowerCase()));
      const inferred = extractFileRefsFromText(text, existing);
      return mergeArtifactLists(formal, inferred);
    },
    [],
  );

  const buildLiveTurnArtifacts = useCallback(
    (text: string) => {
      const formal = liveArtifactsRef.current;
      const existing = new Set(formal.map((item) => item.path.toLowerCase()));
      const inferred = extractFileRefsFromText(text, existing);
      return mergeArtifactLists(formal, inferred);
    },
    [liveArtifacts],
  );

  const attachArtifactsToMessage = useCallback(
    (message: TaskMessage, text: string, extra: ArtifactItem[] = []): TaskMessage => {
      const artifacts = mergeArtifactLists(
        buildTurnArtifacts(message as Record<string, unknown>, text),
        extra,
      );
      if (!artifacts.length) return message;
      return { ...message, artifacts };
    },
    [buildTurnArtifacts],
  );

  const handleOpenFolder = useCallback(async () => {
    const path = contextMenu.path;
    closeContextMenu();
    if (!taskId || !path) return;
    try {
      await refreshWorkspaceFiles();
      await tasksApi.revealWorkspacePath(taskId, resolvePath(path));
    } catch (err) {
      window.alert(err instanceof Error ? err.message : String(err));
    }
  }, [closeContextMenu, contextMenu.path, refreshWorkspaceFiles, resolvePath, taskId]);

  const handleShareFile = useCallback(async () => {
    const path = resolvePath(contextMenu.path);
    closeContextMenu();
    const shareText = path;
    try {
      if (navigator.share) {
        await navigator.share({ title: path.split("/").pop() || path, text: shareText });
        return;
      }
    } catch {
      /* fall through to clipboard */
    }
    try {
      await navigator.clipboard.writeText(shareText);
      window.alert("文件路径已复制，可粘贴分享。");
    } catch {
      window.prompt("复制文件路径以分享：", shareText);
    }
  }, [closeContextMenu, contextMenu.path, resolvePath]);

  const productArtifacts = useMemo(
    () => liveArtifacts.filter((item) => item.role === "product"),
    [liveArtifacts],
  );

  return useMemo(
    () => ({
      panelOpen,
      setPanelOpen,
      panelTab,
      setPanelTab,
      selectedPath,
      setSelectedPath,
      contextMenu,
      productArtifacts,
      openPanel,
      closePanel,
      openArtifact,
      openFileRef,
      showContextMenu,
      closeContextMenu,
      pushLiveArtifact,
      resetLiveArtifacts,
      takeLiveArtifacts,
      buildTurnArtifacts,
      buildLiveTurnArtifacts,
      attachArtifactsToMessage,
      handleOpenFolder,
      handleShareFile,
      refreshWorkspaceFiles,
    }),
    [
      panelOpen,
      panelTab,
      selectedPath,
      contextMenu,
      productArtifacts,
      openPanel,
      closePanel,
      openArtifact,
      openFileRef,
      showContextMenu,
      closeContextMenu,
      pushLiveArtifact,
      resetLiveArtifacts,
      takeLiveArtifacts,
      buildTurnArtifacts,
      buildLiveTurnArtifacts,
      attachArtifactsToMessage,
      handleOpenFolder,
      handleShareFile,
      refreshWorkspaceFiles,
    ],
  );
}
