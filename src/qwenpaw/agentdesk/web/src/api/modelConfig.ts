import { request } from "./request";

export interface ProviderModel {
  id: string;
  name: string;
}

export interface Provider {
  id: string;
  name: string;
  base_url: string;
  api_key_prefix: string;
  api_key_configured: boolean;
  require_api_key: boolean;
  freeze_url: boolean;
  is_local: boolean;
  is_custom: boolean;
  models: ProviderModel[];
}

export interface AgentDeskConfig {
  working_dir: string;
  secret_dir: string;
  suggested_working_dir: string;
  suggested_secret_dir: string;
  paths_saved: boolean;
  saved_working_dir: string | null;
  saved_secret_dir: string | null;
  model_ready: boolean;
  active_model: { provider_id: string; model: string } | null;
  active_model_label: string | null;
  providers: Provider[];
}

export const modelConfigApi = {
  getConfig: () => request<AgentDeskConfig>("/config"),

  updateDataDirs: (body: { working_dir: string; secret_dir: string }) =>
    request<{
      working_dir: string;
      secret_dir: string;
      saved_working_dir: string;
      saved_secret_dir: string;
      requires_restart: boolean;
      message: string;
    }>("/config/data-dirs", {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  updateProvider: (
    providerId: string,
    body: { api_key?: string; base_url?: string },
  ) =>
    request<Provider>(`/config/providers/${encodeURIComponent(providerId)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  setActiveModel: (providerId: string, model: string) =>
    request<{
      active_model: { provider_id: string; model: string } | null;
      active_model_label: string | null;
      model_ready: boolean;
    }>("/config/active-model", {
      method: "PUT",
      body: JSON.stringify({ provider_id: providerId, model }),
    }),
};

export default modelConfigApi;

