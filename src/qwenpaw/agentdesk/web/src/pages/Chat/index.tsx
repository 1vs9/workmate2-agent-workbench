import {
  AgentScopeRuntimeWebUI,
  type IAgentScopeRuntimeWebUIOptions,
  type IAgentScopeRuntimeWebUIRef,
} from "@agentscope-ai/chat";
import { useCallback, useMemo, useRef } from "react";
import sessionApi from "./sessionApi";
import defaultConfig from "./defaultConfig";
import chatApi from "../../api/chat";
import { getApiUrl } from "../../api/config";
import { buildAuthHeaders } from "../../api/authHeaders";
import { useTheme } from "../../theme/ThemeContext";
import { extractUserMessageText, normalizeContentUrls, toDisplayUrl } from "./utils";

const DEFAULT_USER_ID = "default";
const DEFAULT_CHANNEL = "console";

interface SessionInfo {
  session_id?: string;
  user_id?: string;
  channel?: string;
}

interface CustomWindow extends Window {
  currentSessionId?: string;
  currentUserId?: string;
  currentChannel?: string;
}

declare const window: CustomWindow;

export default function ChatPage() {
  const { isDark } = useTheme();
  const chatRef = useRef<IAgentScopeRuntimeWebUIRef>(null);

  const customFetch = useCallback(
    async (data: {
      input?: Array<Record<string, unknown>>;
      biz_params?: Record<string, unknown>;
      signal?: AbortSignal;
    }): Promise<Response> => {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...buildAuthHeaders(),
      };

      const { input = [], biz_params } = data;
      const session: SessionInfo =
        (input[input.length - 1]?.session as SessionInfo) || {};
      const lastInput = input.slice(-1);
      const lastMsg = lastInput[0];
      const rewrittenInput =
        lastMsg?.content && Array.isArray(lastMsg.content)
          ? [
              {
                ...lastMsg,
                content: (lastMsg.content as Array<Record<string, unknown>>).map(
                  (c) => normalizeContentUrls(c as never),
                ),
              },
            ]
          : lastInput;

      const requestBody = {
        input: rewrittenInput,
        session_id: window.currentSessionId || session?.session_id || "",
        user_id: window.currentUserId || session?.user_id || DEFAULT_USER_ID,
        channel: window.currentChannel || session?.channel || DEFAULT_CHANNEL,
        stream: true,
        ...biz_params,
      };

      const backendChatId =
        sessionApi.getRealIdForSession(requestBody.session_id) ??
        requestBody.session_id;
      if (backendChatId) {
        const userText = (rewrittenInput as Array<{ role?: string }>)
          .filter((m) => m.role === "user")
          .map((m) => extractUserMessageText(m as never))
          .join("\n")
          .trim();
        if (userText) {
          sessionApi.setLastUserMessage(backendChatId, userText);
        }
      }

      return fetch(getApiUrl("/console/chat"), {
        method: "POST",
        headers,
        body: JSON.stringify(requestBody),
        signal: data.signal,
      });
    },
    [],
  );

  const options = useMemo(() => {
    return {
      ...defaultConfig,
      theme: {
        ...defaultConfig.theme,
        darkMode: isDark,
        leftHeader: {
          ...defaultConfig.theme.leftHeader,
          title: "AgentDesk",
        },
      },
      welcome: {
        ...defaultConfig.welcome,
      },
      sender: {
        ...defaultConfig.sender,
      },
      session: {
        multiple: true,
        hideBuiltInSessionList: false,
        api: sessionApi,
      },
      api: {
        ...defaultConfig.api,
        fetch: customFetch,
        responseParser: (chunk: string) =>
          JSON.parse(chunk) as Record<string, unknown>,
        replaceMediaURL: (url: string) => toDisplayUrl(url),
        cancel(data: { session_id: string }) {
          const resolvedChatId =
            sessionApi.getRealIdForSession(data.session_id) ?? data.session_id;
          if (resolvedChatId) {
            chatApi.stopChat(resolvedChatId).catch((err) => {
              console.error("Failed to stop chat:", err);
            });
          }
        },
        async reconnect(data: { session_id: string; signal?: AbortSignal }) {
          const headers: Record<string, string> = {
            "Content-Type": "application/json",
            ...buildAuthHeaders(),
          };
          return fetch(getApiUrl("/console/chat"), {
            method: "POST",
            headers,
            body: JSON.stringify({
              reconnect: true,
              session_id: window.currentSessionId || data.session_id,
              user_id: window.currentUserId || DEFAULT_USER_ID,
              channel: window.currentChannel || DEFAULT_CHANNEL,
            }),
            signal: data.signal,
          });
        },
      },
    } as unknown as IAgentScopeRuntimeWebUIOptions;
  }, [customFetch, isDark]);

  return (
    <div
      style={{
        height: "100%",
        width: "100%",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <AgentScopeRuntimeWebUI ref={chatRef} options={options} />
    </div>
  );
}
