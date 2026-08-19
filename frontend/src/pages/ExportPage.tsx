import { useEffect, useMemo, useRef, useState } from "react";
import { FolderOpen, RotateCcw } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { api } from "../services/api";
import { useAppStore } from "../stores/appStore";
import type { WorkState } from "../types";

export function ExportPage() {
  const store = useAppStore();
  const queryClient = useQueryClient();
  const workId = store.selectedWorkId;
  const workTask = store.tasks.some((task) => Number(task.workId || 0) === Number(workId));
  const [scope, setScope] = useState("book");
  const [format, setFormat] = useState("txt");
  const [start, setStart] = useState(1);
  const [end, setEnd] = useState(1);
  const [chapter, setChapter] = useState(1);
  const [includeDraft, setIncludeDraft] = useState(false);
  const [result, setResult] = useState("");
  const [pendingAction, setPendingAction] = useState<"export" | "choose" | "open" | "reset" | null>(null);
  const initializedWork = useRef<number | null>(null);
  const state = useQuery({ queryKey: ["work", workId], queryFn: () => api<WorkState>(`/api/works/${workId}/summary`), enabled: Boolean(workId) });
  const dir = useQuery({ queryKey: ["export-dir", workId], queryFn: () => api<Record<string, unknown>>(`/api/works/${workId}/export-dir`), enabled: Boolean(workId) });
  const chapterNumbers = useMemo(() => (state.data?.chapters || state.data?.outline?.chapters || []).map((item) => Number(item.chapter_number)).filter((item) => Number.isFinite(item) && item > 0).sort((a, b) => a - b), [state.data?.chapters, state.data?.outline?.chapters]);
  const chapterKey = chapterNumbers.join(",");

  useEffect(() => {
    if (!workId || !chapterNumbers.length || initializedWork.current === Number(workId)) return;
    initializedWork.current = Number(workId);
    setStart(chapterNumbers[0]);
    setEnd(chapterNumbers[chapterNumbers.length - 1]);
    setChapter(store.selectedChapter && chapterNumbers.includes(Number(store.selectedChapter)) ? Number(store.selectedChapter) : chapterNumbers[0]);
    setResult("");
  }, [workId, chapterKey]);
  useEffect(() => { if (store.selectedChapter) setChapter(Number(store.selectedChapter)); }, [store.selectedChapter]);

  async function exportNow() {
    if (!workId || pendingAction || workTask) {
      if (workTask && !pendingAction) store.notify("当前作品仍有任务运行，暂时不能导出。", "warning");
      return;
    }
    if (scope === "range" && start > end) {
      store.notify("起始章节不能大于结束章节。", "warning");
      return;
    }
    setPendingAction("export");
    try {
      const data = await api<{ path: string }>(`/api/works/${workId}/export`, {
        method: "POST",
        body: { scope, format, chapter_number: chapter, start_chapter: start, end_chapter: end, include_draft: includeDraft },
      });
      setResult(`导出完成\n${data.path}`);
      store.notify("导出完成。", "success");
    } catch (error) {
      setResult((error as Error).message);
      store.notify((error as Error).message, "danger");
    } finally { setPendingAction(null); }
  }

  async function directory(action: "choose" | "open" | "reset") {
    if (!workId || pendingAction || workTask) {
      if (workTask && !pendingAction) store.notify("当前作品仍有任务运行，暂时不能操作导出目录。", "warning");
      return;
    }
    setPendingAction(action);
    try {
      await api(`/api/works/${workId}/export-dir/${action}`, { method: "POST" });
      await queryClient.invalidateQueries({ queryKey: ["export-dir", workId] });
    } catch (error) { store.notify((error as Error).message, "danger"); }
    finally { setPendingAction(null); }
  }

  if (!workId) return <div className="page"><PageHeader title="导出" /><EmptyState title="先选择一个作品" /></div>;
  return <div className="page">
    <PageHeader title="导出作品" description="导出前会校验章节连续性，发现空章会直接提示。" />
    <main className="export-page"><div className="content-width">
      <section className="form-section"><h3 className="section-title">导出范围</h3>
        <div className="form-grid three">
          <label className="field">范围<select value={scope} onChange={(e) => setScope(e.target.value)}><option value="book">整本作品</option><option value="range">章节范围</option><option value="chapter">单章</option></select></label>
          <label className="field">格式<select value={format} onChange={(e) => setFormat(e.target.value)}><option value="txt">TXT</option><option value="docx">DOCX</option></select></label>
          {scope === "chapter" && <label className="field">章节<input type="number" min="1" value={chapter} onChange={(e) => setChapter(Number(e.target.value))} /></label>}
          {scope === "range" && <><label className="field">起始章节<input type="number" min="1" value={start} onChange={(e) => setStart(Number(e.target.value))} /></label><label className="field">结束章节<input type="number" min="1" value={end} onChange={(e) => setEnd(Number(e.target.value))} /></label></>}
        </div>
        <label className="check-field"><input type="checkbox" checked={includeDraft} onChange={(e) => setIncludeDraft(e.target.checked)} />允许使用草稿补齐空章节</label>
        <button className="btn primary export-action" disabled={Boolean(pendingAction) || workTask} onClick={exportNow}><FolderOpen size={16} />{pendingAction === "export" ? "正在导出" : "开始导出"}</button>
      </section>
      <section className="form-section"><h3 className="section-title">导出位置</h3><p className="path-line">{String(dir.data?.export_dir || "默认导出目录")}</p><div className="toolbar"><button className="btn" disabled={Boolean(pendingAction) || workTask} onClick={() => directory("choose")}><FolderOpen size={15} />{pendingAction === "choose" ? "正在选择" : "选择目录"}</button><button className="btn" disabled={Boolean(pendingAction) || workTask} onClick={() => directory("open")}><FolderOpen size={15} />{pendingAction === "open" ? "正在打开" : "打开目录"}</button><button className="btn quiet" disabled={Boolean(pendingAction) || workTask} onClick={() => directory("reset")}><RotateCcw size={15} />{pendingAction === "reset" ? "正在恢复" : "恢复默认"}</button></div></section>
      {result && <pre className="export-result">{result}</pre>}
    </div></main>
  </div>;
}
