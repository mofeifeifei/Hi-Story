import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { api } from "../services/api";
import { useAppStore } from "../stores/appStore";
import { formatTime, readable, recordTitle, statusText } from "../utils/format";

type RecordItem = Record<string, unknown> & { record_type?: string };
type RecordPage = { items: RecordItem[]; page: number; page_size: number; total: number };

export function RecordsPage() {
  const store = useAppStore();
  const queryClient = useQueryClient();
  const workId = store.selectedWorkId;
  const [filter, setFilter] = useState("all");
  const [open, setOpen] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const pageSize = 40;
  const kind = filter === "chapter" ? "all" : filter;
  const chapter = filter === "chapter" ? store.selectedChapter : null;
  const query = useQuery({ queryKey: ["records-page", workId, page, kind, chapter], queryFn: () => api<RecordPage>(`/api/works/${workId}/records-page?page=${page}&page_size=${pageSize}&kind=${encodeURIComponent(kind)}${chapter ? `&chapter_number=${chapter}` : ""}`), enabled: Boolean(workId) });
  useEffect(() => { setPage(1); setOpen(null); }, [workId, chapter]);
  if (!workId) return <div className="page"><PageHeader title="运行记录" /><EmptyState title="先选择一个作品" /></div>;
  const records = query.data?.items || [];
  const total = query.data?.total || 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  return <div className="page"><PageHeader title="运行记录" description="记录按时间倒序加载，错误默认收起，点击后查看详情。" actions={<><select className="input record-filter" value={filter} onChange={(event) => { setFilter(event.target.value); setPage(1); setOpen(null); }} aria-label="记录筛选"><option value="all">全部记录</option><option value="chapter">当前章节</option><option value="chapterOutlines">细纲生成</option><option value="revise">修订</option><option value="memory">记忆</option><option value="failed">失败记录</option></select><button className="icon-button" title="刷新记录" onClick={() => queryClient.invalidateQueries({ queryKey: ["records-page", workId] })}><RefreshCw size={17} /></button></>} />
    <main className="records-page"><div className="record-timeline">{query.isLoading ? <div className="loading-block">正在读取记录...</div> : records.map((record, index) => { const id = `${record.record_type || "record"}-${String(record.id || index)}`; const expanded = open === id; return <article className={`record-entry ${["failed", "error", "interrupted"].includes(String(record.status)) ? "failed" : ""}`} key={id}><div className="record-marker" /><div className="record-main"><button className="record-toggle" onClick={() => setOpen(expanded ? null : id)}>{expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}<span><strong>{recordTitle(record.title || record.kind)}</strong><small>{formatTime(record.created_at)}{record.chapter_number ? ` · 第 ${String(record.chapter_number)} 章` : ""}</small></span><em>{statusText(record.status)}</em></button>{expanded && <pre className="record-detail">{readable(recordDetail(record))}</pre>}</div></article>; })}{!query.isLoading && !records.length && <EmptyState title="暂无运行记录" description="生成正文、细纲或保存资料后，记录会出现在这里。" />}{totalPages > 1 && <div className="pager record-pager"><button className="btn small" disabled={page === 1} onClick={() => { setPage(page - 1); setOpen(null); }}>上一页</button><span>{page} / {totalPages} · 共 {total} 条</span><button className="btn small" disabled={page >= totalPages} onClick={() => { setPage(page + 1); setOpen(null); }}>下一页</button></div>}</div></main>
  </div>;
}

function recordDetail(record: RecordItem) {
  if (record.record_type !== "task") return record;
  const detail = { ...record };
  for (const key of ["agent_name", "model", "prompt_name", "estimated_input_tokens", "estimated_output_tokens", "estimated_total_tokens", "finish_reason", "input_chars", "output_chars"]) delete detail[key];
  return detail;
}
