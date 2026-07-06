export type ArtifactRole = "product" | "change";

export interface ArtifactItem {
  kind: "file";
  role: ArtifactRole;
  path: string;
  name: string;
  summary?: string;
  op?: string;
  tool?: string;
}

const PRODUCT_SUFFIXES = new Set([
  ".pptx",
  ".ppt",
  ".docx",
  ".doc",
  ".pdf",
  ".xlsx",
  ".xls",
  ".csv",
  ".zip",
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".svg",
  ".mp4",
  ".mov",
  ".html",
  ".htm",
  ".md",
  ".txt",
  ".json",
  ".yaml",
  ".yml",
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".py",
  ".rs",
  ".go",
]);

const INLINE_FILE_RE =
  /(?:^|[\s`"'（(「【\[])([\w./\\-]+\.(?:md|txt|markdown|json|ya?ml|py|ts|tsx|js|jsx|html?|css|less|csv|xml|pdf|docx?|xlsx?|pptx?|png|jpe?g|gif|webp|svg|zip|rs|go|toml|ini|env|sh|bat|ps1))(?:$|[\s`"'）)」】\].,;:!?])/gi;

export function normalizeArtifactReadPath(path: string): string {
  const raw = String(path || "").replace(/\\/g, "/").trim();
  if (!raw) return raw;
  const lower = raw.toLowerCase();
  if (lower.startsWith("backend/data/skills/")) {
    return `skills/${raw.slice("backend/data/skills/".length)}`;
  }
  const marker = "/data/skills/";
  const idx = lower.indexOf(marker);
  if (idx >= 0) return `skills/${raw.slice(idx + marker.length)}`;
  if (lower.startsWith("data/skills/")) {
    return `skills/${raw.slice("data/skills/".length)}`;
  }
  return raw;
}

export function inferArtifactRole(
  artifact: Partial<ArtifactItem> & { name?: string; path?: string },
): ArtifactRole | null {
  if (artifact.role === "product" || artifact.role === "change") {
    return artifact.role;
  }
  const name = String(artifact.name || artifact.path || "").trim();
  if (name.startsWith("~$")) return null;
  const dot = name.lastIndexOf(".");
  const suffix = dot >= 0 ? name.slice(dot).toLowerCase() : "";
  if (PRODUCT_SUFFIXES.has(suffix)) return "product";
  return "change";
}

export function looksLikeFileName(text: string): boolean {
  const value = String(text || "").trim();
  if (!value || value.includes("\n") || value.length > 260) return false;
  const dot = value.lastIndexOf(".");
  if (dot <= 0) return false;
  const suffix = value.slice(dot).toLowerCase();
  return PRODUCT_SUFFIXES.has(suffix);
}

/** True when a path is already relative to the task workspace root. */
export function isExplicitWorkspaceRelPath(path: string): boolean {
  const normalized = normalizeArtifactReadPath(path);
  if (!normalized || !normalized.includes("/")) return false;
  if (/^[a-zA-Z]:/.test(normalized)) return false;
  if (normalized.startsWith("//") || normalized.startsWith("/")) return false;
  return true;
}

export function normalizeArtifactList(items: unknown[]): ArtifactItem[] {
  const result: ArtifactItem[] = [];
  for (const item of items || []) {
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    const path = normalizeArtifactReadPath(String(record.path || ""));
    const name = String(record.name || path.split("/").pop() || path || "文件");
    const role = inferArtifactRole({ ...record, name, path });
    if (!role) continue;
    result.push({
      kind: "file",
      role,
      path,
      name,
      summary: String(record.summary || name),
      op: record.op ? String(record.op) : undefined,
      tool: record.tool ? String(record.tool) : undefined,
    });
  }
  return result;
}

export function artifactFromStreamEvent(evt: Record<string, unknown>): ArtifactItem | null {
  return normalizeArtifactList([evt])[0] ?? null;
}

export function extractFileRefsFromText(
  text: string,
  existingPaths = new Set<string>(),
): ArtifactItem[] {
  const found = new Map<string, ArtifactItem>();
  const normalizedExisting = new Set(
    [...existingPaths].map((p) => normalizeArtifactReadPath(p).toLowerCase()),
  );

  const register = (raw: string) => {
    const cleaned = raw.replace(/^[`"'([]+|[`"')\],;:!?.]+$/g, "").trim();
    if (!looksLikeFileName(cleaned)) return;
    const path = normalizeArtifactReadPath(cleaned);
    const key = path.toLowerCase();
    if (normalizedExisting.has(key) || found.has(key)) return;
    const role = inferArtifactRole({ name: cleaned, path });
    if (!role) return;
    found.set(key, {
      kind: "file",
      role,
      path,
      name: path.split("/").pop() || path,
      summary: path,
    });
  };

  let match: RegExpExecArray | null;
  INLINE_FILE_RE.lastIndex = 0;
  while ((match = INLINE_FILE_RE.exec(text)) !== null) {
    register(match[1]);
  }

  for (const part of text.match(/`([^`\n]+)`/g) ?? []) {
    register(part.slice(1, -1));
  }

  return [...found.values()];
}

export function mergeArtifactLists(...lists: ArtifactItem[][]): ArtifactItem[] {
  const merged = new Map<string, ArtifactItem>();
  for (const list of lists) {
    for (const item of list) {
      merged.set(item.path.toLowerCase(), item);
    }
  }
  return [...merged.values()];
}

export function resolveWorkspacePath(
  nameOrPath: string,
  workspaceFiles: string[],
): string {
  const normalized = normalizeArtifactReadPath(nameOrPath);
  if (!normalized) return normalized;
  if (workspaceFiles.includes(normalized)) return normalized;
  // Tool-emitted workspace paths (e.g. skills/foo/SKILL.md) open directly.
  if (isExplicitWorkspaceRelPath(normalized)) return normalized;
  const lower = normalized.toLowerCase();
  const basename = normalized.split("/").pop()?.toLowerCase() ?? lower;
  if (basename === "skill.md") {
    const skillMatches = workspaceFiles.filter((p) => {
      const entry = p.toLowerCase();
      return entry === "skill.md" || entry.endsWith("/skill.md");
    });
    const underSkills = skillMatches.filter((p) =>
      p.toLowerCase().startsWith("skills/"),
    );
    if (underSkills.length === 1) return underSkills[0];
    if (underSkills.length > 1) {
      return [...underSkills].sort((a, b) => b.length - a.length)[0];
    }
    if (skillMatches.length === 1) return skillMatches[0];
  }
  const exact = workspaceFiles.find((p) => p.toLowerCase() === lower);
  if (exact) return exact;
  const byName = workspaceFiles.filter(
    (p) => p.split("/").pop()?.toLowerCase() === basename,
  );
  if (byName.length === 1) return byName[0];
  return normalized;
}

export function readArtifactsFromMessage(message: Record<string, unknown>): ArtifactItem[] {
  const raw = message.artifacts;
  if (!Array.isArray(raw)) return [];
  return normalizeArtifactList(raw);
}

export function skillProductArtifact(skillName: string): ArtifactItem {
  const name = String(skillName || "").trim();
  const path = `skills/${name}/SKILL.md`;
  return {
    kind: "file",
    role: "product",
    path,
    name: `${name}/SKILL.md`,
    summary: path,
    op: "write",
    tool: "materialize_skill",
  };
}
