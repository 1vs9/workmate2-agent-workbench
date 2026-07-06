import { create } from "zustand";

interface SkillsState {
  revision: number;
  bumpSkillsRevision: () => void;
}

/** Global signal for skills list consumers to refetch after chat create/upload. */
export const useSkillsStore = create<SkillsState>((set) => ({
  revision: 0,
  bumpSkillsRevision: () => set((state) => ({ revision: state.revision + 1 })),
}));
