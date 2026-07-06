import { request } from "./request";

export interface PlazaCard {
  name: string;
  tags: string[];
  desc: string;
  author?: string;
  usage?: string;
  avatar?: string;
  skills?: string[];
  mcp?: string[];
  tools?: string[];
  joined?: boolean;
}

export interface Employee {
  name: string;
  id?: string;
  agent_id?: string;
  joined?: boolean;
  avatar?: string;
  desc: string;
  tools: string[];
  skills: string[];
  requested_skills?: string[];
  mounted_skills?: string[];
  failed_skills?: string[];
  mcp: string[];
  workspace_dir?: string;
  enabled?: boolean;
}

export const plazaApi = {
  listPlaza: () => request<PlazaCard[]>("/plaza"),

  createPlazaCard: (body: Partial<PlazaCard> & { name: string }) =>
    request<PlazaCard>("/plaza", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  joinPlaza: (name: string) =>
    request<Employee>(`/plaza/${encodeURIComponent(name)}/join`, {
      method: "POST",
    }),

  updatePlaza: (name: string, body: Partial<PlazaCard>) =>
    request<PlazaCard>(`/plaza/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  deletePlazaCard: (name: string) =>
    request<{ deleted: boolean; name: string }>(
      `/plaza/${encodeURIComponent(name)}`,
      { method: "DELETE" },
    ),

  listEmployees: () => request<Employee[]>("/employees"),

  createEmployee: (body: Partial<Employee> & { name: string }) =>
    request<Employee>("/employees", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateEmployee: (name: string, body: Partial<Employee>) =>
    request<Employee>(`/employees/${encodeURIComponent(name)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  deleteEmployee: (name: string) =>
    request<{ deleted: boolean; name: string }>(
      `/employees/${encodeURIComponent(name)}`,
      { method: "DELETE" },
    ),
};

export default plazaApi;
