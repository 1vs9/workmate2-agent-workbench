import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  type Assignee,
  getDefaultAssignee,
} from "../types/assignee";
import type { ComposerTaskSnapshot } from "../utils/composerTaskCache";

interface ComposerState {
  assignee: Assignee;
  skillNames: string[];
  planMode: boolean;
  modelAuto: boolean;
  modelProviderId: string | null;
  modelId: string | null;
  modelName: string | null;
  setAssignee: (assignee: Assignee) => void;
  setSkillNames: (names: string[]) => void;
  toggleSkill: (name: string) => void;
  setPlanMode: (enabled: boolean) => void;
  setModelAuto: (enabled: boolean) => void;
  setModel: (
    providerId: string,
    modelId: string,
    displayName: string,
  ) => void;
  resetAssignee: () => void;
  /** Fresh composer for a new task chat (default agent + optional skills). */
  resetForNewChat: (skillNames?: string[], assignee?: Assignee) => void;
  applyComposerSnapshot: (snapshot: ComposerTaskSnapshot) => void;
}

export const useComposerStore = create<ComposerState>()(
  persist(
    (set, get) => ({
      assignee: getDefaultAssignee(),
      skillNames: [],
      planMode: false,
      modelAuto: true,
      modelProviderId: null,
      modelId: null,
      modelName: null,
      setAssignee: (assignee) => set({ assignee }),
      setSkillNames: (skillNames) => set({ skillNames }),
      toggleSkill: (name) => {
        const current = get().skillNames;
        if (current.includes(name)) {
          set({ skillNames: current.filter((n) => n !== name) });
        } else {
          set({ skillNames: [...current, name] });
        }
      },
      setPlanMode: (planMode) => set({ planMode }),
      setModelAuto: (modelAuto) => set({ modelAuto }),
      setModel: (modelProviderId, modelId, modelName) =>
        set({
          modelAuto: false,
          modelProviderId,
          modelId,
          modelName,
        }),
      resetAssignee: () => set({ assignee: getDefaultAssignee() }),
      resetForNewChat: (skillNames = [], assignee) =>
        set({
          assignee: assignee ?? getDefaultAssignee(),
          skillNames,
          planMode: false,
        }),
      applyComposerSnapshot: (snapshot) =>
        set({
          assignee: snapshot.assignee,
          skillNames: [...snapshot.skillNames],
          planMode: snapshot.planMode,
        }),
    }),
    {
      name: "agentdesk-composer",
      partialize: (state) => ({
        assignee: state.assignee,
        planMode: state.planMode,
        modelAuto: state.modelAuto,
        modelProviderId: state.modelProviderId,
        modelId: state.modelId,
        modelName: state.modelName,
      }),
      merge: (persistedState, currentState) => ({
        ...currentState,
        ...(persistedState as object),
        // Skills are per-task intent, not session defaults — never restore from storage.
        skillNames: [],
      }),
    },
  ),
);
