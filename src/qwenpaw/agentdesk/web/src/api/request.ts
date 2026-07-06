import { getApiUrl } from "./config";
import { buildAuthHeaders } from "./authHeaders";

/** Thrown for non-2xx API responses. */
export class ApiError extends Error {
  status: number;
  detail?: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Extract a readable message from a FastAPI error body (string or {detail}). */
function parseErrorDetail(
  body: string,
  fallback: string,
): { message: string; detail?: unknown } {
  if (!body) return { message: fallback };
  try {
    const json = JSON.parse(body);
    const detail = (json as { detail?: unknown }).detail;
    if (Array.isArray(detail)) {
      return {
        message: detail
          .map((d) =>
            typeof d === "object" && d && "msg" in d
              ? String((d as { msg: unknown }).msg)
              : JSON.stringify(d),
          )
          .join("; "),
        detail,
      };
    }
    if (typeof detail === "string") return { message: detail, detail };
    if (typeof detail === "object" && detail !== null) {
      const conflicts = (detail as { conflicts?: unknown[] }).conflicts;
      if (Array.isArray(conflicts) && conflicts.length) {
        const names = conflicts
          .map((item) =>
            typeof item === "object" && item && "skill_name" in item
              ? String((item as { skill_name: unknown }).skill_name)
              : "",
          )
          .filter(Boolean);
        const message =
          names.length === 1
            ? `技能「${names[0]}」已存在于技能库中`
            : `以下技能已存在于技能库中：${names.join("、")}`;
        return { message, detail };
      }
      return { message: JSON.stringify(detail), detail };
    }
    return { message: body };
  } catch {
    return { message: body };
  }
}

/**
 * JSON request helper against the `/api` backend. Adds auth headers and a JSON
 * Content-Type by default; parses the JSON body and throws ApiError on failure.
 * When the body is FormData, the Content-Type is left to the browser so the
 * multipart boundary is set correctly.
 */
export async function request<T>(
  path: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<T> {
  const { timeoutMs = 120_000, ...fetchInit } = init;
  const isFormData =
    typeof FormData !== "undefined" && fetchInit.body instanceof FormData;

  const headers: Record<string, string> = {
    ...(isFormData ? {} : { "Content-Type": "application/json" }),
    ...buildAuthHeaders(),
    ...((fetchInit.headers as Record<string, string>) ?? {}),
  };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  if (fetchInit.signal) {
    fetchInit.signal.addEventListener("abort", () => controller.abort(), {
      once: true,
    });
  }

  let response: Response;
  try {
    response = await fetch(getApiUrl(path), {
      ...fetchInit,
      headers,
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new ApiError(
        408,
        `请求超时（${Math.round(timeoutMs / 1000)} 秒），请稍后重试`,
      );
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    let body = "";
    try {
      body = await response.text();
    } catch {
      /* ignore */
    }
    const parsed = parseErrorDetail(body, response.statusText);
    throw new ApiError(response.status, parsed.message, parsed.detail);
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}
