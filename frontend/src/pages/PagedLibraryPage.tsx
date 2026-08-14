import { useDeferredValue, useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Save, Search, Trash2 } from "lucide-react";
import { EmptyState } from "../components/EmptyState";
import { PageHeader } from "../components/PageHeader";
import { api } from "../services/api";
import { useAppStore } from "../stores/appStore";

type Item = Record<string, unknown>;
type PageData = { items: Item[]; page: number; page_size: number; total: number };
type FieldType = "text" | "number" | "area" | "check";
type Category = { label: string; title: (item: Item) => string; single?: boolean; fields: Array<[string, string, FieldType]> };

const categories: Record<string, Category> = {
  characters: { label: "人物", title: (x) => String(x.name || "未命名人物"), fields: [["name","姓名","text"],["role","定位","text"],["personality","性格","area"],["goal","目标","area"],["secret","秘密","area"],["speaking_style","说话风格","area"],["relationship","人物关系","area"],["current_goal","当前目标","area"],["current_fear","当前恐惧","area"],["current_state","当前状态","area"],["arc_stage","成长阶段","text"],["arc_notes","成长备注","area"]] },
  world_rules: { label: "世界规则", title: (x) => String(x.rule_name || "未命名规则"), fields: [["rule_name","规则名称","text"],["rule_content","规则内容","area"],["limitations","限制条件","area"],["forbidden_changes","禁止改动","area"]] },
  plot_threads: { label: "伏笔", title: (x) => String(x.content || "未命名伏笔"), fields: [["first_chapter","首次出现章节","number"],["content","伏笔内容","area"],["status","状态","text"],["planned_resolve_chapter","计划回收章节","number"],["actual_resolve_chapter","实际回收章节","number"]] },
  timeline: { label: "时间线", title: (x) => String(x.event || "未命名事件"), fields: [["chapter_number","章节","number"],["story_time","故事时间","text"],["event","事件","area"],["characters_involved","涉及人物","area"]] },
  historical_profile: { label: "历史设定卡", title: (x) => String(x.dynasty || x.period || "历史设定卡"), single: true, fields: [["dynasty","朝代","text"],["period","具体时期","text"],["year_range","年份范围","text"],["current_ruler","当前君主或政权","text"],["historical_stage","历史阶段","area"],["political_context","政局背景","area"],["official_system","官制总览","area"],["military_system","军制兵制","area"],["social_order","阶层与礼法","area"],["daily_life","衣食住行","area"],["currency","货币","area"],["geo_notes","地理与地名","area"],["language_style","语言风格","area"],["taboo_words","禁用现代词","area"],["fiction_boundary","虚构边界","area"],["locked_facts","不可改历史事实","area"],["source_notes","资料备注","area"]] },
  historical_facts: { label: "历史事实", title: (x) => String(x.name || x.content || "未命名历史事实"), fields: [["chapter_number","来源章节","number"],["category","分类","text"],["name","名称","text"],["content","事实内容","area"],["source_type","来源类型","text"],["certainty","可信度","text"],["fictionalized","是否虚构","check"],["chapter_impact","本章影响","area"],["future_constraint","后续约束","area"]] },
  chapter_notes: { label: "章节批注", title: (x) => `第 ${x.chapter_number || "?"} 章 · ${x.note_type || "批注"}`, fields: [["chapter_number","章节","number"],["note_type","批注类型","text"],["content","批注内容","area"]] },
};

export function LibraryPage() {
  const store = useAppStore();
  const queryClient = useQueryClient();
  const workId = store.selectedWorkId;
  const [kind, setKind] = useState("characters");
  const [selectedId, setSelectedId] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState<Item>({});
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search.trim());
  const [page, setPage] = useState(1);
  const [characterScope, setCharacterScope] = useState("valid");
  const pageSize = 50;
  const def = categories[kind];
  const countsQuery = useQuery({ queryKey: ["library-counts", workId], queryFn: () => api<Record<string, number>>(`/api/works/${workId}/library/counts`), enabled: Boolean(workId) });
  const pageQuery = useQuery({ queryKey: ["library-page", workId, kind, page, deferredSearch, characterScope], queryFn: () => api<PageData>(`/api/works/${workId}/library/${kind}/items?page=${page}&page_size=${pageSize}&q=${encodeURIComponent(deferredSearch)}&scope=${kind === "characters" ? characterScope : "valid"}`), enabled: Boolean(workId), placeholderData: (previous) => previous });
  const detailQuery = useQuery({ queryKey: ["library-item", workId, kind, selectedId], queryFn: () => api<Item>(`/api/works/${workId}/library/${kind}/items/${selectedId}`), enabled: Boolean(workId && typeof selectedId === "number" && !def.single) });

  useEffect(() => { setPage(1); setSelectedId(null); setDraft({}); }, [kind, deferredSearch, characterScope, workId]);
  useEffect(() => { if (def.single && pageQuery.data) setDraft(pageQuery.data.items[0] || {}); }, [def.single, pageQuery.data]);
  useEffect(() => { if (detailQuery.data) setDraft(detailQuery.data); }, [detailQuery.data]);

  async function refreshCategory() {
    await Promise.all([queryClient.invalidateQueries({ queryKey: ["library-page", workId, kind] }), queryClient.invalidateQueries({ queryKey: ["library-counts", workId] })]);
  }
  async function save() {
    if (!workId) return;
    try {
      const data = await api<{ id: number; item?: Item }>(`/api/works/${workId}/library/${kind}/item`, { method: "POST", body: draft });
      setSelectedId(def.single ? null : data.id); setDraft(data.item || { ...draft, id: data.id });
      await refreshCategory(); store.notify("资料已保存。", "success");
    } catch (error) { store.notify((error as Error).message, "danger"); }
  }
  async function remove() {
    if (!workId || !draft.id || def.single || !window.confirm("确定删除当前资料吗？")) return;
    try {
      await api(`/api/works/${workId}/library/${kind}/items/${draft.id}`, { method: "DELETE" });
      setSelectedId(null); setDraft({}); await refreshCategory(); store.notify("资料已删除。", "success");
    } catch (error) { store.notify((error as Error).message, "danger"); }
  }

  if (!workId) return <div className="page"><PageHeader title="资料库" /><EmptyState title="先选择一个作品" /></div>;
  const items = pageQuery.data?.items || [];
  const total = pageQuery.data?.total || 0;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const showEditor = def.single || selectedId === "new" || Boolean(selectedId);
  return <div className="page"><PageHeader title="资料库" description="分类按需加载，每页最多显示 50 条。" actions={<><button className="btn" disabled={def.single} onClick={() => { setSelectedId("new"); setDraft({}); }}><Plus size={16} />新增{def.label}</button><button className="btn primary" disabled={!showEditor} onClick={save}><Save size={16} />保存当前资料</button></>} />
    <div className="library-layout"><aside className="library-categories">{Object.entries(categories).map(([key, item]) => <button className={kind === key ? "active" : ""} key={key} onClick={() => setKind(key)}><span>{item.label}</span><strong>{countsQuery.data?.[key] ?? "-"}</strong></button>)}</aside>
      <aside className="library-list"><div className="rail-search"><div className="search-box"><Search size={16} /><input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={`搜索${def.label}`} disabled={def.single} /></div>{kind === "characters" && <select className="input library-scope" value={characterScope} onChange={(event) => setCharacterScope(event.target.value)} aria-label="人物范围"><option value="valid">全部有效人物</option><option value="auto">自动发现人物</option><option value="invalid">异常空记录（{countsQuery.data?.characters_invalid || 0}）</option></select>}</div><div className="library-items">{pageQuery.isLoading ? <p className="list-empty">正在加载...</p> : items.map((item) => { const id = Number(item.id || 0); return <button className={selectedId === id ? "active" : ""} key={id || kind} onClick={() => def.single ? setDraft(item) : setSelectedId(id)}><strong>{def.title(item)}</strong><small>{item.updated_at ? `最近修改：${String(item.updated_at)}` : def.label}</small></button>; })}{!pageQuery.isLoading && !items.length && <p className="list-empty">暂无资料</p>}</div>{totalPages > 1 && <div className="pager"><button className="btn small" disabled={page === 1} onClick={() => setPage(page - 1)}>上一页</button><span>{page} / {totalPages} · 共 {total} 条</span><button className="btn small" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</button></div>}</aside>
      <main className="library-editor">{showEditor ? detailQuery.isLoading ? <div className="loading-block">正在读取详情...</div> : <><div className="library-editor-head"><div><h3>{def.label}详情</h3><p>修改后点击保存，变更会立即写入作品数据库。</p></div>{!def.single && Boolean(draft.id) && <button className="btn danger" onClick={remove}><Trash2 size={15} />删除</button>}</div><div className="form-grid">{def.fields.map(([key, label, type]) => <LibraryField key={key} label={label} type={type} value={draft[key]} onChange={(value) => setDraft({ ...draft, [key]: value })} />)}</div></> : <EmptyState title={`选择一条${def.label}资料`} description="左侧列表用于定位，右侧只加载当前资料的完整字段。" />}</main></div>
  </div>;
}

function LibraryField({ label, type, value, onChange }: { label: string; type: FieldType; value: unknown; onChange: (value: unknown) => void }) {
  if (type === "check") return <label className="check-field"><input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />{label}</label>;
  return <label className={`field ${type === "area" ? "span-all" : ""}`}>{label}{type === "area" ? <textarea rows={4} value={String(value || "")} onChange={(e) => onChange(e.target.value)} /> : <input type={type} value={String(value ?? "")} onChange={(e) => onChange(type === "number" ? Number(e.target.value) : e.target.value)} />}</label>;
}
