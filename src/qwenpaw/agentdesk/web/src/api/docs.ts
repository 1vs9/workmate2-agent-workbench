import { request } from "./request";

/** A document in the case library (案例库) or knowledge library (资料库). */
export interface Doc {
  id: string;
  title: string;
  content: string;
  tags: string[];
  author?: string;
  created_at?: number;
  updated_at?: number;
}

export interface DocInput {
  title: string;
  content: string;
  tags?: string[];
  author?: string;
}

export type DocKind = "cases" | "knowledge";

/** Both case and knowledge libraries share an identical doc CRUD contract. */
export function createDocsApi(kind: DocKind) {
  const base = `/${kind}`;
  return {
    list: () => request<Doc[]>(base),

    create: (body: DocInput) =>
      request<Doc>(base, { method: "POST", body: JSON.stringify(body) }),

    update: (id: string, body: Partial<DocInput>) =>
      request<Doc>(`${base}/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify(body),
      }),

    remove: (id: string) =>
      request<{ deleted: boolean; id: string }>(
        `${base}/${encodeURIComponent(id)}`,
        { method: "DELETE" },
      ),
  };
}

export const casesApi = createDocsApi("cases");
export const knowledgeApi = createDocsApi("knowledge");
