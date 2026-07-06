/** Split stored team roster into leader + worker names for the create/edit form. */
export function splitTeamRoster(team: {
  leader?: string;
  members?: string[];
}): { leader: string; workers: string[] } {
  const leader = (team.leader ?? "").trim();
  const rawMembers = team.members ?? [];
  const workers = leader
    ? rawMembers.filter((name) => name !== leader)
    : rawMembers.length > 1
      ? rawMembers.slice(1)
      : [];
  return {
    leader: leader || rawMembers[0] || "",
    workers,
  };
}

/** Workers shown in UI; leader is never duplicated in the workers list. */
export function normalizeTeamWorkers(
  leader: string | undefined,
  workers: string[] | undefined,
): string[] {
  const trimmedLeader = (leader ?? "").trim();
  return (workers ?? []).filter(
    (name) => name.trim() && name.trim() !== trimmedLeader,
  );
}

export function countTeamWorkers(team: {
  leader?: string;
  members?: string[];
}): number {
  const { workers } = splitTeamRoster(team);
  return workers.length;
}
