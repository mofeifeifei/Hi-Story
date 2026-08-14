import { useEffect, useState } from "react";
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
  const [scope, setScope] = useState("book");
  const [format, setFormat] = useState("txt");
  const [start, setStart] = useState(1);
  const [end, setEnd] = useState(1);
  const [chapter, setChapter] = useState(1);
  const [includeDraft, setIncludeDraft] = useState(false);
  const [result, setResult] = useState("");
  const state = useQuery({ queryKey: ["work", workId], queryFn: () => api<WorkState>(`/api/works/${workId}`), enabled: Boolean(workId) });
  const dir = useQuery({ queryKey: ["export-dir", workId], queryFn: () => api<Record<string, unknown>>(`/api/works/${workId}/export-dir`), enabled: Boolean(workId) });

  useEffect(() => {
    setEnd(state.data?.chapters?.length || 1);
    setChapter(store.selectedChapter || 1);
  }, [state.data?.chapters?.length, store.selectedChapter]);

  async function exportNow() {
    if (!workId) return;
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
    }
  }

  async function directory(action: "choose" | "open" | "reset") {
    if (!workId) return;
    try {
      await api(`/api/works/${workId}/export-dir/${action}`, { method: "POST" });
      queryClient.invalidateQueries({ queryKey: ["export-dir", workId] });
    } catch (error) { store.notify((error as Error).message, "danger"); }
  }

  if (!workId) return <div className="page"><PageHeader title="导出" /><EmptyState title="先选择一个作品" /></div>;
  return <div className="page">
    <PageHeader title="导出作品" description="导出前会校验章节连续性，发现空章会直接提示。" />
    <main className="export-page"><div className="content-width">
      <section className="form-section"><h3 className="section-title">导出范围</h3>
        <div className="form-grid three">
          <label className="field">范围<select value={scope} onChange={(e) => setScope(e.target.value)}><option value="book">整本作品</option><option value="range">章节范围</option><option value="chapter">单章</option></select></label>
          <label className="field">格式<select value={format} onChange={(e) => setFormat(e.target.value)}><option value="txt">TXT</option><option value="docx">DOCX</option></select></label>
          {scope === "chapter" ? <label className="field">章节<input type="number" min="1" value={chapter} onChange={(e) => setChapter(Number(e.target.value))} /></label> : <><label className="field">起始章节<input type="number" min="1" value={start} onChange={(e) => setStart(Number(e.target.value))} /></label><label className="field">结束章节<input type="number" min="1" value={end} onChange={(e) => setEnd(Number(e.target.value))} /></label></>}
        </div>
        <label className="check-field"><input type="checkbox" checked={includeDraft} onChange={(e) => setIncludeDraft(e.target.checked)} />允许使用草稿补齐空章节</label>
        <button className="btn primary export-action" onClick={exportNow}><FolderOpen size={16} />开始导出</button>
      </section>
      <section className="form-section"><h3 className="section-title">导出位置</h3><p className="path-line">{String(dir.data?.export_dir || "默认导出目录")}</p><div className="toolbar"><button className="btn" onClick={() => directory("choose")}><FolderOpen size={15} />选择目录</button><button className="btn" onClick={() => directory("open")}><FolderOpen size={15} />打开目录</button><button className="btn quiet" onClick={() => directory("reset")}><RotateCcw size={15} />恢复默认</button></div></section>
      {result && <pre className="export-result">{result}</pre>}
    </div></main>
  </div>;
}
