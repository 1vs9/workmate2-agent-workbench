import { create } from "zustand";

import modelConfigApi, { type Provider } from "../api/modelConfig";
import { plazaApi, type Employee, type PlazaCard } from "../api/plaza";
import { skillsApi, type SkillItem } from "../api/skills";
import { teamsApi, type Team } from "../api/teams";
import { useSkillsStore } from "./skillsStore";

/**
 * Shared, cached reference data (plaza / employees / teams / skills / model providers).
 *
 * These lists are read by many components that mount on every chat open or
 * task switch (notably {@link ComposerToolbar}, Plaza, and the TaskChat page).
 * Fetching them independently on each mount produced 4-6 redundant requests per
 * switch and made switching feel slow. This store fetches once and serves a cached
 * copy with a stale-while-revalidate policy:
 *
 * - `ensureLoaded()` renders instantly from cache and only hits the network
 *   when the cache is empty or older than the freshness window. Concurrent
 *   callers share a single in-flight request (no thundering herd on switch).
 * - Mutation sites (plaza / team / skill management) call `invalidate()` or a
 *   targeted refresher so the cache reflects new data on the next mount.
 * - Skill uploads already bump {@link useSkillsStore}; we bridge that signal to
 *   transparently refresh the cached skill list.
 */

const DEFAULT_MAX_AGE_MS = 20_000;
const SESSION_PLAZA_KEY = "wm.ref.plaza";
const SESSION_EMPLOYEES_KEY = "wm.ref.employees";

interface ReferenceDataState {
  plazaCards: PlazaCard[];
  employees: Employee[];
  teams: Team[];
  skills: SkillItem[];
  providers: Provider[];
  loadedAt: number;
  loading: boolean;
  /** Fetch all lists if never loaded or stale; dedupes concurrent callers. */
  ensureLoaded: (maxAgeMs?: number) => Promise<void>;
  /** Force a full refetch of every list. */
  refresh: () => Promise<void>;
  refreshPlaza: () => Promise<void>;
  refreshEmployees: () => Promise<void>;
  refreshTeams: () => Promise<void>;
  refreshSkills: () => Promise<void>;
  /** Mark the cache stale so the next ensureLoaded refetches. */
  invalidate: () => void;
}

let inflight: Promise<void> | null = null;

function filterEnabledSkills(items: SkillItem[]): SkillItem[] {
  return items.filter((item) => item.enabled !== false);
}

function readSessionJson<T>(key: string): T[] {
  if (typeof sessionStorage === "undefined") return [];
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return [];
  }
}

function writeSessionJson(key: string, value: unknown[]): void {
  if (typeof sessionStorage === "undefined") return;
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Quota or privacy mode — ignore.
  }
}

export const useReferenceDataStore = create<ReferenceDataState>((set, get) => {
  const fetchAll = async (): Promise<void> => {
    const [plaza, emp, teamList, skillList, config] = await Promise.all([
      plazaApi.listPlaza().catch(() => null),
      plazaApi.listEmployees().catch(() => null),
      teamsApi.listTeams().catch(() => null),
      skillsApi.listSkills().catch(() => null),
      modelConfigApi.getConfig().catch(() => null),
    ]);
    if (plaza) writeSessionJson(SESSION_PLAZA_KEY, plaza);
    if (emp) writeSessionJson(SESSION_EMPLOYEES_KEY, emp);
    set((prev) => ({
      plazaCards: plaza ?? prev.plazaCards,
      employees: emp ?? prev.employees,
      teams: teamList ?? prev.teams,
      skills: skillList ? filterEnabledSkills(skillList) : prev.skills,
      providers: config?.providers ?? prev.providers,
      loadedAt: Date.now(),
      loading: false,
    }));
  };

  const runFullRefresh = (): Promise<void> => {
    if (inflight) return inflight;
    set({ loading: true });
    inflight = fetchAll().finally(() => {
      inflight = null;
    });
    return inflight;
  };

  return {
    plazaCards: readSessionJson<PlazaCard>(SESSION_PLAZA_KEY),
    employees: readSessionJson<Employee>(SESSION_EMPLOYEES_KEY),
    teams: [],
    skills: [],
    providers: [],
    loadedAt: 0,
    loading: false,

    ensureLoaded: (maxAgeMs = DEFAULT_MAX_AGE_MS) => {
      const { loadedAt } = get();
      const fresh = loadedAt > 0 && Date.now() - loadedAt < maxAgeMs;
      if (fresh) return Promise.resolve();
      return runFullRefresh();
    },

    refresh: () => runFullRefresh(),

    refreshPlaza: async () => {
      const plaza = await plazaApi.listPlaza().catch(() => null);
      if (plaza) {
        writeSessionJson(SESSION_PLAZA_KEY, plaza);
        set({ plazaCards: plaza, loadedAt: Date.now() });
      }
    },

    refreshEmployees: async () => {
      const emp = await plazaApi.listEmployees().catch(() => null);
      if (emp) {
        writeSessionJson(SESSION_EMPLOYEES_KEY, emp);
        set({ employees: emp });
      }
    },

    refreshTeams: async () => {
      const teamList = await teamsApi.listTeams().catch(() => null);
      if (teamList) set({ teams: teamList });
    },

    refreshSkills: async () => {
      const skillList = await skillsApi.listSkills().catch(() => null);
      if (skillList) set({ skills: filterEnabledSkills(skillList) });
    },

    invalidate: () => set({ loadedAt: 0 }),
  };
});

// Bridge the existing skills revision signal (bumped after skill create/upload)
// so the cached skill list refreshes without each consumer re-subscribing.
// Guarded so partial mocks of useSkillsStore (e.g. in unit tests) stay safe.
if (typeof useSkillsStore.subscribe === "function") {
  useSkillsStore.subscribe((state, prev) => {
    if (state.revision === prev.revision) return;
    const store = useReferenceDataStore.getState();
    if (store.loadedAt > 0) {
      void store.refreshSkills();
    }
  });
}
