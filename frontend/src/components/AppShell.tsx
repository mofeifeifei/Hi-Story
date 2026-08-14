import { useEffect, useState, type ReactNode } from "react";
import {
  Archive, BookOpenText, ChevronDown, CircleStop, FileOutput, FolderPen, Library,
  LoaderCircle, Menu, Plus, RefreshCw, ScrollText, Settings, X,
} from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, cancelTask } from "../services/api";
import { useAppStore } from "../stores/appStore";
import type { PageKey, Work } from "../types";

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
  const [elapsed, setElapsed] = useState(0);
  const health = useQuery({ queryKey: ["health"], queryFn: () => api<Record<string, unknown>>("/api/health"), refetchInterval: 30_000 });
  const worksQuery = useQuery({ queryKey: ["works"], queryFn: () => api<{ works: Work[] }>("/api/works") });
  const currentWork = store.works.find((work) => Number(work.id) === Number(store.selectedWorkId));
  const taskQuery = useQuery({
    queryKey: ["task", store.task?.id],
    queryFn: () => api<{ stage?: string; detail?: string }>(`/api/tasks/${store.task!.id}`),
    enabled: Boolean(store.task),
    refetchInterval: store.task ? 1000 : false,
  });

  useEffect(() => {
    if (!worksQuery.data) return;
    store.setWorks(worksQuery.data.works || []);
    if (!store.selectedWorkId && worksQuery.data.works?.length) store.selectWork(worksQuery.data.works[0].id);
  }, [worksQuery.data]);

  useEffect(() => {
    if (!store.task) { setElapsed(0); return; }
    const update = () => setElapsed(Math.floor((Date.now() - store.task!.startedAt) / 1000));
    update();
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, [store.task]);

  async function createWork() {
    try {
      const data = await api<{ work: Work; works: Work[] }>("/api/works", {
        method: "POST",
        body: { title: "未命名作品", idea: "", genre: "", platform: "", target_words: 0, style: "" },
      });
      store.setWorks(data.works || [...store.works, data.work]);
      store.selectWork(data.work.id);
      store.setPage("project");
      queryClient.setQueryData(["works"], { works: data.works });
      store.notify("新作品已创建。", "success");
    } catch (error) { store.notify((error as Error).message, "danger"); }
  }

  async function stopTask() {
    if (!store.task) return;
    try { await cancelTask(store.task.id); } catch { /* The local abort still prevents a late UI write. */ }
    store.task.controller.abort();
    store.notify("已请求停止任务，模型请求可能需要片刻才会结束。", "warning");
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
            <select className="work-select" value={store.selectedWorkId || ""} onChange={(event) => store.selectWork(Number(event.target.value))} aria-label="切换作品">
              {!store.works.length && <option value="">暂无作品</option>}
              {store.works.map((work) => <option key={work.id} value={work.id}>{work.title || "未命名作品"}</option>)}
            </select>
            <ChevronDown size={16} />
          </div>
          <button className="btn new-work" onClick={createWork} title="新建作品"><Plus size={17} /><span>新建作品</span></button>
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
            {store.task && <div className="task-chip"><LoaderCircle className="spinner" size={15} /><span>{store.task.title} · {stageLabel(taskQuery.data?.stage, taskQuery.data?.detail)} · {formatElapsed(elapsed)}</span><button className="icon-button" onClick={stopTask} title="停止任务"><CircleStop size={17} /></button></div>}
            <button className="icon-button" onClick={() => queryClient.invalidateQueries()} title="刷新当前数据"><RefreshCw size={17} /></button>
            {store.pendingResults.length > 0 && <button className="pending-result-button" onClick={() => { const item = store.pendingResults[0]; store.selectWork(item.workId); store.selectChapter(item.chapterNumber); store.setPage("writing"); store.dismissPendingResult(item.id); }} title="打开最早一条待处理结果"><BookOpenText size={16} />待处理结果 {store.pendingResults.length}</button>}
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
