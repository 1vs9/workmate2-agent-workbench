import { buildAuthHeaders } from "./authHeaders";

export interface StreamEvent {
  type: string;
  [key: string]: unknown;
}

export interface ChatStreamBody {
  task_id: string;
  message?: string;
  reconnect?: boolean;
  mode?: "single" | "team";
  chat_mode?: "chat" | "plan";
  intent?: string;
  employee_name?: string;
  team_id?: string;
  team_name?: string;
  team_member?: string;
  skill_names?: string[];
  choice_payload?: Record<string, unknown>;
  wizard_action?: string;
  wizard_payload?: Record<string, unknown>;
  [key: string]: unknown;
}

function getStreamUrl(): string {
  const base = import.meta.env.VITE_API_BASE_URL || "";
  return `${base}/api/chat/stream`;
}

/** SSE chat stream — mirrors legacy AgentDeskAPI.chatStream. */
export async function chatStream(
  body: ChatStreamBody,
  onEvent: (event: StreamEvent) => void,
  options: {
    signal?: AbortSignal;
    timeoutMs?: number;
    idleTimeoutMs?: number;
    onController?: (controller: AbortController) => void;
  } = {},
): Promise<void> {
  const idleTimeoutMs = options.idleTimeoutMs ?? 180_000;
  // Absolute timeout applies only until the HTTP response headers arrive; default
  // it to at least the idle budget so a slow cold start is not cut off early.
  const timeoutMs = options.timeoutMs ?? Math.max(180_000, idleTimeoutMs + 60_000);
  const controller = options.signal ? null : new AbortController();
  const signal = options.signal ?? controller!.signal;
  if (options.onController && controller) {
    options.onController(controller);
  }

  const timer = window.setTimeout(() => controller?.abort(), timeoutMs);
  let idleTimer: ReturnType<typeof setTimeout> | null = null;

  const bumpIdleTimer = () => {
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(() => controller?.abort(), idleTimeoutMs);
  };

  let response: Response;
  try {
    response = await fetch(getStreamUrl(), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...buildAuthHeaders(),
      },
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      if (signal.aborted) throw err;
      throw new Error("请求超时，请稍后重试。");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("无法读取响应流");

  const decoder = new TextDecoder();
  let buffer = "";
  bumpIdleTimer();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bumpIdleTimer();
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data:")) continue;
        const jsonStr = line.slice(5).trim();
        if (!jsonStr) continue;
        try {
          const evt = JSON.parse(jsonStr) as StreamEvent;
          onEvent(evt);
          bumpIdleTimer();
        } catch (e) {
          console.warn("[chatStream] SSE parse error", e);
        }
      }
    }
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      if (signal.aborted) throw err;
      throw new Error("连接长时间无响应，已自动停止。可点击停止后重试。");
    }
    throw err;
  } finally {
    if (idleTimer) clearTimeout(idleTimer);
  }
}

/** Reconnect to an in-progress task stream (legacy AgentDeskAPI.chatStreamReconnect). */
export async function chatStreamReconnect(
  taskId: string,
  onEvent: (event: StreamEvent) => void,
  options: {
    signal?: AbortSignal;
    timeoutMs?: number;
    idleTimeoutMs?: number;
    onController?: (controller: AbortController) => void;
  } = {},
): Promise<void> {
  return chatStream(
    { task_id: taskId, message: "", reconnect: true },
    onEvent,
    options,
  );
}

/** Approve or deny a pending tool/action (legacy AgentDeskAPI.approveChat). */
export async function chatApprove(
  taskId: string,
  approved = true,
): Promise<void> {
  const base = import.meta.env.VITE_API_BASE_URL || "";
  const response = await fetch(`${base}/api/chat/approve`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildAuthHeaders(),
    },
    body: JSON.stringify({ task_id: taskId, approved }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
}
