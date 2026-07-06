import { request } from "./request";

export type AvatarRole = "employee" | "team";

export interface GenerateAvatarBody {
  name: string;
  description?: string;
  desc?: string;
  role?: AvatarRole;
}

export interface GenerateAvatarResponse {
  url: string;
  seed: string;
}

export const avatarsApi = {
  generate: (body: GenerateAvatarBody) =>
    request<GenerateAvatarResponse>("/avatars/generate", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export default avatarsApi;
