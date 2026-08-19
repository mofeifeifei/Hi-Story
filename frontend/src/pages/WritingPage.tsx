import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Copy, Eye, FileClock, MoreHorizontal, PanelRightClose, PanelRightOpen, Play, Save, Search, Sparkles, Trash2, X } from "lucide-react";
import { api, createTaskId } from "../services/api";
import { useAppStore } from "../stores/appStore";
import type { Chapter, ChapterSummary, OutlineState, WorkState } from "../types";
import { readable, safeJson, statusText, wordCount } from "../utils/format";
import { PageHeader } from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";
import { readNumberList, readScroll, writeNumberList, writeScroll } from "../utils/workspaceState";

type InspectorTab = "task" | "continuity" | "revision" | "memory" | "versions";
interface ChapterState { chapter: Chapter; review?: Record<string, unknown>; review_readable?: string; candidate_versions?: Array<Record<string, unknown>>; outline_readable?: string; memory_readable?: string; chapter_word_target?: Record<string, unknown>; }
interface RevisionAdvice { target: string; evidence: string; action: string; keep: string; avoid: string; }

export function WritingPage() {
  const store = useAppStore();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<number[]>([]);
  const [title, setTitle] = useState("");
  const [dirty, setDirty] = useState(false);
  const [savedAt, setSavedAt] = useState("");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("task");
  const [instruction, setInstruction] = useState("");
  const [context, setContext] = useState<Record<string, unknown> | null>(null);
  const [contextReadable, setContextReadable] = useState("");
  const [loadingContext, setLoadingContext] = useState(false);
  const [mode, setMode] = useState("standard");
  const [candidateText, setCandidateText] = useState<string | null>(null);
  const [candidateReview, setCandidateReview] = useState<Record<string, unknown> | null>(null);
  const [candidateBlockers, setCandidateBlockers] = useState<string[]>([]);
  const [previewCandidate, setPreviewCandidate] = useState<{ text: string; label: string } | null>(null);
  const editorScroll = useRef<HTMLDivElement>(null);
  const loadingChapter = useRef(false);
  const suppressScrollSave = useRef(false);
  const scrollOwner = useRef<{ workId: number; chapterNumber: number } | null>(null);
  const restoreTimer = useRef<number | null>(null);
  const contextRequest = useRef<AbortController | null>(null);

  const workState = useQuery({
    queryKey: ["work", store.selectedWorkId],
    queryFn: () => api<WorkState>(`/api/works/${store.selectedWorkId}/summary`),
    enabled: Boolean(store.selectedWorkId),
  });
  const outline: OutlineState = workState.data?.outline || { full_outline: "", volume_outline: [], chapters: [] };
  const chapters = outline.chapters || [];

  const chapterState = useQuery({
    queryKey: ["chapter", store.selectedWorkId, store.selectedChapter],
    queryFn: ({ signal }) => api<ChapterState>(`/api/works/${store.selectedWorkId}/chapters/${store.selectedChapter}`, { signal }),
    enabled: Boolean(store.selectedWorkId && store.selectedChapter),
  });

  const editor = useEditor({
    extensions: [StarterKit.configure({ heading: false, blockquote: false, code: false, codeBlock: false, bulletList: false, orderedList: false, horizontalRule: false }), Placeholder.configure({ placeholder: "在这里开始写正文，或根据细纲生成本章。" })],
    content: "",
    editorProps: { attributes: { class: "manuscript-editor", spellcheck: "false" }, transformPastedHTML: (html) => html.replace(/<[^>]*>/g, "") },
    onUpdate: () => { if (!loadingChapter.current) { setDirty(true); saveLocalDraft(); } },
  });

  useEffect(() => {
    if (!chapters.length || store.selectedChapter) return;
    store.selectChapter(Number(chapters[0].chapter_number));
  }, [chapters.length, store.selectedChapter]);

  useLayoutEffect(() => {
    const workId = Number(store.selectedWorkId);
    const chapterNumber = Number(store.selectedChapter);
    const previous = scrollOwner.current;
    if (previous && editorScroll.current && !loadingChapter.current && !suppressScrollSave.current) {
      writeScroll(scrollKey(previous.chapterNumber, previous.workId), editorScroll.current.scrollTop);
    }
    if (!workId || !chapterNumber) {
      scrollOwner.current = null;
      return;
    }
    if (restoreTimer.current !== null) window.clearTimeout(restoreTimer.current);
    loadingChapter.current = true;
    suppressScrollSave.current = true;
    scrollOwner.current = { workId, chapterNumber };
    if (editorScroll.current) {
      editorScroll.current.scrollTop = readScroll(scrollKey(chapterNumber, workId));
    }
  }, [store.selectedWorkId, store.selectedChapter]);

  useEffect(() => {
    if (!chapterState.data?.chapter || !editor) return;
    const chapter = chapterState.data.chapter;
    const targetWorkId = Number(store.selectedWorkId);
    const targetChapter = Number(chapter.chapter_number);
    if (restoreTimer.current !== null) window.clearTimeout(restoreTimer.current);
    loadingChapter.current = true;
    setTitle(chapter.title || "");
    const text = chapter.status === "problem_draft" ? chapter.draft || chapter.final_text || "" : chapter.final_text || chapter.draft || "";
    editor.commands.setContent(textToHtml(text), { emitUpdate: false });
    setDirty(false);
    setCandidateText(null);
    setCandidateReview(null);
    setCandidateBlockers([]);
    setInstruction("");
    setContext(null);
    setContextReadable("");
    restoreTimer.current = window.setTimeout(() => {
      const current = useAppStore.getState();
      if (Number(current.selectedWorkId) !== targetWorkId || Number(current.selectedChapter) !== targetChapter) return;
      restoreLocalDraft(chapter, targetWorkId);
      restoreScroll(targetWorkId, targetChapter);
      loadingChapter.current = false;
      suppressScrollSave.current = false;
      restoreTimer.current = null;
    }, 0);
    return () => {
      if (restoreTimer.current !== null) window.clearTimeout(restoreTimer.current);
      restoreTimer.current = null;
    };
  }, [chapterState.data?.chapter.id, chapterState.data?.chapter.updated_at, editor]);

  useEffect(() => () => {
    const owner = scrollOwner.current;
    if (owner && editorScroll.current) {
      writeScroll(scrollKey(owner.chapterNumber, owner.workId), editorScroll.current.scrollTop);
    }
  }, []);
  useEffect(() => { store.setNavigationGuard(dirty ? () => window.confirm("当前正文有未保存修改。确定离开当前页面吗？") : null); return () => store.setNavigationGuard(null); }, [dirty]);

  function plainText() { return editor?.getText({ blockSeparator: "\n\n" }) || ""; }
  function draftKey(chapterNumber = store.selectedChapter, workId = store.selectedWorkId) { return `hi-story:draft:${workId}:${chapterNumber}`; }
  function scrollKey(chapterNumber: number, workId: number) { return `hi-story:scroll:v2:${workId}:${chapterNumber}`; }
  function expandedKey() { return `hi-story:writing-expanded:${store.selectedWorkId}`; }
  function saveLocalDraft(nextTitle = title) {
    if (!editor || !store.selectedChapter) return;
    try { localStorage.setItem(draftKey(), JSON.stringify({ text: plainText(), title: nextTitle, updatedAt: chapterState.data?.chapter.updated_at || "", savedAt: Date.now() })); } catch { /* Browser storage can be disabled. */ }
  }
  function restoreLocalDraft(chapter: Chapter, workId: number) {
    try {
      const draft = JSON.parse(localStorage.getItem(draftKey(chapter.chapter_number, workId)) || "null");
      if (!draft || typeof draft.text !== "string" || draft.text === plainText()) return;
      if (window.confirm(`第 ${chapter.chapter_number} 章有一份尚未保存的本地草稿，是否恢复？`)) {
        loadingChapter.current = true;
        editor?.commands.setContent(textToHtml(draft.text), { emitUpdate: false });
        setTitle(draft.title || chapter.title || "");
        setDirty(true);
        loadingChapter.current = false;
      } else localStorage.removeItem(draftKey(chapter.chapter_number, workId));
    } catch { /* Ignore malformed local data. */ }
  }
  function saveScroll() {
    const owner = scrollOwner.current;
    if (!owner || !editorScroll.current || loadingChapter.current || suppressScrollSave.current) return;
    writeScroll(scrollKey(owner.chapterNumber, owner.workId), editorScroll.current.scrollTop);
  }
  function restoreScroll(workId: number, chapterNumber: number) {
    if (!editorScroll.current) return;
    editorScroll.current.scrollTop = readScroll(scrollKey(chapterNumber, workId));
  }

  async function chooseChapter(number: number) {
    if (number === store.selectedChapter) return;
    if (dirty && !window.confirm("当前章节有未保存修改。切换后仍会保留本地草稿，确定继续吗？")) return;
    const owner = scrollOwner.current;
    if (owner && editorScroll.current) {
      writeScroll(scrollKey(owner.chapterNumber, owner.workId), editorScroll.current.scrollTop);
    }
    store.selectChapter(number);
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      const chapter = chapterState.data!.chapter;
      const target = { workId: Number(store.selectedWorkId), chapterNumber: Number(chapter.chapter_number) };
      const data = await api<ChapterState>(`/api/works/${target.workId}/chapters/${target.chapterNumber}`, {
        method: "PUT",
        body: { chapter_id: chapter.id, updated_at: chapter.updated_at, revision: Number(chapter.revision || 0), title: title.trim(), final_text: plainText(), invalidate_memory: plainText() !== String(chapter.final_text || "") },
      });
      return { data, target };
    },
    onSuccess: ({ data, target }) => {
      queryClient.setQueryData(["chapter", target.workId, target.chapterNumber], data);
      queryClient.invalidateQueries({ queryKey: ["work", target.workId] });
      localStorage.removeItem(draftKey(target.chapterNumber, target.workId));
      const stillActive = Number(useAppStore.getState().selectedWorkId) === target.workId && Number(useAppStore.getState().selectedChapter) === target.chapterNumber;
      if (!stillActive) {
        store.addPendingResult({ workId: target.workId, chapterNumber: target.chapterNumber, title: "最终稿保存完成", detail: `第 ${target.chapterNumber} 章已保存。` });
        return;
      }
      setCandidateText(null); setCandidateReview(null); setCandidateBlockers([]); setDirty(false); setSavedAt(new Date().toLocaleTimeString("zh-CN", { hour12: false, hour: "2-digit", minute: "2-digit" }));
      const gate = (data as any).quality_gate?.manual || {};
      const issueCount = [...(gate.blockers || []), ...(gate.warnings || [])].length;
      const alreadySaved = Boolean((data as any).quality_gate?.already_saved);
      store.notify(
        alreadySaved ? "当前内容已经保存。" : issueCount ? `最终稿已保存，仍有 ${issueCount} 项质量提醒。` : "最终稿已保存。",
        issueCount ? "warning" : "success",
      );
    },
    onError: (error) => store.notify((error as Error).message, "danger"),
  });

  async function runTask(kind: "chapter" | "revise" | "memory") {
    const chapter = chapterState.data?.chapter;
    const chapterTask = store.tasks.some((task) => Number(task.workId || 0) === Number(store.selectedWorkId) && Number(task.chapterNumber || 0) === Number(chapter?.chapter_number));
    if (!chapter || chapterTask) {
      if (chapterTask) store.notify("当前章节已有任务运行，请等待完成或先停止任务。", "warning");
      return;
    }
    const taskWorkId = Number(store.selectedWorkId);
    if (kind !== "chapter" && dirty && !window.confirm("当前修改尚未保存。修订和记忆将以编辑区当前内容为准，确定继续吗？")) return;
    if (kind === "revise" && !instruction.trim()) { store.notify("请先填写明确的修改要求。", "warning"); return; }
    const taskId = createTaskId(kind);
    const controller = new AbortController();
    store.setTask({ id: taskId, kind, title: kind === "chapter" ? `生成第 ${chapter.chapter_number} 章` : kind === "revise" ? `修订第 ${chapter.chapter_number} 章` : `整理第 ${chapter.chapter_number} 章记忆`, detail: "", startedAt: Date.now(), controller, workId: taskWorkId, chapterNumber: chapter.chapter_number });
    try {
      let data: any;
      if (kind === "chapter") data = await api(`/api/works/${taskWorkId}/chapters/${chapter.chapter_number}/generate`, { method: "POST", signal: controller.signal, body: { task_id: taskId, mode, do_memory: false } });
      if (kind === "revise") data = await api(`/api/works/${taskWorkId}/chapters/${chapter.chapter_number}/revise`, { method: "POST", signal: controller.signal, body: { task_id: taskId, instruction: instruction.trim(), current_text: plainText(), chapter_id: chapter.id, updated_at: chapter.updated_at, revision: Number(chapter.revision || 0) } });
      if (kind === "memory") data = await api(`/api/works/${taskWorkId}/chapters/${chapter.chapter_number}/memory`, { method: "POST", signal: controller.signal, body: { task_id: taskId, chapter_id: chapter.id, updated_at: chapter.updated_at, revision: Number(chapter.revision || 0) } });
      const current = useAppStore.getState();
      const targetStillActive = current.page === "writing" && Number(current.selectedWorkId) === taskWorkId && Number(current.selectedChapter) === Number(chapter.chapter_number);
      if (kind === "revise" && targetStillActive) {
        setInstruction("");
      }
      if (kind === "revise" && data.candidate_only && data.revised_text && targetStillActive) {
        setCandidateText(data.revised_text);
        setCandidateReview(data.review || null);
        setCandidateBlockers((data.quality_blockers || []).map((item: unknown) => String(item)));
        setInspectorTab("revision");
        queryClient.invalidateQueries({ queryKey: ["chapter", taskWorkId, chapter.chapter_number] });
        store.notify(data.message || "修订稿已保存到候选版本，当前编辑器正文未被替换。", "warning");
      } else {
        if (kind === "revise" && targetStillActive) {
          setCandidateText(null);
          setCandidateReview(null);
          setCandidateBlockers([]);
        }
        queryClient.setQueryData(["chapter", taskWorkId, chapter.chapter_number], data);
        queryClient.invalidateQueries({ queryKey: ["chapter", taskWorkId, chapter.chapter_number] });
        queryClient.invalidateQueries({ queryKey: ["work", taskWorkId] });
        if (targetStillActive) {
          setDirty(false);
          if (kind === "memory") {
            localStorage.removeItem(draftKey(chapter.chapter_number, taskWorkId));
            setCandidateText(null);
          }
        }
        if (targetStillActive) store.notify(kind === "memory" ? "章节记忆已入库。" : kind === "revise" ? (data.candidate_only ? "修订稿已保存为候选版本。" : "正文已修订。") : "正文生成完成。", data.candidate_only ? "warning" : "success");
      }
      if (!targetStillActive) {
        current.addPendingResult({ workId: taskWorkId, chapterNumber: chapter.chapter_number, title: kind === "memory" ? "记忆整理完成" : kind === "revise" ? "修订完成" : "正文生成完成", detail: `第 ${chapter.chapter_number} 章已有新结果。` });
      }
    } catch (error) {
      if ((error as Error).name !== "AbortError") store.notify((error as Error).message, "danger");
    } finally { useAppStore.getState().removeTask(taskId); }
  }

  async function loadContext(targetWorkId: number, targetChapter: number) {
    contextRequest.current?.abort();
    const controller = new AbortController();
    contextRequest.current = controller;
    setLoadingContext(true);
    try {
      const data = await api<any>(`/api/works/${targetWorkId}/chapters/${targetChapter}/context`, { signal: controller.signal });
      const current = useAppStore.getState();
      if (Number(current.selectedWorkId) !== targetWorkId || Number(current.selectedChapter) !== targetChapter) return;
      setContext(data.context || {}); setContextReadable(data.context_error ? `上下文构建失败：${data.context_error}` : data.context_readable || "");
    } catch (error) { if ((error as Error).name !== "AbortError") store.notify((error as Error).message, "danger"); }
    finally { if (contextRequest.current === controller) { contextRequest.current = null; setLoadingContext(false); } }
  }

  useEffect(() => {
    contextRequest.current?.abort();
    setContext(null); setContextReadable(""); setLoadingContext(false);
    if (inspectorTab === "continuity" && store.selectedWorkId && store.selectedChapter) {
      loadContext(Number(store.selectedWorkId), Number(store.selectedChapter));
    }
    return () => contextRequest.current?.abort();
  }, [inspectorTab, store.selectedWorkId, store.selectedChapter]);

  const grouped = useMemo(() => groupChapters(chapters, outline.volume_outline, search), [chapters, outline.volume_outline, search]);
  useEffect(() => {
    if (!store.selectedWorkId || !grouped.length) return;
    const saved = readNumberList(expandedKey());
    setExpanded(saved === null ? grouped.map((group) => group.number) : saved);
  }, [store.selectedWorkId, Boolean(grouped.length)]);
  function toggleWritingVolume(number: number) {
    const next = expanded.includes(number) ? expanded.filter((item) => item !== number) : [...expanded, number];
    setExpanded(next); writeNumberList(expandedKey(), next);
  }
  const chapter = chapterState.data?.chapter;
  const workTask = store.tasks.some((task) => Number(task.workId || 0) === Number(store.selectedWorkId));
  const chapterTask = store.tasks.some((task) => Number(task.workId || 0) === Number(store.selectedWorkId) && Number(task.chapterNumber || 0) === Number(chapter?.chapter_number));
  const activeReview = dirty ? undefined : candidateReview || chapterState.data?.review;
  const revisionAdvice = useMemo(() => revisionAdviceFrom(activeReview), [activeReview]);
  const visibleRevisionAdvice = revisionAdvice;
  const revisionCopyText = useMemo(() => formatRevisionCopy(visibleRevisionAdvice), [visibleRevisionAdvice]);
  const versions = chapterState.data?.candidate_versions || [];
  const visibleVersions = versions.filter((version) => !candidateText || String(version.content || "").trim() !== candidateText.trim());
  const canSaveFinal = Boolean(
    chapter
    && plainText().trim()
    && !saveMutation.isPending
    && !workTask
  );
  const canGenerateMemory = Boolean(
    chapter
    && String(chapter.final_text || chapter.draft || "").trim()
    && !dirty
    && !chapterTask
  );

  async function copyRevisionText() {
    if (!revisionCopyText.trim()) {
      store.notify("当前正文没有可复制的修订建议。", "warning");
      return;
    }
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(revisionCopyText);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = revisionCopyText;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        const copied = document.execCommand("copy");
        textarea.remove();
        if (!copied) throw new Error("浏览器拒绝了复制操作");
      }
      store.notify(`已复制 ${visibleRevisionAdvice.length} 条修改建议。`, "success");
    } catch {
      store.notify("复制失败，请选中修订建议后手动复制。", "danger");
    }
  }

  function loadCandidate(text: string, notify = true) {
    if (workTask) {
      store.notify("当前作品仍有任务运行，暂时不能载入候选稿。", "warning");
      return;
    }
    loadingChapter.current = true;
    editor?.commands.setContent(textToHtml(text), { emitUpdate: false });
    setDirty(true);
    loadingChapter.current = false;
    setPreviewCandidate(null);
    if (notify) store.notify("候选稿已载入编辑器，确认后可保存为最终稿。", "info");
  }

  function promoteCandidate(text: string) {
    if (workTask || saveMutation.isPending) return;
    if (candidateText === text && candidateBlockers.length) {
      const summary = candidateBlockers.slice(0, 3).map((item) => `- ${item}`).join("\n");
      if (!window.confirm(`这份候选稿仍有 ${candidateBlockers.length} 项问题：\n${summary}\n\n仍要保存为最终稿吗？`)) return;
    }
    loadingChapter.current = true;
    editor?.commands.setContent(textToHtml(text), { emitUpdate: false });
    setDirty(true);
    loadingChapter.current = false;
    setPreviewCandidate(null);
    window.setTimeout(() => saveMutation.mutate(), 0);
  }

  async function deleteCandidate(versionId: unknown) {
    if (!chapter || !versionId || workTask || !window.confirm("确定删除这份候选稿吗？此操作无法撤销。")) return;
    try {
      await api(`/api/works/${store.selectedWorkId}/chapters/${chapter.chapter_number}/versions/${versionId}`, { method: "DELETE" });
      await queryClient.invalidateQueries({ queryKey: ["chapter", store.selectedWorkId, chapter.chapter_number] });
      store.notify("候选稿已删除。", "success");
    } catch (error) { store.notify((error as Error).message, "danger"); }
  }

  async function deleteChapterRange(fromCurrent: boolean) {
    if (!chapter || !store.selectedWorkId || workTask) return;
    const message = fromCurrent
      ? `确定删除第 ${chapter.chapter_number} 章及之后的全部章节吗？正文、细纲和记忆都会删除，此操作无法撤销。`
      : `确定删除第 ${chapter.chapter_number} 章吗？正文、细纲和记忆都会删除，此操作无法撤销。`;
    if (!window.confirm(message)) return;
    try {
      const suffix = fromCurrent ? "/delete-from" : "";
      const data = await api<WorkState & { deleted_count?: number }>(`/api/works/${store.selectedWorkId}/chapters/${chapter.chapter_number}${suffix}`, {
        method: "DELETE",
        body: { chapter_id: chapter.id, updated_at: chapter.updated_at, revision: Number(chapter.revision || 0) },
      });
      queryClient.setQueryData(["work", store.selectedWorkId], data);
      queryClient.removeQueries({ queryKey: ["chapter", store.selectedWorkId] });
      const remaining = data.outline?.chapters || data.chapters || [];
      const next = [...remaining].sort((a, b) => Number(a.chapter_number) - Number(b.chapter_number)).find((item) => Number(item.chapter_number) >= chapter.chapter_number)
        || [...remaining].sort((a, b) => Number(b.chapter_number) - Number(a.chapter_number))[0];
      store.selectChapter(next ? Number(next.chapter_number) : null);
      setDirty(false); localStorage.removeItem(draftKey(chapter.chapter_number, Number(store.selectedWorkId)));
      store.notify(fromCurrent ? `已删除 ${Number(data.deleted_count || 0)} 章。` : `第 ${chapter.chapter_number} 章已删除。`, "success");
    } catch (error) { store.notify((error as Error).message, "danger"); }
  }
  if (!store.selectedWorkId) return <div className="page"><PageHeader title="正文写作" /><EmptyState title="先选择一个作品" description="新建或选择作品后，章节和正文编辑器会显示在这里。" /></div>;

  return <div className="page">
    <PageHeader title="正文写作" description="章节独立加载，本地草稿与阅读位置自动保留。" actions={<>
      <select className="input" style={{ width: 116 }} value={mode} onChange={(event) => setMode(event.target.value)} aria-label="生成方式"><option value="standard">正式生成</option><option value="fast">快速试稿</option></select>
      <button className="btn primary" disabled={!chapter || chapterTask} onClick={() => runTask("chapter")}><Sparkles size={17} />生成正文</button>
      <button className="btn" disabled={!canSaveFinal} onClick={() => saveMutation.mutate()}><Save size={16} />保存最终稿</button>
      <button className="btn" disabled={!canGenerateMemory} title={canGenerateMemory ? "根据当前稿生成记忆；问题稿会先保存为最终稿" : "当前章节没有可用正文"} onClick={() => runTask("memory")}><FileClock size={16} />记忆入库</button>
      <button className="icon-button" onClick={store.toggleInspector} title={store.inspectorOpen ? "收起辅助面板" : "展开辅助面板"}>{store.inspectorOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}</button>
      <details className="button-menu"><summary className="icon-button" title="更多操作"><MoreHorizontal size={18} /></summary><div className="menu-popover"><button className="btn danger" onClick={() => clearChapter(store.selectedWorkId!, chapter!, queryClient, store.notify, () => { localStorage.removeItem(draftKey(chapter!.chapter_number)); setDirty(false); })} disabled={!chapter || workTask}><Trash2 size={15} />清空本章正文</button><button className="btn danger" onClick={() => deleteChapterRange(false)} disabled={!chapter || workTask}><Trash2 size={15} />删除当前章节</button><button className="btn danger" onClick={() => deleteChapterRange(true)} disabled={!chapter || workTask}><Trash2 size={15} />删除本章及之后</button></div></details>
    </>} />
    <div className={`writing-shell ${store.inspectorOpen ? "" : "inspector-closed"}`}>
      <aside className="chapter-rail"><div className="rail-search"><div className="search-box"><Search size={16} /><input className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索章节" /></div></div><div className="chapter-list">
        {grouped.map((group) => <div className="volume-group" key={group.number}><button className="volume-heading" onClick={() => toggleWritingVolume(group.number)}>{expanded.includes(group.number) ? <ChevronDown size={14} /> : <ChevronRight size={14} />}第 {group.number} 卷 · {group.title}</button>{expanded.includes(group.number) && group.chapters.map((item) => <button className={`chapter-row ${Number(item.chapter_number) === Number(store.selectedChapter) ? "active" : ""}`} key={item.chapter_number} onClick={() => chooseChapter(Number(item.chapter_number))}><span><strong>第 {item.chapter_number} 章 · {item.title || "未命名"}</strong><small>{statusText(item.status)}</small></span><i className={`chapter-status-dot ${item.status || ""}`} /></button>)}</div>)}
      </div></aside>
      <section className="editor-column">{chapterState.isLoading ? <div className="loading-block">正在载入章节...</div> : chapter ? <>
        <div className="editor-toolbar"><span className="chapter-number">第 {chapter.chapter_number} 章</span><input className="title-input" value={title} onChange={(event) => { const nextTitle = event.target.value; setTitle(nextTitle); setDirty(true); saveLocalDraft(nextTitle); }} placeholder="章节标题" /><span className={`status-badge ${chapter.status || ""}`}>{statusText(chapter.status)}</span></div>
        <div className="editor-scroll" ref={editorScroll} onScroll={saveScroll}><div className="manuscript-wrap"><EditorContent editor={editor} /></div></div>
        <div className="editor-status"><span className={dirty ? "dirty" : "saved"}>{dirty ? "有未保存修改" : savedAt ? `${savedAt} 已保存` : "已同步"}</span><span>第 {Number(chapter.revision || 0)} 版</span><span>{wordCount(plainText()).toLocaleString()} 字</span><span>记忆：{String(chapter.memory_json || "").trim() ? "已入库" : "未入库"}</span></div>
      </> : <EmptyState title="选择一章开始写作" description="左侧会按分卷展示所有已有细纲的章节。" />}</section>
      <aside className="inspector"><div className="inspector-tabs">{([['task','本章任务'],['continuity','上下章衔接'],['revision','修订'],['memory','记忆'],['versions','候选版本']] as Array<[InspectorTab,string]>).map(([key,label]) => <button key={key} className={inspectorTab === key ? "active" : ""} onClick={() => setInspectorTab(key)}>{label}</button>)}<button className="inspector-close" onClick={store.toggleInspector} title="关闭辅助面板"><X size={16} /></button></div><div className="inspector-content">
        {inspectorTab === "task" && <><h3>本章任务</h3><pre className="readable">{chapter ? taskText(chapter, chapterState.data?.outline_readable) : "未载入章节。"}</pre></>}
        {inspectorTab === "continuity" && <><h3>上下章衔接</h3><pre className="readable">{loadingContext ? "正在构建本章上下文..." : contextReadable || readable(context)}</pre></>}
        {inspectorTab === "revision" && <div className="revision-box"><h3>修订建议</h3>{candidateText && <p className="candidate-warning">当前显示的是候选稿复审结果。候选稿未覆盖编辑器正文。</p>}{visibleRevisionAdvice.length ? <div className="revision-advice-list">{visibleRevisionAdvice.map((item, index) => <section className="revision-advice-item" key={`${index}-${item.target}-${item.action}`}><div className="revision-advice-head"><span>{index + 1}</span><strong>{item.target || item.evidence || "本章相关段落"}</strong></div><p><b>修改：</b>{item.action}</p></section>)}</div> : <p className="revision-empty">当前正文没有可用的修订建议。</p>}<button className="btn" disabled={!revisionCopyText.trim()} onClick={copyRevisionText}><Copy size={15} />复制修改话术</button><label className="field">修改要求<textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="粘贴上方修改话术，或直接写清楚要改什么。" /></label><button className="btn primary" disabled={!instruction.trim() || chapterTask} onClick={() => runTask("revise")}><Play size={15} />按要求修订</button></div>}
        {inspectorTab === "memory" && <><h3>章节记忆</h3><pre className="readable">{chapterState.data?.memory_readable || readable(safeJson(chapter?.memory_json, null))}</pre></>}
        {inspectorTab === "versions" && <><h3>候选版本</h3>{candidateText && <Candidate text={candidateText} label="本次修订候选稿" disabled={Boolean(workTask) || saveMutation.isPending} onPreview={() => setPreviewCandidate({ text: candidateText, label: "本次修订候选稿" })} onLoad={() => loadCandidate(candidateText)} onPromote={() => promoteCandidate(candidateText)} />}{visibleVersions.map((version) => { const text = String(version.content || ""); const label = candidateLabel(version); return <Candidate key={String(version.id)} text={text} label={label} disabled={Boolean(workTask) || saveMutation.isPending} onPreview={() => setPreviewCandidate({ text, label })} onLoad={() => loadCandidate(text)} onPromote={() => promoteCandidate(text)} onDelete={() => deleteCandidate(version.id)} />; })}{!candidateText && !visibleVersions.length && <p className="readable">暂无候选版本。未通过自动验收的稿件会保存在这里，不会覆盖最终稿。</p>}</>}
      </div></aside>
    </div>
    {previewCandidate && <div className="modal-backdrop" role="presentation" onMouseDown={() => setPreviewCandidate(null)}><section className="candidate-preview" role="dialog" aria-modal="true" aria-label="候选稿预览" onMouseDown={(event) => event.stopPropagation()}><header><div><strong>{previewCandidate.label}</strong><span>候选稿，未覆盖最终稿</span></div><button className="icon-button" title="关闭预览" onClick={() => setPreviewCandidate(null)}><X size={17} /></button></header><div className="candidate-preview-body">{previewCandidate.text}</div><footer><button className="btn" onClick={() => setPreviewCandidate(null)}>关闭</button><button className="btn" disabled={Boolean(workTask) || saveMutation.isPending} onClick={() => loadCandidate(previewCandidate.text)}><Eye size={15} />载入编辑器</button><button className="btn primary" disabled={Boolean(workTask) || saveMutation.isPending} onClick={() => promoteCandidate(previewCandidate.text)}><Save size={15} />保存为最终稿</button></footer></section></div>}
  </div>;
}

function Candidate({ text, label, disabled = false, onPreview, onLoad, onPromote, onDelete }: { text: string; label: string; disabled?: boolean; onPreview: () => void; onLoad: () => void; onPromote: () => void; onDelete?: () => void }) { return <div className="candidate"><div className="candidate-head"><strong>{label}</strong><span className="status-badge problem_draft">未覆盖最终稿</span></div><p>{text}</p><div className="candidate-actions"><button className="btn small" onClick={onPreview}><Eye size={14} />预览</button><button className="btn small" disabled={disabled} onClick={onLoad}><Play size={14} />载入</button><button className="btn small" disabled={disabled} onClick={onPromote}><Save size={14} />转为最终稿</button>{onDelete && <button className="icon-button danger-icon" disabled={disabled} title="删除候选稿" onClick={onDelete}><Trash2 size={14} /></button>}</div></div>; }
function candidateLabel(version: Record<string, unknown>): string {
  const name = String(version.version_name || "");
  if (name === "web_user_instruction_first_pass") return "第一轮修订稿";
  if (name.startsWith("reviser_rejected_repeat_")) return "重复风险未采用稿";
  if (name.startsWith("reviser_rejected_style_")) return "风格校验未采用稿";
  return "历史候选稿";
}
function textToHtml(text: string) { return String(text || "").split(/\n{2,}|\r?\n/).filter(Boolean).map((line) => `<p>${escapeHtml(line)}</p>`).join(""); }
function escapeHtml(text: string) { return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;"); }
function revisionAdviceFrom(review?: Record<string, unknown>): RevisionAdvice[] {
  const plan = Array.isArray(review?.revision_plan) ? review.revision_plan : [];
  const suggestions = Array.isArray(review?.suggestions) ? review.suggestions : [];
  const source = plan.length ? plan : suggestions;
  return source.map((item) => {
    if (typeof item === "string") return { target: "", evidence: "", action: item.trim(), keep: "", avoid: "" };
    if (!item || typeof item !== "object") return null;
    const value = item as Record<string, unknown>;
    return {
      target: String(value.target || "").trim(),
      evidence: String(value.evidence || "").trim(),
      action: String(value.action || "").trim(),
      keep: String(value.keep || "").trim(),
      avoid: String(value.avoid || "").trim(),
    };
  }).filter((item): item is RevisionAdvice => Boolean(item?.action)).slice(0, 5);
}
function formatRevisionCopy(items: RevisionAdvice[]) {
  return items.map((item, index) => [
    `${index + 1}. 修改目标：${item.target || item.evidence || "本章相关段落"}`,
    `   修改：${item.action}`,
    item.keep ? `   保留：${item.keep}` : "",
    item.avoid ? `   避免：${item.avoid}` : "",
  ].filter(Boolean).join("\n")).join("\n\n");
}
function taskText(chapter: Chapter, fallback?: string) { const detail = safeJson(chapter.outline_json, {}); return readable(Object.keys(detail).length ? detail : { title: chapter.title, outline: chapter.outline, ending_hook: chapter.ending_hook, handoff: chapter.handoff }) || fallback || "暂无任务单。"; }
function groupChapters(chapters: ChapterSummary[], volumes: Array<Record<string, unknown>>, search: string) {
  const map = new Map<number, { number: number; title: string; chapters: ChapterSummary[] }>();
  volumes.forEach((volume, index) => { const number = Number(volume.volume_number || index + 1); map.set(number, { number, title: String(volume.title || "未命名"), chapters: [] }); });
  chapters.forEach((chapter) => { const detail = safeJson(chapter.outline_json, {}); const number = Number(chapter.volume_number || detail.volume_number || 1); if (!map.has(number)) map.set(number, { number, title: `第${number}卷`, chapters: [] }); if (!search || `${chapter.title || ""}${chapter.outline || ""}${chapter.summary || ""}`.toLowerCase().includes(search.toLowerCase())) map.get(number)!.chapters.push(chapter); });
  return [...map.values()].filter((group) => group.chapters.length).sort((a,b) => a.number-b.number);
}
async function clearChapter(workId: number, chapter: Chapter, queryClient: any, notify: (message:string,tone?:any)=>void, onCleared: () => void) {
  if (!window.confirm(`确定清空第 ${chapter.chapter_number} 章正文吗？细纲会保留。`)) return;
  try { await api(`/api/works/${workId}/chapters/${chapter.chapter_number}/clear-text`, { method: "POST", body: { chapter_id: chapter.id, updated_at: chapter.updated_at, revision: Number(chapter.revision || 0) } }); onCleared(); await queryClient.invalidateQueries({ queryKey: ["work", workId] }); await queryClient.invalidateQueries({ queryKey: ["chapter", workId, chapter.chapter_number] }); notify("正文已清空。", "success"); } catch (error) { notify((error as Error).message, "danger"); }
}
