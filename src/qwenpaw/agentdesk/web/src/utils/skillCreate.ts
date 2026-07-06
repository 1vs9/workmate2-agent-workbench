/** Detect skill find-and-install requests (Skills page「查找技能」draft). */
export function isSkillFindMessage(text: string): boolean {
  const t = String(text || "").trim();
  if (!t) return false;
  if (/请帮我查找/i.test(t)) return true;
  return /(查找|搜索|寻找|找).{0,80}(安装|下载).{0,40}(skill|技能)/i.test(t);
}

export const SKILL_CREATOR_SKILL = "make-skill";

/** Summary / edit turns that mention skills but are not create requests. */
function isSkillCreateMetaMessage(text: string): boolean {
  const firstLine = text.split(/\n/)[0]?.trim() ?? text;
  if (
    /^(把|将)?(上述|以上|这些|上面|这个)/.test(firstLine) &&
    /总结|概括|汇总|整理|归纳|描述|说明/.test(firstLine)
  ) {
    return true;
  }
  if (/^(总结|概括|汇总|整理|归纳|描述|说明)/.test(firstLine)) {
    return true;
  }
  return /总结|概括|汇总|整理|归纳|描述成|说明成|改成|修改|优化|润色/.test(
    text.slice(0, 60),
  );
}

/**
 * Detect one-sentence skill creation requests.
 * Requires explicit create intent on the first line (or short message), not
 * incidental "创建 skill" mentions inside pasted feature lists.
 */
export function isSkillCreateMessage(text: string): boolean {
  const t = String(text || "").trim();
  if (!t || isSkillFindMessage(t) || isSkillCreateMetaMessage(t)) return false;

  if (/请帮我创建一个可以实现「/.test(t) && /」的\s*skill/i.test(t)) {
    return true;
  }

  const probe = t.length <= 120 ? t : (t.split(/\n/)[0]?.trim() ?? t);
  if (/请(帮我|为我)?(创建|新建|写一个|做一个|生成).{0,60}(skill|技能)/i.test(probe)) {
    return true;
  }
  if (/\/make-skill\b/i.test(probe)) return true;
  if (/^create\s+(a\s+)?skill\b/i.test(probe)) return true;

  return false;
}

export const SKILL_FIND_DRAFT = "请帮我查找并自动安装能「……」的skill";
export const SKILL_CREATE_DRAFT = "请帮我创建一个可以实现「……」的skill";
export const SKILL_DRAFT_MARKER = "……";
