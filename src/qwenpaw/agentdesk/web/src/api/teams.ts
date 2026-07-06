import { request } from "./request";

export interface Team {
  id: string;
  name: string;
  tags: string[];
  desc: string;
  avatar: string;
  members: string[];
  leader: string;
  leader_agent_id?: string;
  usage?: string;
}

export interface CreateTeamBody {
  name: string;
  tags?: string[];
  desc?: string;
  avatar?: string;
  members: string[];
  leader?: string;
}

export const teamsApi = {
  listTeams: () => request<Team[]>("/teams"),

  createTeam: (body: CreateTeamBody) =>
    request<Team>("/teams", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateTeam: (id: string, body: Partial<Team>) =>
    request<Team>(`/teams/${encodeURIComponent(id)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  deleteTeam: (id: string) =>
    request<{ deleted: boolean; id: string }>(
      `/teams/${encodeURIComponent(id)}`,
      { method: "DELETE" },
    ),
};

export default teamsApi;
