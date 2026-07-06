import { request } from "./request";

export interface SkillItem {
  name: string;
  description: string;
  body: string;
  content?: string;
  source?: string;
  version_text?: string;
  /** Tool-style icon key (metadata.qwenpaw.icon). */
  icon?: string;
  /** @deprecated Legacy emoji metadata — UI derives tool icons from name/icon. */
  emoji?: string;
  installed?: boolean;
  enabled?: boolean;
}

export interface MountResult {
  mounted: boolean;
  skill_name: string;
  agent_id?: string;
  workspace_dir?: string;
  enabled?: boolean;
}

export interface MountBody {
  employee_name?: string;
  agent_id?: string;
  task_id?: string;
  scope?: "agent" | "task";
  overwrite?: boolean;
}

export interface SkillUploadResult {
  uploaded: number;
  skills: SkillItem[];
  mounted?: boolean;
  recovered?: string[];
}

export interface HubImportResult {
  installed: boolean;
  name: string;
  enabled: boolean;
  source_url: string;
}

export interface BuiltinImportResult {
  imported?: string[];
  updated?: string[];
  unchanged?: string[];
  skipped?: string[];
  conflicts?: unknown[];
}

export interface SkillFileEntry {
  name: string;
  path: string;
  type: "file" | "directory";
  children?: SkillFileEntry[];
}

export interface SkillFileTree {
  skill_name: string;
  location: "workspace" | "pool" | string;
  entries: SkillFileEntry[];
}

export interface SkillFileContent {
  skill_name: string;
  location: "workspace" | "pool" | string;
  path: string;
  content: string;
  size: number;
  is_markdown: boolean;
}

export const skillsApi = {
  listSkills: () => request<SkillItem[]>("/skills"),

  importFromHub: (body: {
    bundle_url: string;
    version?: string;
    target_name?: string;
  }) =>
    request<HubImportResult>("/skills/pool/import", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  importBuiltin: (skillNames: string[]) =>
    request<BuiltinImportResult>("/skills/pool/import-builtin", {
      method: "POST",
      body: JSON.stringify({ skill_names: skillNames }),
    }),

  /** Install to workspace pool then mount — returns the mounted skill name. */
  async installAndMount(options: {
    poolName?: string;
    sourceUrl?: string;
    targetName?: string;
    knownPoolNames?: Set<string>;
  }): Promise<string> {
    let skillName = options.targetName || options.poolName || "";

    if (options.sourceUrl) {
      const target = options.targetName?.trim();
      const genericTarget =
        !target || target.toLowerCase() === "skill" || target.toLowerCase() === "skills";
      const imported = await skillsApi.importFromHub({
        bundle_url: options.sourceUrl,
        target_name: genericTarget ? undefined : target,
      });
      skillName = imported.name;
    } else if (options.poolName) {
      skillName = options.poolName;
      const inPool = options.knownPoolNames?.has(skillName);
      if (!inPool) {
        try {
          const result = await skillsApi.importBuiltin([skillName]);
          const resolved =
            result.imported?.[0] ?? result.updated?.[0] ?? result.unchanged?.[0];
          if (resolved) skillName = resolved;
        } catch {
          /* may already exist in pool */
        }
      }
    }

    if (!skillName) {
      throw new Error("无法确定技能名称");
    }

    await skillsApi.mountSkill(skillName, { scope: "agent" });
    return skillName;
  },

  createSkill: (body: { name: string; description: string; body: string }) =>
    request<SkillItem>("/skills", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  uploadSkill: (
    fileOrFiles: File | File[],
    autoInstallSafe = true,
  ): Promise<SkillUploadResult> => {
    const form = new FormData();
    if (Array.isArray(fileOrFiles)) {
      const relativePaths: string[] = [];
      for (const entry of fileOrFiles) {
        form.append("files", entry);
        relativePaths.push(
          (entry as File & { webkitRelativePath?: string }).webkitRelativePath ||
            entry.name ||
            "SKILL.md",
        );
      }
      form.append("relative_paths", JSON.stringify(relativePaths));
    } else {
      form.append("file", fileOrFiles);
    }
    form.append("auto_install_safe", String(autoInstallSafe));
    return request("/skills/upload", { method: "POST", body: form });
  },

  mountSkill: (skillName: string, body: MountBody = {}) =>
    request<MountResult>(`/skills/${encodeURIComponent(skillName)}/mount`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteSkill: (skillName: string) =>
    request<{ deleted: boolean; name: string }>(
      `/skills/${encodeURIComponent(skillName)}`,
      { method: "DELETE" },
    ),

  listSkillFiles: (skillName: string) =>
    request<SkillFileTree>(`/skills/${encodeURIComponent(skillName)}/files`),

  readSkillFile: (skillName: string, filePath: string) =>
    request<SkillFileContent>(
      `/skills/${encodeURIComponent(skillName)}/files/${filePath
        .split("/")
        .map(encodeURIComponent)
        .join("/")}`,
    ),

  listTools: () => request<unknown[]>("/tools"),
};

export default skillsApi;
