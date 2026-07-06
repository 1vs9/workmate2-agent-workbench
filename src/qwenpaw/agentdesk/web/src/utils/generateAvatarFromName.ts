/** Deterministic human portrait URLs (DiceBear Personas, cached by backend). */

import type { AvatarRole } from "../api/avatars";

async function sha256Hex(value: string): Promise<string> {
  const data = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export function avatarSeedSync(name: string, description: string, role: AvatarRole): string {
  const raw = `${role}:${name.trim()}:${description.trim()}`;
  let hash = 0;
  for (let i = 0; i < raw.length; i += 1) {
    hash = (hash * 31 + raw.charCodeAt(i)) | 0;
  }
  const positive = Math.abs(hash);
  return positive.toString(16).padStart(16, "0").slice(0, 16);
}

export async function avatarSeed(
  name: string,
  description = "",
  role: AvatarRole = "employee",
): Promise<string> {
  const raw = `${role}:${name.trim()}:${description.trim()}`;
  if (globalThis.crypto?.subtle) {
    const hex = await sha256Hex(raw);
    return hex.slice(0, 16);
  }
  return avatarSeedSync(name, description, role);
}

export function portraitAvatarUrl(seed: string): string {
  return `/api/avatars/${seed}.svg`;
}

/** Immediate portrait URL (sync hash; may differ from SHA-256 until async refresh). */
export function buildPortraitAvatarUrlSync(
  name: string,
  description = "",
  role: AvatarRole = "employee",
): string {
  return portraitAvatarUrl(avatarSeedSync(name, description, role));
}

export async function buildPortraitAvatarUrl(
  name: string,
  description = "",
  role: AvatarRole = "employee",
): Promise<string> {
  const seed = await avatarSeed(name, description, role);
  return portraitAvatarUrl(seed);
}

/** Employee portrait URL from name + optional description. */
export async function generateAvatarFromName(
  name: string,
  description = "",
): Promise<string> {
  return buildPortraitAvatarUrl(name, description, "employee");
}

/** Team portrait URL from name + optional description. */
export async function generateTeamAvatarFromName(
  name: string,
  description = "",
): Promise<string> {
  return buildPortraitAvatarUrl(name, description, "team");
}
