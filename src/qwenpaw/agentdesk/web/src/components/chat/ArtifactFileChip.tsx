import type { ArtifactItem } from "../../utils/artifacts";

interface ArtifactFileChipProps {
  artifact: ArtifactItem;
  onOpen: (artifact: ArtifactItem) => void;
  onContextMenu: (artifact: ArtifactItem, event: React.MouseEvent) => void;
}

export default function ArtifactFileChip({
  artifact,
  onOpen,
  onContextMenu,
}: ArtifactFileChipProps) {
  const roleClass = artifact.role === "product" ? " is-product" : "";
  return (
    <button
      type="button"
      className={`wm-artifact-chip${roleClass}`}
      title={artifact.summary || artifact.path}
      onClick={() => onOpen(artifact)}
      onContextMenu={(event) => onContextMenu(artifact, event)}
    >
      <svg viewBox="0 0 20 20" fill="none" className="h-3.5 w-3.5 shrink-0" aria-hidden="true">
        <path
          d="M6 3h5l3 3v11H6V3Z"
          stroke="currentColor"
          strokeWidth="1.5"
          fill="none"
        />
        <path d="M11 3v4h4" stroke="currentColor" strokeWidth="1.5" fill="none" />
      </svg>
      <span className="truncate">{artifact.name}</span>
    </button>
  );
}
