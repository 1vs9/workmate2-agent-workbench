import type { MarketResult } from "../api/market";
import type { SkillItem } from "../api/skills";

function norm(value: string | undefined | null): string {
  return (value ?? "").trim().toLowerCase();
}

/** Resolve the workspace skill name used by mount/chat APIs. */
export function resolveInstalledSkillChatName(options: {
  installedSkills: SkillItem[];
  installedNameHint?: string;
  slug?: string;
  displayName?: string;
  sourceUrl?: string;
}): string {
  const { installedSkills, installedNameHint, slug, displayName, sourceUrl } =
    options;
  const installed = installedSkills.filter((s) => s.installed);

  const hint = (installedNameHint ?? "").trim();
  if (hint && installed.some((s) => s.name === hint)) {
    return hint;
  }

  const slugNorm = norm(slug);
  if (slugNorm) {
    const exact = installed.find((s) => norm(s.name) === slugNorm);
    if (exact) return exact.name;
    const partial = installed.find((s) => {
      const nameNorm = norm(s.name);
      return nameNorm.includes(slugNorm) || slugNorm.includes(nameNorm);
    });
    if (partial) return partial.name;
  }

  const url = (sourceUrl ?? "").trim();
  if (url) {
    const bySource = installed.find((s) => {
      const src = String(s.source ?? "").trim();
      if (!src) return false;
      return src === url || src.includes(url) || url.includes(src);
    });
    if (bySource) return bySource.name;

    const tail = url.split("/").filter(Boolean).pop();
    const tailNorm = norm(tail);
    if (tailNorm) {
      const byTail = installed.find((s) => {
        const nameNorm = norm(s.name);
        return nameNorm === tailNorm || nameNorm.includes(tailNorm);
      });
      if (byTail) return byTail.name;
    }
  }

  const display = (displayName ?? "").trim();
  if (display) {
    const byDisplay = installed.find((s) => s.name === display);
    if (byDisplay) return byDisplay.name;
  }

  return hint || (slug ?? "").trim() || display;
}

export function resolveMarketSkillChatName(
  result: MarketResult,
  installedSkills: SkillItem[],
  installedNameHint?: string,
): string {
  return resolveInstalledSkillChatName({
    installedSkills,
    installedNameHint,
    slug: result.slug,
    displayName: result.name,
    sourceUrl: result.source_url,
  });
}
