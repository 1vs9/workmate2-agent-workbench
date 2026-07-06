import { request } from "./request";

export interface Schedule {
  mode: "cron" | "interval" | "once";
  cron?: string;
  timezone?: string;
  interval_amount?: number;
  interval_unit?: "hours" | "minutes";
  run_at?: string;
}

export interface DateRange {
  start: string | null;
  end: string | null;
}

export interface AutomationJob {
  id: string;
  task_id: string;
  name: string;
  workspace: string;
  prompt: string;
  employee_name: string | null;
  model_name: string | null;
  skill_names: string[];
  chat_mode: "chat" | "plan";
  schedule: Schedule;
  date_range: DateRange;
  enabled: boolean;
  status: string;
  cron_job_id: string | null;
  created_at: number;
  updated_at: number;
  frequency?: string;
  eta?: string;
}

export interface CreateJobBody {
  name: string;
  workspace: string;
  prompt: string;
  employee_name: string | null;
  model_name: string | null;
  skill_names: string[];
  chat_mode: "chat" | "plan";
  schedule: Schedule;
  date_range: DateRange;
}

export interface HistoryItem {
  id: string;
  job_id: string;
  task_id: string;
  name: string;
  workspace: string;
  status: string;
  time: string;
}

export const automationApi = {
  listJobs: () => request<AutomationJob[]>("/automation/jobs"),

  createJob: (body: CreateJobBody) =>
    request<AutomationJob>("/automation/jobs", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateJob: (id: string, body: Partial<CreateJobBody>) =>
    request<AutomationJob>(`/automation/jobs/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  runJob: (id: string) =>
    request<{ id: string; status: string }>(
      `/automation/jobs/${encodeURIComponent(id)}/run`,
      { method: "POST" },
    ),

  pauseJob: (id: string) =>
    request<AutomationJob>(`/automation/jobs/${encodeURIComponent(id)}/pause`, {
      method: "POST",
    }),

  resumeJob: (id: string) =>
    request<AutomationJob>(
      `/automation/jobs/${encodeURIComponent(id)}/resume`,
      { method: "POST" },
    ),

  deleteJob: (id: string) =>
    request<{ deleted: boolean; id: string }>(
      `/automation/jobs/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    ),

  listHistory: () => request<HistoryItem[]>("/automation/history"),
};

export default automationApi;
