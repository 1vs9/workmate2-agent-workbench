import { plazaApi } from "../api/plaza";

/** Persist employee skills to store and mount on the agent workspace. */
export async function syncEmployeeSkills(
  employeeName: string,
  skillNames: string[],
  options?: { desc?: string; tags?: string[] },
): Promise<{ mounted: string[]; failed: string[] }> {
  const name = employeeName.trim();
  const skills = [...new Set(skillNames.map((s) => s.trim()).filter(Boolean))];

  const body: Record<string, unknown> = { skills };
  if (options?.desc !== undefined) body.desc = options.desc;
  if (options?.tags !== undefined) body.tags = options.tags;

  const updated = await plazaApi.updateEmployee(name, body);
  const mounted = (updated.mounted_skills ?? skills).filter(Boolean);
  const failed = (updated.failed_skills ?? []).filter(Boolean);
  if (failed.length > 0 && mounted.length === 0) {
    throw new Error(
      `技能未能挂载：${failed.join("、")}。请确认技能已在技能池中安装，或使用正式名称（例如 excel → xlsx）。`,
    );
  }
  return { mounted, failed };
}
