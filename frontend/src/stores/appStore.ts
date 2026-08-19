import { create } from "zustand";
import type { Notice, PageKey, PendingResult, TaskState, Work } from "../types";

interface AppStore {
  page: PageKey;
  works: Work[];
  selectedWorkId: number | null;
  selectedChapter: number | null;
  sidebarCollapsed: boolean;
  inspectorOpen: boolean;
  task: TaskState | null;
  tasks: TaskState[];
  notices: Notice[];
  pendingResults: PendingResult[];
  navigationGuard: (() => boolean) | null;
  setPage: (page: PageKey) => void;
  setWorks: (works: Work[]) => void;
  selectWork: (id: number | null) => void;
  selectChapter: (chapter: number | null) => void;
  toggleSidebar: () => void;
  toggleInspector: () => void;
  setTask: (task: TaskState | null) => void;
  removeTask: (taskId: string) => void;
  syncTasks: (tasks: TaskState[]) => void;
  setNavigationGuard: (guard: (() => boolean) | null) => void;
  notify: (message: string, tone?: Notice["tone"]) => void;
  dismissNotice: (id: number) => void;
  addPendingResult: (result: Omit<PendingResult, "id">) => void;
  dismissPendingResult: (id: number) => void;
}

let noticeId = 0;

export const useAppStore = create<AppStore>((set, get) => ({
  page: "writing",
  works: [],
  selectedWorkId: null,
  selectedChapter: null,
  sidebarCollapsed: false,
  inspectorOpen: window.matchMedia("(min-width: 861px)").matches,
  task: null,
  tasks: [],
  notices: [],
  pendingResults: [],
  navigationGuard: null,
  setPage: (page) => {
    if (page === get().page) return;
    const guard = get().navigationGuard;
    if (guard && !guard()) return;
    set({ page, navigationGuard: null });
  },
  setWorks: (works) => set({ works }),
  selectWork: (selectedWorkId) => {
    if (selectedWorkId === get().selectedWorkId) return;
    const guard = get().navigationGuard;
    if (guard && !guard()) return;
    set({ selectedWorkId, selectedChapter: null, navigationGuard: null });
  },
  selectChapter: (selectedChapter) => set({ selectedChapter }),
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  toggleInspector: () => set((state) => ({ inspectorOpen: !state.inspectorOpen })),
  setTask: (task) => set((state) => {
    if (task === null) {
      const currentId = state.task?.id;
      const tasks = currentId ? state.tasks.filter((item) => item.id !== currentId) : state.tasks;
      return { tasks, task: tasks[0] || null };
    }
    const tasks = [...state.tasks.filter((item) => item.id !== task.id), task];
    return { tasks, task };
  }),
  removeTask: (taskId) => set((state) => {
    const tasks = state.tasks.filter((item) => item.id !== taskId);
    const current = state.task?.id === taskId ? tasks[0] || null : state.task;
    return { tasks, task: current };
  }),
  syncTasks: (remoteTasks) => set((state) => {
    const byId = new Map(state.tasks.map((item) => [item.id, item]));
    const tasks = remoteTasks.map((remote) => ({ ...byId.get(remote.id), ...remote, controller: byId.get(remote.id)?.controller || new AbortController() }));
    const current = state.task && tasks.find((item) => item.id === state.task?.id) || tasks[0] || null;
    return { tasks, task: current };
  }),
  setNavigationGuard: (navigationGuard) => set({ navigationGuard }),
  notify: (message, tone = "info") => {
    const id = ++noticeId;
    set((state) => ({ notices: [...state.notices, { id, message, tone }] }));
    window.setTimeout(() => set((state) => ({ notices: state.notices.filter((item) => item.id !== id) })), 5200);
  },
  dismissNotice: (id) => set((state) => ({ notices: state.notices.filter((item) => item.id !== id) })),
  addPendingResult: (result) => set((state) => ({ pendingResults: [...state.pendingResults.filter((item) => !(item.workId === result.workId && item.chapterNumber === result.chapterNumber)), { ...result, id: ++noticeId }] })),
  dismissPendingResult: (id) => set((state) => ({ pendingResults: state.pendingResults.filter((item) => item.id !== id) })),
}));
