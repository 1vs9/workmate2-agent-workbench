import ArtifactFileChip from "./ArtifactFileChip";
import type { ArtifactItem } from "../../utils/artifacts";

interface TurnArtifactsProps {
  products: ArtifactItem[];
  changes: ArtifactItem[];
  onOpen: (artifact: ArtifactItem) => void;
  onContextMenu: (artifact: ArtifactItem, event: React.MouseEvent) => void;
  onViewAll: (tab: "files" | "changes") => void;
}

function ArtifactSection({
  title,
  items,
  viewAllTab,
  onOpen,
  onContextMenu,
  onViewAll,
}: {
  title: string;
  items: ArtifactItem[];
  viewAllTab: "files" | "changes";
  onOpen: (artifact: ArtifactItem) => void;
  onContextMenu: (artifact: ArtifactItem, event: React.MouseEvent) => void;
  onViewAll: (tab: "files" | "changes") => void;
}) {
  if (!items.length) return null;
  return (
    <div className="wm-turn-artifacts">
      <div className="wm-turn-artifacts-title">
        {title}（{items.length}）
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {items.map((artifact) => (
          <ArtifactFileChip
            key={artifact.path}
            artifact={artifact}
            onOpen={onOpen}
            onContextMenu={onContextMenu}
          />
        ))}
      </div>
      <button
        type="button"
        className="wm-artifact-link"
        onClick={() => onViewAll(viewAllTab)}
      >
        {viewAllTab === "files" ? "查看全部制品 →" : "查看文件变更 →"}
      </button>
    </div>
  );
}

export default function TurnArtifacts({
  products,
  changes,
  onOpen,
  onContextMenu,
  onViewAll,
}: TurnArtifactsProps) {
  if (!products.length && !changes.length) return null;
  return (
    <div className="mt-2 space-y-2">
      <ArtifactSection
        title="任务产生制品"
        items={products}
        viewAllTab="files"
        onOpen={onOpen}
        onContextMenu={onContextMenu}
        onViewAll={onViewAll}
      />
      <ArtifactSection
        title="文件变更"
        items={changes}
        viewAllTab="changes"
        onOpen={onOpen}
        onContextMenu={onContextMenu}
        onViewAll={onViewAll}
      />
    </div>
  );
}
