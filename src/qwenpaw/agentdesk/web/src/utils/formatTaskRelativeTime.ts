/** Normalize Unix seconds or milliseconds to epoch milliseconds. */
export function normalizeTimestampMs(value?: number | string | null): number | undefined {
  if (value == null || value === "") return undefined;
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n) || n <= 0) return undefined;
  // Backend uses time.time() (seconds); JS Date uses ms (~1e12+).
  return n < 1e12 ? n * 1000 : n;
}

/** Human-readable relative time for sidebar task rows (e.g. 刚刚, 19分钟前). */
export function formatTaskRelativeTime(timestamp?: number | null): string {
  const ms = normalizeTimestampMs(timestamp);
  if (ms == null) return "";

  const diffMs = Date.now() - ms;
  if (diffMs < 0) return "刚刚";

  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return "刚刚";

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}分钟前`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前`;

  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}天前`;

  const months = Math.floor(days / 30);
  if (months < 12) return `${months}个月前`;

  const years = Math.floor(months / 12);
  return `${years}年前`;
}

export function taskTimestamp(task: {
  updatedAt?: number | string;
  updated_at?: number | string;
  createdAt?: number | string;
  created_at?: number | string;
}): number | undefined {
  const raw =
    task.updatedAt ??
    task.updated_at ??
    task.createdAt ??
    task.created_at;
  return normalizeTimestampMs(raw);
}
