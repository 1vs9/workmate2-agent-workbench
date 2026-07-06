import { request } from "./request";

export type ChatStatus = "idle" | "running";

export interface ChatSpec {
  id: string;
  session_id: string;
  user_id: string;
  channel: string;
  name?: string;
  created_at: string | null;
  updated_at: string | null;
  meta?: Record<string, unknown>;
  status?: ChatStatus;
  pinned?: boolean;
}

export interface Message {
  role: string;
  content: unknown;
  [key: string]: unknown;
}

export interface ChatHistory {
  messages: Message[];
  status?: ChatStatus;
}

export interface ChatUpdateRequest {
  name?: string;
  pinned?: boolean;
}

function toQuery(params?: Record<string, string | undefined>): string {
  if (!params) return "";
  const pairs = Object.entries(params).filter(
    (entry): entry is [string, string] => entry[1] != null && entry[1] !== "",
  );
  if (pairs.length === 0) return "";
  return (
    "?" +
    pairs
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join("&")
  );
}

export const chatApi = {
  listChats: (params?: { user_id?: string; channel?: string }) =>
    request<ChatSpec[]>(`/chats${toQuery(params)}`),

  createChat: (chat: Partial<ChatSpec>) =>
    request<ChatSpec>("/chats", {
      method: "POST",
      body: JSON.stringify(chat),
    }),

  getChat: (chatId: string) =>
    request<ChatHistory>(`/chats/${encodeURIComponent(chatId)}`),

  updateChat: (chatId: string, chat: ChatUpdateRequest) =>
    request<ChatSpec>(`/chats/${encodeURIComponent(chatId)}`, {
      method: "PUT",
      body: JSON.stringify(chat),
    }),

  deleteChat: (chatId: string) =>
    request<{ deleted: boolean }>(`/chats/${encodeURIComponent(chatId)}`, {
      method: "DELETE",
    }),

  stopChat: (chatId: string) =>
    request<void>(`/console/chat/stop?chat_id=${encodeURIComponent(chatId)}`, {
      method: "POST",
    }),
};

export default chatApi;
