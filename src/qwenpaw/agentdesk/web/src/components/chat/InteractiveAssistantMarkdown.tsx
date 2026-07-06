import { useCallback, useLayoutEffect, useRef } from "react";
import AssistantMarkdown from "./AssistantMarkdown";
import { looksLikeFileName } from "../../utils/artifacts";

interface InteractiveAssistantMarkdownProps {
  content: string;
  streaming?: boolean;
  onFileRefClick: (fileName: string, event?: React.MouseEvent) => void;
  onFileRefContextMenu: (fileName: string, event: React.MouseEvent) => void;
}

export default function InteractiveAssistantMarkdown({
  content,
  streaming = false,
  onFileRefClick,
  onFileRefContextMenu,
}: InteractiveAssistantMarkdownProps) {
  const rootRef = useRef<HTMLDivElement>(null);

  const enhanceFileRefs = useCallback(() => {
    const root = rootRef.current;
    if (!root) return;
    root.querySelectorAll("code").forEach((node) => {
      if (node.closest("pre")) return;
      if (node.classList.contains("wm-file-ref")) return;
      const text = node.textContent?.trim() ?? "";
      if (!looksLikeFileName(text)) return;
      node.classList.add("wm-file-ref");
      node.setAttribute("data-wm-file-ref", text);
      node.setAttribute("role", "button");
      node.setAttribute("tabindex", "0");
      node.setAttribute("title", `查看 ${text}`);
    });
  }, []);

  useLayoutEffect(() => {
    enhanceFileRefs();
  }, [content, streaming, enhanceFileRefs]);

  const handleClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const target = (event.target as HTMLElement | null)?.closest("[data-wm-file-ref]");
    if (!(target instanceof HTMLElement)) return;
    event.preventDefault();
    event.stopPropagation();
    const fileName = target.getAttribute("data-wm-file-ref");
    if (fileName) onFileRefClick(fileName, event);
  };

  const handleContextMenu = (event: React.MouseEvent<HTMLDivElement>) => {
    const target = (event.target as HTMLElement | null)?.closest("[data-wm-file-ref]");
    if (!(target instanceof HTMLElement)) return;
    event.preventDefault();
    event.stopPropagation();
    const fileName = target.getAttribute("data-wm-file-ref");
    if (fileName) onFileRefContextMenu(fileName, event);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const target = (event.target as HTMLElement | null)?.closest("[data-wm-file-ref]");
    if (!(target instanceof HTMLElement)) return;
    event.preventDefault();
    const fileName = target.getAttribute("data-wm-file-ref");
    if (fileName) {
      onFileRefClick(fileName, event as unknown as React.MouseEvent);
    }
  };

  return (
    <div
      ref={rootRef}
      className="wm-markdown-interactive"
      onClick={handleClick}
      onContextMenu={handleContextMenu}
      onKeyDown={handleKeyDown}
    >
      <AssistantMarkdown content={content} streaming={streaming} />
    </div>
  );
}
