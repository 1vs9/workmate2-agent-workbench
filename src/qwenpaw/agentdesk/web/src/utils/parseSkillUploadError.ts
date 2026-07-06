import { ApiError } from "../api/request";

export interface SkillUploadConflict {
  reason: string;
  skill_name: string;
  suggested_name?: string;
}

export interface SkillUploadConflictDetail {
  imported?: string[];
  count?: number;
  conflicts?: SkillUploadConflict[];
}

/** Parse structured upload conflict payload from an API error. */
export function parseSkillUploadConflictDetail(
  err: unknown,
): SkillUploadConflictDetail | null {
  if (!(err instanceof ApiError)) return null;
  const structured = err.detail;
  if (structured && typeof structured === "object" && "conflicts" in structured) {
    return structured as SkillUploadConflictDetail;
  }
  try {
    const parsed = JSON.parse(err.message) as { detail?: SkillUploadConflictDetail };
    if (parsed.detail?.conflicts?.length) return parsed.detail;
  } catch {
    /* not JSON */
  }
  return null;
}

/** Human-readable Chinese message for upload conflict errors. */
export function formatSkillUploadConflictMessage(
  detail: SkillUploadConflictDetail,
): string {
  const conflicts = detail.conflicts ?? [];
  if (!conflicts.length) return "技能上传失败：名称冲突";
  if (conflicts.length === 1) {
    const conflict = conflicts[0];
    const name = conflict.skill_name;
    const suggested = conflict.suggested_name;
    let message = `技能「${name}」已存在于技能库中，无需重复上传。`;
    if (suggested && suggested !== name) {
      message += `如需保留两个版本，可改用建议名称「${suggested}」。`;
    }
    return message;
  }
  const names = conflicts.map((item) => item.skill_name).join("、");
  return `以下技能已存在于技能库中：${names}。无需重复上传。`;
}
