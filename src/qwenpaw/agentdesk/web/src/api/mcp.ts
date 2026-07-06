import { request } from "./request";

export interface McpClient {
  key: string;
  name: string;
  description: string;
  enabled: boolean;
  transport: string;
  url: string;
  command: string;
  args: string[];
}

export interface McpPreset {
  id: string;
  name: string;
  description: string;
  requiresApiKey: string | null;
  installed: boolean;
}

export interface McpUpsertBody {
  name: string;
  description?: string;
  enabled?: boolean;
  transport?: string;
  url?: string;
  command?: string;
  args?: string[];
}

export const mcpApi = {
  listMcp: () => request<McpClient[]>("/mcp"),

  listPresets: () => request<McpPreset[]>("/mcp/presets"),

  installPreset: (presetId: string) =>
    request<McpClient>(`/mcp/presets/${encodeURIComponent(presetId)}/install`, {
      method: "POST",
    }),

  upsertMcp: (body: McpUpsertBody) =>
    request<McpClient>("/mcp", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  deleteMcp: (name: string) =>
    request<{ deleted: boolean; name: string }>(
      `/mcp/${encodeURIComponent(name)}`,
      { method: "DELETE" },
    ),
};

export default mcpApi;
