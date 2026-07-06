import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

export interface ArtifactContextMenuProps {
  open: boolean;
  x: number;
  y: number;
  onClose: () => void;
  onOpenFolder: () => void;
  onShareFile: () => void;
  onAddToComposer: () => void;
}

export default function ArtifactContextMenu({
  open,
  x,
  y,
  onClose,
  onOpenFolder,
  onShareFile,
  onAddToComposer,
}: ArtifactContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handlePointer = (event: MouseEvent) => {
      if (menuRef.current?.contains(event.target as Node)) return;
      onClose();
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", handlePointer);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handlePointer);
      document.removeEventListener("keydown", handleKey);
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open || !menuRef.current) return;
    const rect = menuRef.current.getBoundingClientRect();
    const el = menuRef.current;
    if (rect.right > window.innerWidth) {
      el.style.left = `${Math.max(8, window.innerWidth - rect.width - 8)}px`;
    }
    if (rect.bottom > window.innerHeight) {
      el.style.top = `${Math.max(8, window.innerHeight - rect.height - 8)}px`;
    }
  }, [open, x, y]);

  if (!open) return null;

  return createPortal(
    <div
      ref={menuRef}
      className="wm-artifact-context-menu"
      style={{ left: x, top: y }}
      role="menu"
    >
      <button type="button" role="menuitem" onClick={onOpenFolder}>
        打开文件夹
      </button>
      <button type="button" role="menuitem" onClick={onShareFile}>
        分享文件
      </button>
      <button type="button" role="menuitem" onClick={onAddToComposer}>
        添加到对话框
      </button>
    </div>,
    document.body,
  );
}
