import { plazaApi } from "../api/plaza";
import { avatarsApi } from "../api/avatars";
import {
  buildEmployeeDesc,
  deriveEmployeeTags,
  suggestEmployeeSkills,
  type EmployeeCreateFormValues,
} from "./employeeCreate";

export interface EmployeeCreateResult {
  name: string;
  desc: string;
  avatar: string;
  tags: string[];
  mountedSkills: string[];
}

/** 按 employee-creator 工作流：创建岗位卡 → join（由后端完成技能同步）。 */
export async function executeEmployeeCreateWizard(
  values: EmployeeCreateFormValues,
): Promise<EmployeeCreateResult> {
  const name = values.name.trim();
  const desc = buildEmployeeDesc(values);
  const tags = deriveEmployeeTags(values.specialty);
  const selected = (values.skillNames ?? []).filter(Boolean);
  const skillNames =
    selected.length > 0
      ? selected
      : suggestEmployeeSkills(values.specialty, values.background);

  const { url: avatar } = await avatarsApi.generate({
    name,
    description: desc,
    role: "employee",
  });

  await plazaApi.createPlazaCard({ name, desc, avatar, tags, skills: skillNames });
  const joined = await plazaApi.joinPlaza(name);
  const mountedSkills = Array.isArray(joined.mounted_skills)
    ? (joined.mounted_skills ?? []).filter(Boolean)
    : skillNames;

  return { name, desc, avatar, tags, mountedSkills };
}
