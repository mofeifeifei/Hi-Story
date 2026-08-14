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
  notices: Notice[];
  pendingResults: PendingResult[];
  setPage: (page: PageKey) => void;
  setWorks: (works: Work[]) => void;
  selectWork: (id: number | null) => void;
  selectChapter: (chapter: number | null) => void;
  toggleSidebar: () => void;
  toggleInspector: () => void;
  setTask: (task: TaskState | null) => void;
  notify: (message: string, tone?: Notice["tone"]) => void;
  dismissNotice: (id: number) => void;
  addPendingResult: (result: Omit<PendingResult, "id">) => void;
  dismissPendingResult: (id: number) => void;
}

let noticeId = 0;

export const useAppStore = create<AppStore>((set) => ({
  page: "writing",
  works: [],
  selectedWorkId: null,
  selectedChapter: null,
  sidebarCollapsed: false,
  inspectorOpen: window.matchMedia("(min-width: 861px)").matches,
  task: null,
  notices: [],
  pendingResults: [],
  setPage: (page) => set({ page }),
  setWorks: (works) => set({ works }),
  selectWork: (selectedWorkId) => set({ selectedWorkId, selectedChapter: null }),
  selectChapter: (selectedChapter) => set({ selectedChapter }),
  toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
  toggleInspector: () => set((state) => ({ inspectorOpen: !state.inspectorOpen })),
  setTask: (task) => set({ task }),
  notify: (message, tone = "info") => {
    const id = ++noticeId;
    set((state) => ({ notices: [...state.notices, { id, message, tone }] }));
    window.setTimeout(() => set((state) => ({ notices: state.notices.filter((item) => item.id !== id) })), 5200);
  },
  dismissNotice: (id) => set((state) => ({ notices: state.notices.filter((item) => item.id !== id) })),
  addPendingResult: (result) => set((state) => ({ pendingResults: [...state.pendingResults.filter((item) => !(item.workId === result.workId && item.chapterNumber === result.chapterNumber)), { ...result, id: ++noticeId }] })),
  dismissPendingResult: (id) => set((state) => ({ pendingResults: state.pendingResults.filter((item) => item.id !== id) })),
}));
