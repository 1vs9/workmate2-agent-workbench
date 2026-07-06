import { buildAuthHeaders } from "./authHeaders";

export interface ProbeResult {
  ok: boolean;
  base?: string;
  error?: string;
}

const FALLBACK_BASES = ["http://127.0.0.1:8088", "http://localhost:8088"];

function getCandidateBases(): string[] {
  const list: string[] = [];
  if (typeof window !== "undefined" && window.location.protocol.startsWith("http")) {
    list.push(window.location.origin);
  }
  const envBase = import.meta.env.VITE_API_BASE_URL;
  if (envBase) list.push(envBase.replace(/\/$/, ""));
  for (const base of FALLBACK_BASES) {
    if (!list.includes(base)) list.push(base);
  }
  return list;
}

async function probeBase(base: string): Promise<ProbeResult> {
  try {
    const health = await fetch(`${base}/health`, {
      method: "GET",
      cache: "no-store",
    });
    if (!health.ok) {
      return { ok: false, base, error: `/health HTTP ${health.status}` };
    }
    const tools = await fetch(`${base}/api/tools`, {
      method: "GET",
      cache: "no-store",
      headers: buildAuthHeaders(),
    });
    if (!tools.ok) {
      return { ok: false, base, error: `/api/tools HTTP ${tools.status}` };
    }
    return { ok: true, base };
  } catch (err) {
    return {
      ok: false,
      base,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

/** Check backend /health and /api/tools (mirrors legacy AgentDeskAPI.probe). */
export async function probeBackend(): Promise<ProbeResult> {
  const errors: string[] = [];
  for (const base of getCandidateBases()) {
    const result = await probeBase(base);
    if (result.ok) return result;
    if (result.error) errors.push(`${base}: ${result.error}`);
  }
  return {
    ok: false,
    error: errors[0] || "无法连接后端",
  };
}
