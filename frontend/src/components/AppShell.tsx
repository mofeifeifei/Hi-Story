import { useEffect, useState, type ReactNode } from "react";
import {
  Archive, BookOpenText, ChevronDown, CircleStop, FileOutput, FolderPen, Library,
  LoaderCircle, Menu, Plus, RefreshCw, ScrollText, Settings, X,
} from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, cancelTask } from "../services/api";
import { useAppStore } from "../stores/appStore";
import type { PageKey, TaskState, Work } from "../types";

const pages: Array<{ key: PageKey; label: string; icon: typeof FolderPen }> = [
  { key: "project", label: "作品设定", icon: FolderPen },
  { key: "outline", label: "大纲与细纲", icon: ScrollText },
  { key: "writing", label: "正文写作", icon: BookOpenText },
  { key: "library", label: "资料库", icon: Library },
  { key: "export", label: "导出", icon: FileOutput },
  { key: "records", label: "运行记录", icon: Archive },
  { key: "settings", label: "设置", icon: Settings },
];

export function AppShell({ children }: { children: ReactNode }) {
  const store = useAppStore();
  const queryClient = useQueryClient();
  const [creatingWork, setCreatingWork] = useState(false);
  const health = useQuery({ queryKey: ["health"], queryFn: () => api<Record<string, unknown>>("/api/health"), refetchInterval: 30_000 });
  const worksQuery = useQuery({ queryKey: ["works"], queryFn: () => api<{ works: Work[] }>("/api/works") });
  const activeTaskQuery = useQuery({ queryKey: ["active-task"], queryFn: () => api<{ tasks?: Array<Record<string, unknown>> }>("/api/tasks/active"), refetchInterval: 1500 });
  const currentWork = store.works.find((work) => Number(work.id) === Number(store.selectedWorkId));

  useEffect(() => {
    if (!worksQuery.data) return;
    const works = worksQuery.data.works || [];
    store.setWorks(works);
    if ((!store.selectedWorkId || !works.some((work) => Number(work.id) === Number(store.selectedWorkId))) && works.length) store.selectWork(works[0].id);
  }, [worksQuery.data]);

  useEffect(() => {
    const remoteTasks = (activeTaskQuery.data?.tasks || []).map((task): TaskState => {
      const startedAt = Date.parse(String(task.started_at || ""));
      return {
        id: String(task.id),
        kind: String(task.kind || "task"),
        title: String(task.title || "AI 任务"),
        detail: String(task.detail || task.stage || ""),
        startedAt: Number.isFinite(startedAt) ? startedAt : Date.now(),
        remoteSeen: true,
        controller: new AbortController(),
        workId: Number(task.work_id || 0) || undefined,
        chapterNumber: Number(task.chapter_number || 0) || undefined,
      };
    });
    const remoteIds = new Set(remoteTasks.map((task) => task.id));
    for (const previous of store.tasks) {
      if (remoteIds.has(previous.id)) continue;
      // The POST that creates a task and this polling request are independent
      // HTTP requests. Keep a just-created local task briefly until the server
      // has had a chance to register it; the request's finally block still
      // removes it immediately when it completes or fails.
      if (!previous.remoteSeen && Date.now() - previous.startedAt < 5000) continue;
      queryClient.invalidateQueries({ queryKey: ["work", previous.workId] });
      queryClient.invalidateQueries({ queryKey: ["outline-state", previous.workId] });
      queryClient.invalidateQueries({ queryKey: ["chapter", previous.workId] });
      queryClient.invalidateQueries({ queryKey: ["library-counts", previous.workId] });
      queryClient.invalidateQueries({ queryKey: ["records-page", previous.workId] });
    }
    store.syncTasks(remoteTasks);
  }, [activeTaskQuery.data]);

  useEffect(() => {
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!store.navigationGuard) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [store.navigationGuard]);

  async function createWork() {
    if (creatingWork || store.tasks.length) {
      if (store.tasks.length) store.notify("当前仍有任务运行，请等待完成后再新建作品。", "warning");
      return;
    }
    const guard = store.navigationGuard;
    if (guard && !guard()) return;
    setCreatingWork(true);
    try {
      const data = await api<{ work: Work; works: Work[] }>("/api/works", {
        method: "POST",
        body: { title: "未命名作品", idea: "", genre: "", platform: "", target_words: 0, style: "" },
      });
      store.setWorks(data.works || [...store.works, data.work]);
      store.setNavigationGuard(null);
      store.selectWork(data.work.id);
      store.setPage("project");
      queryClient.setQueryData(["works"], { works: data.works });
      store.notify("新作品已创建。", "success");
    } catch (error) { store.notify((error as Error).message, "danger"); }
    finally { setCreatingWork(false); }
  }

  async function stopTask(task: TaskState) {
    const taskId = task.id;
    try {
      await cancelTask(taskId);
      store.setTask({ ...task, detail: "正在终止模型请求" });
      store.notify("正在停止任务；已经完整返回的修订稿会保留为候选稿。", "warning");
    } catch (error) {
      store.notify(`停止任务失败：${(error as Error).message}`, "danger");
    }
  }

  function openPendingResult() {
    const item = store.pendingResults[0];
    if (!item) return;
    const guard = store.navigationGuard;
    if (guard && !guard()) return;
    store.setNavigationGuard(null);
    store.selectWork(item.workId);
    store.selectChapter(item.chapterNumber);
    store.setPage("writing");
    store.dismissPendingResult(item.id);
  }

  const pageLabel = pages.find((item) => item.key === store.page)?.label || "小说工作台";
  return (
    <div className={`app ${store.sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <aside className="app-sidebar">
        <div className="brand-row">
          <img className="brand-mark" src="./brand-logo.png" alt="Hi Story" />
          <div className="brand-copy"><strong>Hi Story</strong><span>长篇小说工作台</span></div>
          <button className="icon-button" onClick={store.toggleSidebar} title="折叠侧栏" aria-label="折叠侧栏"><Menu size={18} /></button>
        </div>
        <div className="sidebar-body">
          <div className="work-switcher">
            <select className="work-select" value={store.selectedWorkId || ""} title="切换作品；正在运行的任务会继续执行" onChange={(event) => store.selectWork(Number(event.target.value))} aria-label="切换作品">
              {!store.works.length && <option value="">暂无作品</option>}
              {store.works.map((work) => <option key={work.id} value={work.id}>{work.title || "未命名作品"}</option>)}
            </select>
            <ChevronDown size={16} />
          </div>
          <button className="btn new-work" disabled={Boolean(store.tasks.length) || creatingWork} onClick={createWork} title={store.tasks.length ? "请等待当前任务结束" : "新建作品"}><Plus size={17} /><span>{creatingWork ? "正在创建" : "新建作品"}</span></button>
          <div className="nav-label">创作流程</div>
          <nav className="main-nav">
            {pages.map(({ key, label, icon: Icon }) => (
              <button key={key} className={`nav-button ${store.page === key ? "active" : ""}`} onClick={() => store.setPage(key)} title={label}>
                <Icon size={18} /><span>{label}</span>
              </button>
            ))}
          </nav>
          <div className="sidebar-footer"><div className="service-line"><i className="service-dot" /><span>{health.isSuccess ? "本地服务已连接" : "正在连接本地服务"}</span></div></div>
        </div>
      </aside>
      <section className="app-main">
        <header className="topbar">
          <div className="topbar-title"><h1>{currentWork?.title || "未选择作品"}</h1><p>{pageLabel}{currentWork?.genre ? ` · ${currentWork.genre}` : ""}</p></div>
          <div className="topbar-actions">
            {store.tasks.map((task) => <div className="task-chip" key={task.id}><LoaderCircle className="spinner" size={15} /><span>{task.title} · {task.detail || stageLabel("", "执行中")} · {formatElapsed(Math.floor((Date.now() - task.startedAt) / 1000))}</span><button className="icon-button" onClick={() => stopTask(task)} title="停止任务"><CircleStop size={17} /></button></div>)}
            <button className="icon-button" disabled={Boolean(store.navigationGuard)} onClick={() => queryClient.invalidateQueries()} title={store.navigationGuard ? "请先保存当前修改" : "刷新当前数据"}><RefreshCw size={17} /></button>
            {store.pendingResults.length > 0 && <button className="pending-result-button" onClick={openPendingResult} title="打开最早一条待处理结果"><BookOpenText size={16} />待处理结果 {store.pendingResults.length}</button>}
          </div>
        </header>
        <main className="page-host">{children}</main>
      </section>
      <div className="toast-stack">
        {store.notices.map((notice) => <div className={`toast ${notice.tone}`} key={notice.id}><p>{notice.message}</p><button className="icon-button" onClick={() => store.dismissNotice(notice.id)} title="关闭"><X size={15} /></button></div>)}
      </div>
    </div>
  );
}

function formatElapsed(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return minutes ? `${minutes}分${String(rest).padStart(2, "0")}秒` : `${rest}秒`;
}

function stageLabel(stage?: string, detail?: string) {
  if (detail) return detail;
  const labels: Record<string, string> = { writing: "正在生成初稿", reviewing: "正在审稿", revising: "正在修订", validating: "正在验收", memory: "正在整理记忆" };
  return labels[String(stage || "")] || "正在处理";
}
