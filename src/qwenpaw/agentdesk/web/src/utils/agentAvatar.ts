/** Humanized avatar helpers — portrait URLs, initials fallback (no emoji). */

const AVATAR_PALETTE = [
  { bg: "#E8EDF5", text: "#334155" },
  { bg: "#F5E6E0", text: "#7C2D12" },
  { bg: "#E6F0EC", text: "#065F46" },
  { bg: "#EDE9FE", text: "#5B21B6" },
  { bg: "#FEF3C7", text: "#92400E" },
  { bg: "#E0F2FE", text: "#075985" },
  { bg: "#FCE7F3", text: "#9D174D" },
  { bg: "#F3F4F6", text: "#374151" },
] as const;

const EMOJI_AVATAR_RE =
  /^[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F1E6}-\u{1F1FF}\u{2300}-\u{23FF}\u{2B50}\u{1F004}\u{1F0CF}]+$/u;

export type AvatarColors = (typeof AVATAR_PALETTE)[number];

export function hashString(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 31 + value.charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

export function isEmojiAvatar(avatar?: string): boolean {
  const trimmed = avatar?.trim();
  if (!trimmed) return false;
  return EMOJI_AVATAR_RE.test(trimmed) || trimmed.length <= 4;
}

export function isAvatarImageUrl(avatar?: string): boolean {
  const trimmed = avatar?.trim();
  if (!trimmed) return false;
  if (isEmojiAvatar(trimmed)) return false;
  return (
    /^https?:\/\//i.test(trimmed) ||
    trimmed.startsWith("/api/avatars/") ||
    trimmed.startsWith("/") ||
    trimmed.startsWith("data:")
  );
}

export function getInitialsFromName(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";

  const words = trimmed.split(/\s+/).filter(Boolean);
  if (words.length >= 2 && /^[A-Za-z]/.test(words[0] ?? "")) {
    return `${words[0]![0] ?? ""}${words[1]![0] ?? ""}`.toUpperCase();
  }

  const chars = Array.from(trimmed.replace(/\s+/g, ""));
  if (chars.length <= 2) return chars.join("");
  return chars.slice(0, 2).join("");
}

export function getAvatarColorsFromName(name: string): AvatarColors {
  const trimmed = name.trim();
  if (!trimmed) return AVATAR_PALETTE[0]!;
  return AVATAR_PALETTE[hashString(trimmed) % AVATAR_PALETTE.length]!;
}
