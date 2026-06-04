const state = {
  works: [],
  workData: null,
  work: null,
  selectedWorkId: null,
  selectedChapter: 1,
  currentChapter: null,
  pendingPlan: null,
  pendingPlanWorkId: null,
  config: null,
  tab: "project",
  outline: { full_outline: "", volume_outline: [], chapters: [] },
  outlineSelection: { type: "full" },
  outlineExpandedVolumes: [],
  outlineTargetVolume: null,
  libraryKind: "characters",
  libraryItem: null,
  runLogs: [],
  agentRuns: [],
  taskRuns: [],
  task: null,
  taskSerial: 0,
  confirmResolver: null,
};

const $ = (id) => document.getElementById(id);

const STYLE_SELECT_OPTIONS = {
  pace: ["快节奏", "稳推进", "慢热", "强反转", "群像推进"],
  language: ["白话凝练", "古意克制", "幽默轻松", "压迫冷峻", "细腻沉浸"],
  mood: ["热血", "苍凉", "轻松", "压迫", "群像"],
  pov: ["第三人称有限视角", "第三人称多视角", "第一人称", "全知视角"],
  chapter_words: ["2000字左右", "3000字左右", "5000字左右", "按剧情自然分配"],
  payoff: ["低", "中", "高"],
};

const CHAPTER_FIELDS = [
  ["story_time", "故事时间"],
  ["chapter_goal", "本章目标"],
  ["reader_expectation", "读者期待"],
  ["conflict", "核心冲突"],
  ["main_scene", "主要场景"],
  ["characters_present", "出场人物"],
  ["clues", "线索"],
  ["new_information", "信息增量"],
  ["chapter_payoff", "本章回报"],
  ["character_change", "人物变化"],
  ["foreshadowing", "伏笔"],
  ["emotional_turn", "情绪转折"],
  ["emotional_rhythm", "情绪节奏"],
  ["handoff", "下一章接力棒"],
  ["forbidden", "禁止内容"],
];

const BOOK_CONTRACT_FIELDS = [
  ["protagonist_fantasy", "protagonistFantasyInput", "主角爽点"],
  ["escalation_ladder", "escalationLadderInput", "升级阶梯"],
  ["relationship_mainline", "relationshipMainlineInput", "关系主线"],
  ["absolute_red_lines", "absoluteRedLinesInput", "绝对红线"],
];

const LIBRARY_CATEGORIES = {
  characters: {
    label: "人物",
    title: (item) => item.name || "未命名人物",
    readonly: false,
    fields: [
      ["name", "姓名", "input"],
      ["role", "定位", "input"],
      ["personality", "性格", "textarea"],
      ["goal", "目标", "textarea"],
      ["secret", "秘密", "textarea"],
      ["speaking_style", "说话风格", "textarea"],
      ["relationship", "关系", "textarea"],
      ["locked_rules", "锁定规则", "textarea"],
      ["current_goal", "当前目标", "textarea"],
      ["current_fear", "当前恐惧", "textarea"],
      ["current_state", "当前状态", "textarea"],
      ["relationship_stage", "关系阶段", "input"],
      ["secret_exposure", "秘密暴露", "textarea"],
      ["arc_stage", "成长阶段", "input"],
      ["arc_notes", "成长备注", "textarea"],
      ["last_changed_chapter", "最近变化章节", "number"],
    ],
  },
  world_rules: {
    label: "世界观",
    title: (item) => item.rule_name || "未命名规则",
    readonly: false,
    fields: [
      ["rule_name", "规则名称", "input"],
      ["rule_content", "规则内容", "textarea"],
      ["limitations", "限制", "textarea"],
      ["forbidden_changes", "禁止改动", "textarea"],
    ],
  },
  plot_threads: {
    label: "伏笔",
    title: (item) => item.content || "未命名伏笔",
    readonly: false,
    fields: [
      ["first_chapter", "首次出现章节", "number"],
      ["content", "伏笔内容", "textarea"],
      ["status", "状态", "input"],
      ["planned_resolve_chapter", "计划回收章节", "number"],
      ["actual_resolve_chapter", "实际回收章节", "number"],
    ],
  },
  timeline: {
    label: "时间线",
    title: (item) => item.event || "未命名事件",
    readonly: false,
    fields: [
      ["chapter_number", "章节", "number"],
      ["story_time", "故事时间", "input"],
      ["event", "事件", "textarea"],
      ["characters_involved", "涉及人物", "input"],
    ],
  },
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function parseJson(value, fallback) {
  if (!value) return fallback;
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

async function api(path, options = {}) {
  const init = { method: options.method || "GET", headers: {} };
  if (options.signal) init.signal = options.signal;
  if (options.body !== undefined) {
    init.headers["Content-Type"] = "application/json; charset=utf-8";
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  const payload = await response.json();
  if (!payload.ok) {
    throw new Error(payload.error || "本地接口调用失败");
  }
  return payload.data;
}

function log(message, type = "info") {
  const entry = {
    time: new Date(),
    message,
    type,
    work: state.work?.title || "",
    chapter: state.selectedChapter || "",
    task: state.task?.title || "",
  };
  state.runLogs.unshift(entry);
  if (state.runLogs.length > 200) state.runLogs.length = 200;
  renderLogList();
}

function renderLogList() {
  const list = $("logList");
  if (!list) return;
  list.innerHTML = "";
  if (!state.runLogs.length) {
    list.innerHTML = '<div class="empty">暂无运行记录。</div>';
    return;
  }
  for (const entry of state.runLogs) {
    const item = document.createElement("div");
    item.className = `log-entry ${entry.type || "info"}`;
    const meta = [
      entry.work ? `文章：${entry.work}` : "",
      entry.chapter ? `章节：第 ${entry.chapter} 章` : "",
      entry.task ? `任务：${entry.task}` : "",
    ].filter(Boolean).join(" · ");
    item.innerHTML = `
      <div class="log-time">${escapeHtml(entry.time.toLocaleString())}</div>
      <div class="log-message">${escapeHtml(entry.message)}</div>
      ${meta ? `<div class="log-meta">${escapeHtml(meta)}</div>` : ""}
    `;
    list.appendChild(item);
  }
}

function clearRunLogs() {
  state.runLogs = [];
  renderLogList();
  notify("本次运行记录已清空。", "success");
}

function renderTaskRuns() {
  const list = $("taskRunList");
  if (!list) return;
  list.innerHTML = "";
  if (!state.selectedWorkId) {
    list.innerHTML = '<div class="empty">请先选择文章。</div>';
    return;
  }
  if (!state.taskRuns.length) {
    list.innerHTML = '<div class="empty">暂无生成任务流水。</div>';
    return;
  }
  for (const run of state.taskRuns) {
    const item = document.createElement("div");
    item.className = `log-entry ${run.status === "done" ? "success" : run.status === "failed" ? "error" : "info"}`;
    const meta = [
      run.kind ? `类型：${run.kind}` : "",
      run.stage ? `阶段：${run.stage}` : "",
      run.chapter_id ? `章节 ID：${run.chapter_id}` : "",
    ].filter(Boolean).join(" · ");
    item.innerHTML = `
      <div class="log-time">${escapeHtml(run.updated_at || run.created_at || "")}</div>
      <div class="log-message">${escapeHtml(run.title || "未命名任务")} · ${escapeHtml(statusText(run.status || ""))}</div>
      ${meta ? `<div class="log-meta">${escapeHtml(meta)}</div>` : ""}
      ${run.error ? `<div class="log-meta">错误：${escapeHtml(run.error)}</div>` : ""}
    `;
    list.appendChild(item);
  }
}

function renderAgentRuns() {
  const list = $("agentRunList");
  if (!list) return;
  list.innerHTML = "";
  if (!state.selectedWorkId) {
    list.innerHTML = '<div class="empty">请先选择文章。</div>';
    return;
  }
  if (!state.agentRuns.length) {
    list.innerHTML = '<div class="empty">暂无 AI 调用记录。</div>';
    return;
  }
  for (const run of state.agentRuns) {
    const item = document.createElement("div");
    item.className = `log-entry ${run.status === "ok" ? "success" : "error"}`;
    const chapter = run.chapter_number ? `章节：第 ${run.chapter_number} 章` : "章节：全书/项目";
    item.innerHTML = `
      <div class="log-time">${escapeHtml(run.created_at || "")}</div>
      <div class="log-message">${escapeHtml(run.agent_name || "未知 Agent")} · ${escapeHtml(run.status || "未知状态")}</div>
      <div class="log-meta">${escapeHtml(chapter)} · 模型：${escapeHtml(run.model || "未记录")} · 提示词：${escapeHtml(run.prompt_name || "未记录")}</div>
      ${run.error ? `<div class="log-meta">错误：${escapeHtml(run.error)}</div>` : ""}
    `;
    list.appendChild(item);
  }
}

async function refreshRecords() {
  if (!requireWork()) {
    renderAgentRuns();
    renderTaskRuns();
    return;
  }
  try {
    const data = await api(`/api/works/${state.selectedWorkId}/records`);
    state.agentRuns = data.agent_runs || [];
    state.taskRuns = data.task_runs || [];
    renderAgentRuns();
    renderTaskRuns();
    log("运行记录已刷新。");
  } catch (error) {
    showError(error);
  }
}

function notify(message, type = "info") {
  const stack = $("toastStack");
  if (!stack) return;
  const item = document.createElement("div");
  item.className = `toast ${type}`;
  item.textContent = message;
  stack.appendChild(item);
  window.setTimeout(() => item.classList.add("show"), 20);
  window.setTimeout(() => {
    item.classList.remove("show");
    window.setTimeout(() => item.remove(), 180);
  }, 3200);
}

function showError(error) {
  if (error?.name === "AbortError") {
    notify("当前生成已停止。", "warning");
    return;
  }
  const message = error?.message || String(error);
  log(`失败：${message}`);
  notify(message, "error");
}

function requireWork() {
  if (!state.selectedWorkId) {
    notify("请先新建或选择一篇文章。", "warning");
    return false;
  }
  return true;
}

function confirmAction(message, title = "确认操作", okText = "确定") {
  return new Promise((resolve) => {
    const modal = $("confirmModal");
    $("confirmTitle").textContent = title;
    $("confirmMessage").textContent = message;
    $("confirmOkBtn").textContent = okText;
    modal.hidden = false;
    state.confirmResolver = resolve;
  });
}

function closeConfirmModal(result) {
  $("confirmModal").hidden = true;
  if (state.confirmResolver) state.confirmResolver(result);
  state.confirmResolver = null;
}

function startTask(kind, title, detail) {
  const controller = new AbortController();
  const id = `${Date.now()}-${++state.taskSerial}-${kind}`;
  state.task = { id, kind, title, detail, controller, startedAt: Date.now(), status: "running", stopped: false };
  updateTaskUI();
  return state.task;
}

async function cancelBackendTask(task) {
  if (!task?.id) return;
  try {
    const response = await fetch(`/api/tasks/${encodeURIComponent(task.id)}/cancel`, {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: "{}",
    });
    const payload = await response.json();
    if (payload?.ok && payload.data?.status && state.task?.id === task.id) {
      state.task.status = payload.data.status;
    }
  } catch {
    // 前端停止不能依赖取消接口一定返回；请求断开时本地结果仍会被前端丢弃。
  }
}

function stopTask() {
  if (!state.task) {
    notify("当前没有正在运行的生成任务。", "info");
    return;
  }
  const task = state.task;
  state.task.stopped = true;
  state.task.status = "cancelling";
  cancelBackendTask(task);
  state.task.controller.abort();
  log(`${state.task.title}已请求停止。`);
  notify("已请求停止并丢弃迟到结果。", "warning");
  updateTaskUI();
}

function finishTask(kind, status = "done") {
  if (state.task?.kind === kind) {
    state.task.status = status;
    state.task = null;
    updateTaskUI();
  }
}

function taskWasStopped(task) {
  return task?.stopped || task?.controller.signal.aborted || state.task !== task;
}

function updateTaskUI() {
  const active = Boolean(state.task);
  const title = active ? state.task.title : "暂无进行中的任务";
  const detail = active
    ? state.task.stopped ? "已请求停止，后端返回的迟到结果会被丢弃。" : state.task.detail
    : "生成设定、大纲、细纲和正文时，会在这里显示状态。";
  const status = active ? state.task.status || (state.task.stopped ? "cancelling" : "running") : "idle";
  $("taskTitle").textContent = title;
  $("taskDetail").textContent = detail;
  $("taskStatusPill").textContent = active ? statusText(status) : "空闲";
  $("taskStatusPill").className = `task-pill ${active ? status === "cancelling" ? "stopping" : "running" : ""}`;
  $("stopTaskBtn").disabled = !active || state.task.stopped;
  if ($("generatePlanBtn")) {
    $("generatePlanBtn").textContent = state.task?.kind === "plan" && !state.task.stopped ? "停止生成" : "生成设定草稿";
  }
}

function statusText(status) {
  const labels = {
    running: "生成中",
    cancelling: "停止中",
    cancelled: "已停止",
    failed: "失败",
    done: "完成",
  };
  return labels[status] || "生成中";
}

function setTab(tab) {
  state.tab = tab;
  document.querySelectorAll(".flow-nav button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tab);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${tab}`);
  });
  if (tab === "outline") updateOutlineGenerateControls();
}

function bindEvents() {
  $("tabNav").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-tab]");
    if (button) setTab(button.dataset.tab);
  });
  $("refreshBtn").addEventListener("click", refreshCurrentWork);
  $("newWorkBtn").addEventListener("click", createWork);
  $("saveWorkBtn").addEventListener("click", saveWork);
  $("deleteWorkBtn").addEventListener("click", deleteWork);
  $("toggleSettingsLockBtn").addEventListener("click", toggleSettingsLock);
  $("generatePlanBtn").addEventListener("click", generatePlan);
  $("applyPlanBtn").addEventListener("click", applyPlan);
  $("planSearchInput").addEventListener("input", renderPlanBrowser);
  $("generateOutlineBtn").addEventListener("click", generateOutline);
  $("saveOutlineBtn").addEventListener("click", saveOutline);
  $("outlineSearchInput").addEventListener("input", renderOutlineTree);
  $("outlineExpandAllBtn").addEventListener("click", expandAllVolumes);
  $("outlineCollapseAllBtn").addEventListener("click", collapseAllVolumes);
  $("addVolumeBtn").addEventListener("click", addVolume);
  $("addChapterBtn").addEventListener("click", addChapter);
  $("deleteOutlineItemBtn").addEventListener("click", deleteOutlineSelection);
  $("generateChapterOutlinesBtn").addEventListener("click", generateChapterOutlines);
  $("chapterStartInput").addEventListener("input", updateOutlineGenerateControls);
  $("clearLogBtn").addEventListener("click", clearRunLogs);
  $("refreshRecordsBtn").addEventListener("click", refreshRecords);
  $("chapterSearchInput").addEventListener("input", renderChapterLists);
  $("loadChapterBtn").addEventListener("click", () => loadChapter(Number($("writingChapterNumberInput").value || 1), "writing"));
  $("generateChapterBtn").addEventListener("click", generateChapter);
  $("saveChapterBtn").addEventListener("click", saveChapterText);
  $("memoryBtn").addEventListener("click", generateMemory);
  $("deleteWritingChapterBtn").addEventListener("click", deleteCurrentChapter);
  $("reviseWithInstructionBtn").addEventListener("click", reviseWithInstruction);
  $("inspectorTabs").addEventListener("click", switchInspector);
  $("refreshLibraryBtn").addEventListener("click", refreshLibrary);
  $("librarySearchInput").addEventListener("input", renderLibraryList);
  $("addLibraryItemBtn").addEventListener("click", addLibraryItem);
  $("saveLibraryItemBtn").addEventListener("click", saveLibraryItem);
  $("deleteLibraryItemBtn").addEventListener("click", deleteLibraryItem);
  $("exportBtn").addEventListener("click", exportWork);
  $("chooseExportDirBtn").addEventListener("click", chooseExportDir);
  $("openExportDirBtn").addEventListener("click", openExportDir);
  $("resetExportDirBtn").addEventListener("click", resetExportDir);
  $("saveConfigBtn").addEventListener("click", saveConfig);
  $("testApiBtn").addEventListener("click", testApi);
  $("toggleApiKeyBtn").addEventListener("click", toggleApiKeyVisibility);
  $("singleModelInput").addEventListener("change", syncSingleModelFields);
  $("defaultModelInput").addEventListener("input", syncSingleModelFields);
  $("stopTaskBtn").addEventListener("click", stopTask);
  $("confirmCancelBtn").addEventListener("click", () => closeConfirmModal(false));
  $("confirmOkBtn").addEventListener("click", () => closeConfirmModal(true));
  $("confirmModal").addEventListener("click", (event) => {
    if (event.target.id === "confirmModal") closeConfirmModal(false);
  });
}

async function init() {
  bindEvents();
  buildLibraryTabs();
  await Promise.all([loadHealth(), loadConfig(), loadWorks()]);
  updateTaskUI();
  updateProgress();
  renderLogList();
  renderAgentRuns();
  renderTaskRuns();
}

async function loadHealth() {
  const health = await api("/api/health");
  $("connectionText").textContent = `本地服务运行中 · 模型 ${health.model || "未设置"}`;
  $("modeBadge").textContent = health.mock_mode ? "mock 模式" : "真实 API";
}

async function loadConfig() {
  state.config = await api("/api/config");
  fillConfigForm();
}

async function loadWorks() {
  const data = await api("/api/works");
  state.works = data.works || [];
  renderWorks();
  if (state.selectedWorkId) {
    await selectWork(state.selectedWorkId, false);
  } else if (state.works.length) {
    await selectWork(state.works[0].id, false);
  } else {
    clearWorkState();
  }
}

async function refreshCurrentWork() {
  try {
    if (state.selectedWorkId) await selectWork(state.selectedWorkId);
    else await loadWorks();
    log("已刷新。");
  } catch (error) {
    showError(error);
  }
}

function renderWorks() {
  const list = $("workList");
  list.innerHTML = "";
  if (!state.works.length) {
    list.innerHTML = '<div class="empty">暂无文章。</div>';
    return;
  }
  for (const work of state.works) {
    const item = document.createElement("div");
    item.className = `work-item ${Number(work.id) === Number(state.selectedWorkId) ? "active" : ""}`;
    item.innerHTML = `
      <div class="item-title">${escapeHtml(work.title || "未命名文章")}</div>
      <div class="item-meta">ID ${escapeHtml(work.id)} · ${escapeHtml(work.updated_at || work.created_at || "")}</div>
    `;
    item.addEventListener("click", () => selectWork(work.id));
    list.appendChild(item);
  }
}

async function selectWork(workId, writeLog = true) {
  const data = await api(`/api/works/${workId}`);
  applyWorkState(data);
  if (writeLog) log(`已切换到《${state.work.title || "未命名文章"}》。`);
}

function applyWorkState(data) {
  const previousWorkId = state.selectedWorkId;
  state.workData = data;
  state.work = data.work || null;
  state.works = data.works || state.works;
  state.agentRuns = data.agent_runs || [];
  state.taskRuns = data.task_runs || [];
  state.selectedWorkId = state.work ? state.work.id : null;
  if (previousWorkId && state.selectedWorkId !== previousWorkId) {
    state.pendingPlan = null;
    state.pendingPlanWorkId = null;
  }
  if (state.pendingPlanWorkId && state.pendingPlanWorkId !== state.selectedWorkId) {
    state.pendingPlan = null;
    state.pendingPlanWorkId = null;
  }
  state.outline = data.outline || { full_outline: "", volume_outline: [], chapters: [] };
  state.outline.volume_outline = state.outline.volume_outline || [];
  state.outline.chapters = state.outline.chapters || [];
  ensureChapterVolumeNumbers();
  if (!state.outlineSelection) state.outlineSelection = { type: "full" };
  ensureOutlineExpandedVolumes();
  setNextChapterStart();
  updateOutlineGenerateControls();
  renderWorks();
  fillWorkForm();
  fillBookContractForm();
  updateSettingsLockUI();
  renderPlanBrowser();
  renderOutlineTree();
  renderOutlineEditor();
  renderChapterLists();
  renderLibraryFromWork(data);
  renderAgentRuns();
  renderTaskRuns();
  updateExportDir(data);
  $("currentTitle").textContent = state.work ? `《${state.work.title || "未命名文章"}》` : "未选择文章";
  updateProgress();
}

function clearWorkState() {
  state.workData = null;
  state.work = null;
  state.selectedWorkId = null;
  state.currentChapter = null;
  state.pendingPlan = null;
  state.pendingPlanWorkId = null;
  state.outline = { full_outline: "", volume_outline: [], chapters: [] };
  state.outlineSelection = { type: "full" };
  state.outlineExpandedVolumes = [];
  state.outlineTargetVolume = null;
  state.libraryItem = null;
  state.agentRuns = [];
  state.taskRuns = [];
  $("currentTitle").textContent = "未选择文章";
  fillWorkForm();
  fillBookContractForm();
  updateSettingsLockUI();
  renderPlanBrowser();
  renderOutlineTree();
  renderOutlineEditor();
  renderChapterLists();
  renderLibraryFromWork({});
  renderAgentRuns();
  renderTaskRuns();
  updateExportDir({});
  updateOutlineGenerateControls();
  updateProgress();
}

function splitStyle(style) {
  const result = {
    pace: "",
    language: "",
    mood: "",
    pov: "",
    chapter_words: "",
    payoff: "",
  };
  const map = {
    "叙事节奏": "pace",
    "语言风格": "language",
    "情绪底色": "mood",
    "叙事视角": "pov",
    "单章字数": "chapter_words",
    "爽点密度": "payoff",
  };
  const extra = [];
  for (const line of String(style || "").split(/\r?\n/)) {
    const text = line.trim();
    if (!text) continue;
    const match = text.match(/^([^：:]+)[：:]\s*(.*)$/);
    if (match && map[match[1]]) {
      result[map[match[1]]] = match[2].trim();
    } else {
      extra.push(text);
    }
  }
  if (!result.pace && extra.length === 1 && STYLE_SELECT_OPTIONS.pace.includes(extra[0])) {
    result.pace = extra[0];
    extra.length = 0;
  }
  for (const key of ["pace", "language", "mood", "pov", "chapter_words", "payoff"]) {
    if (result[key] && !STYLE_SELECT_OPTIONS[key].includes(result[key])) {
      extra.push(`${Object.keys(map).find((label) => map[label] === key)}：${result[key]}`);
      result[key] = "";
    }
  }
  return result;
}

function fillWorkForm() {
  const work = state.work || {};
  const style = splitStyle(work.style || "");
  $("titleInput").value = work.title || "";
  $("ideaInput").value = work.idea || "";
  $("genreInput").value = work.genre || "";
  $("platformInput").value = work.platform || "";
  $("targetWordsInput").value = Number(work.target_words || 0) || "";
  $("paceInput").value = style.pace;
  $("languageInput").value = style.language;
  $("moodInput").value = style.mood;
  $("povInput").value = style.pov;
  $("chapterWordsInput").value = style.chapter_words;
  $("payoffInput").value = style.payoff;
}

function fillBookContractForm() {
  const contract = state.workData?.book_contract || {};
  if (!contract.absolute_red_lines && state.work?.locked_facts) {
    contract.absolute_red_lines = readableTextList(state.work.locked_facts);
  }
  for (const [key, id] of BOOK_CONTRACT_FIELDS) {
    const node = $(id);
    if (node) node.value = contract[key] || "";
  }
}

function readableTextList(value) {
  const parsed = parseJson(value, null);
  if (Array.isArray(parsed)) return parsed.join("\n");
  return value || "";
}

function collectBookContractForm() {
  const contract = {};
  for (const [key, id] of BOOK_CONTRACT_FIELDS) {
    contract[key] = ($(id)?.value || "").trim();
  }
  return contract;
}

function updateSettingsLockUI() {
  const locked = Boolean(Number(state.work?.settings_locked || 0));
  const status = $("settingsLockStatus");
  const button = $("toggleSettingsLockBtn");
  const panel = $("settingsLockPanel");
  if (status) status.textContent = locked ? "当前已锁定" : "当前未锁定";
  if (button) {
    button.textContent = locked ? "解锁作品设定" : "锁定作品设定";
    button.classList.toggle("primary", !locked);
    button.classList.toggle("danger", locked);
    button.disabled = !state.selectedWorkId;
  }
  if (panel) panel.classList.toggle("locked", locked);
  for (const id of [
    "titleInput",
    "ideaInput",
    "genreInput",
    "platformInput",
    "targetWordsInput",
    "paceInput",
    "languageInput",
    "moodInput",
    "povInput",
    "chapterWordsInput",
    "payoffInput",
    ...BOOK_CONTRACT_FIELDS.map(([, id]) => id),
  ]) {
    const node = $(id);
    if (node) node.disabled = locked;
  }
  if ($("saveWorkBtn")) $("saveWorkBtn").disabled = locked;
  if ($("applyPlanBtn")) $("applyPlanBtn").disabled = locked;
}

async function toggleSettingsLock() {
  if (!requireWork()) {
    updateSettingsLockUI();
    return;
  }
  const locked = !Boolean(Number(state.work?.settings_locked || 0));
  try {
    const data = await api(`/api/works/${state.selectedWorkId}/settings-lock`, {
      method: "POST",
      body: { locked },
    });
    applyWorkState(data);
    log(locked ? "作品设定已锁定。" : "作品设定已解锁。");
    notify(locked ? "作品设定已锁定。" : "作品设定已解锁。", "success");
  } catch (error) {
    updateSettingsLockUI();
    showError(error);
  }
}

function collectWorkForm() {
  const styleParts = [
    ["叙事节奏", $("paceInput").value.trim()],
    ["语言风格", $("languageInput").value.trim()],
    ["情绪底色", $("moodInput").value.trim()],
    ["叙事视角", $("povInput").value.trim()],
    ["单章字数", $("chapterWordsInput").value.trim()],
    ["爽点密度", $("payoffInput").value.trim()],
  ].filter(([, value]) => value);
  return {
    title: $("titleInput").value.trim(),
    idea: $("ideaInput").value.trim(),
    genre: $("genreInput").value.trim(),
    platform: $("platformInput").value.trim(),
    target_words: Number($("targetWordsInput").value || 0),
    style: styleParts.map(([label, value]) => `${label}：${value}`).join("\n"),
    forbidden_tropes: "",
    protagonist_preference: "",
    reader_profile: "",
    locked_facts: $("absoluteRedLinesInput").value.trim(),
    writing_controls: "",
  };
}

async function createWork() {
  try {
    const data = await api("/api/works", { method: "POST", body: {} });
    applyWorkState(data);
    setTab("project");
    log("已新建空白文章。");
  } catch (error) {
    showError(error);
  }
}

async function saveWork() {
  try {
    const body = collectWorkForm();
    let data = state.selectedWorkId
      ? await api(`/api/works/${state.selectedWorkId}`, { method: "PUT", body })
      : await api("/api/works", { method: "POST", body });
    if (data.work?.id) {
      data = await api(`/api/works/${data.work.id}/book-contract`, {
        method: "PUT",
        body: collectBookContractForm(),
      });
    }
    applyWorkState(data);
    log("基础信息与整本契约已保存。");
    notify("基础信息与整本契约已保存。", "success");
  } catch (error) {
    showError(error);
  }
}

async function deleteWork() {
  if (!state.selectedWorkId) return;
  const title = state.work?.title || "当前文章";
  const ok = await confirmAction(`确定删除《${title}》吗？这会删除它的数据库和导出文件。`, "删除文章", "删除");
  if (!ok) return;
  try {
    await api(`/api/works/${state.selectedWorkId}`, { method: "DELETE" });
    state.selectedWorkId = null;
    await loadWorks();
    log(`已删除《${title}》。`);
    notify(`已删除《${title}》。`, "success");
  } catch (error) {
    showError(error);
  }
}

function buildPlanItems() {
  const data = state.workData || {};
  const items = [];
  if (state.pendingPlan) {
    items.push(["设定草稿", formatAny(state.pendingPlan)]);
  }
  const contract = data.book_contract || {};
  if (Object.values(contract).some((value) => String(value || "").trim())) {
    items.push(["整本契约", formatRecord(contract)]);
  }
  if (data.project_readable) items.push(["当前设定", data.project_readable]);
  for (const character of data.characters || []) {
    items.push([`人物 · ${character.name || "未命名"}`, formatRecord(character)]);
  }
  for (const rule of data.world_rules || []) {
    items.push([`规则 · ${rule.rule_name || "未命名"}`, formatRecord(rule)]);
  }
  return items;
}

function renderPlanBrowser() {
  const nav = $("planNav");
  const preview = $("planPreview");
  const keyword = ($("planSearchInput")?.value || "").trim().toLowerCase();
  const items = buildPlanItems().filter(([title, text]) => !keyword || `${title}\n${text}`.toLowerCase().includes(keyword));
  nav.innerHTML = "";
  if (!items.length) {
    nav.innerHTML = '<div class="empty">暂无设定条目。</div>';
    preview.textContent = "暂无设定。";
    return;
  }
  items.forEach(([title, text], index) => {
    const item = document.createElement("div");
    item.className = `nav-item ${index === 0 ? "active" : ""}`;
    item.innerHTML = `<div class="item-title">${escapeHtml(title)}</div>`;
    item.addEventListener("click", () => {
      nav.querySelectorAll(".nav-item").forEach((node) => node.classList.remove("active"));
      item.classList.add("active");
      preview.textContent = text;
    });
    nav.appendChild(item);
  });
  preview.textContent = items[0][1];
}

async function generatePlan() {
  if (state.task?.kind === "plan") {
    stopTask();
    return;
  }
  if (state.task) {
    notify("请先等待当前任务结束，或点击停止生成。", "warning");
    return;
  }
  if (!state.selectedWorkId) await saveWork();
  if (!state.selectedWorkId) return;
  const task = startTask("plan", "生成设定草稿", "策划 AI 正在整理书名、简介、人物、世界观和主线方向。");
  try {
    log("策划 AI 正在生成设定草稿...");
    const data = await api(`/api/works/${state.selectedWorkId}/plan-draft`, {
      method: "POST",
      body: { ...collectWorkForm(), task_id: task.id },
      signal: task.controller.signal,
    });
    if (taskWasStopped(task)) return;
    state.pendingPlan = data.plan;
    state.pendingPlanWorkId = state.selectedWorkId;
    renderPlanBrowser();
    $("planPreview").textContent = data.readable || formatAny(data.plan);
    log("设定草稿已生成。");
    notify("设定草稿已生成。", "success");
  } catch (error) {
    if (taskWasStopped(task)) {
      log("设定草稿生成已停止，返回结果不会写入界面。");
      notify("设定草稿生成已停止。", "warning");
    } else {
      showError(error);
    }
  } finally {
    finishTask("plan");
  }
}

async function applyPlan() {
  if (!state.selectedWorkId || !state.pendingPlan) {
    notify("请先生成设定草稿，再采用入库。", "warning");
    return;
  }
  if (state.pendingPlanWorkId !== state.selectedWorkId) {
    state.pendingPlan = null;
    state.pendingPlanWorkId = null;
    renderPlanBrowser();
    notify("设定草稿不属于当前文章，已清空。请重新生成。", "warning");
    return;
  }
  try {
    const data = await api(`/api/works/${state.selectedWorkId}/apply-plan`, {
      method: "POST",
      body: { plan: state.pendingPlan, inputs: collectWorkForm() },
    });
    state.pendingPlan = null;
    state.pendingPlanWorkId = null;
    applyWorkState(data);
    log("设定草稿已采用入库。");
  } catch (error) {
    showError(error);
  }
}

function renderOutlineTree() {
  const tree = $("outlineTree");
  const keyword = ($("outlineSearchInput")?.value || "").trim().toLowerCase();
  ensureChapterVolumeNumbers();
  ensureOutlineExpandedVolumes();
  tree.innerHTML = "";
  const fullMatches = !keyword || `全书大纲\n${state.outline.full_outline || ""}`.toLowerCase().includes(keyword);
  if (fullMatches) {
    tree.appendChild(outlineTreeItem("full", "全书大纲", { type: "full" }, false));
  }
  let matchCount = fullMatches ? 1 : 0;
  const volumes = state.outline.volume_outline || [];
  if (!volumes.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "暂无分卷。点击“添加分卷”后，再把章节归入对应分卷。";
    tree.appendChild(empty);
    updateOutlineGenerateControls();
    return;
  }
  volumes.forEach((volume, index) => {
    const volumeNumber = Number(volume.volume_number || index + 1);
    const volumeTitle = `分卷 ${volumeNumber} · ${volume.title || "未命名"}`;
    const chapters = chaptersForVolume(volumeNumber);
    const volumeText = `${formatRecord(volume)}\n${chapters.map(outlineText).join("\n")}`;
    const volumeMatches = !keyword || `${volumeTitle}\n${volumeText}`.toLowerCase().includes(keyword);
    const visibleChapters = chapters.filter((chapter) => !keyword || outlineText(chapter).toLowerCase().includes(keyword));
    if (!volumeMatches && !visibleChapters.length) return;
    matchCount += 1;
    const expanded = Boolean(keyword) || isVolumeExpanded(volumeNumber);
    const volumeNode = outlineTreeItem("volume", volumeTitle, { type: "volume", index }, expanded);
    volumeNode.dataset.volumeNumber = String(volumeNumber);
    tree.appendChild(volumeNode);
    if (expanded) {
      for (const chapter of visibleChapters) {
        const selection = { type: "chapter", chapter_number: Number(chapter.chapter_number) };
        tree.appendChild(outlineTreeItem("chapter", `第 ${chapter.chapter_number} 章 · ${chapter.title || "未命名"}`, selection, false));
      }
    }
  });
  if (!matchCount) {
    tree.innerHTML = '<div class="empty">没有匹配的大纲条目。</div>';
    return;
  }
  updateOutlineGenerateControls();
}

function outlineTreeItem(kind, title, selection, expanded) {
  const item = document.createElement("div");
  const active = sameSelection(selection, state.outlineSelection);
  item.className = `nav-item ${kind === "volume" ? "nav-level-1 nav-volume" : kind === "chapter" ? "nav-level-2" : ""} ${active ? "active" : ""}`;
  const marker = kind === "volume" ? `<span class="tree-marker">${expanded ? "▾" : "▸"}</span>` : "";
  item.innerHTML = `${marker}<div class="item-title">${escapeHtml(title)}</div>`;
  item.addEventListener("click", () => {
    commitOutlineEditor();
    state.outlineSelection = selection;
    if (kind === "volume") {
      const volumeNumber = Number(item.dataset.volumeNumber || (state.outline.volume_outline[selection.index]?.volume_number || selection.index + 1));
      state.outlineTargetVolume = volumeNumber;
      toggleVolumeExpanded(volumeNumber);
    } else if (kind === "chapter") {
      const chapter = chapterByNumber(selection.chapter_number);
      state.outlineTargetVolume = Number(chapter?.volume_number || volumeForChapter(chapter));
    }
    renderOutlineTree();
    renderOutlineEditor();
  });
  return item;
}

function sameSelection(a, b) {
  return a?.type === b?.type && a?.index === b?.index && a?.chapter_number === b?.chapter_number;
}

function renderOutlineEditor() {
  const editor = $("outlineEditor");
  const selection = state.outlineSelection || { type: "full" };
  editor.innerHTML = "";
  $("deleteOutlineItemBtn").style.visibility = selection.type === "full" ? "hidden" : "visible";
  if (selection.type === "full") {
    $("outlineEditorTitle").textContent = "全书大纲";
    $("outlineEditorHint").textContent = "";
    editor.innerHTML = `<textarea id="outlineFullEdit" rows="20">${escapeHtml(state.outline.full_outline || "")}</textarea>`;
    return;
  }
  if (selection.type === "volume") {
    const volume = state.outline.volume_outline[selection.index] || {};
    $("outlineEditorTitle").textContent = `分卷：${volume.title || "未命名"}`;
    $("outlineEditorHint").textContent = "";
    editor.innerHTML = `
      <div class="outline-form">
        <div class="grid two">
          ${inputField("volume_number", "卷号", volume.volume_number || selection.index + 1, "number")}
          ${inputField("title", "卷名", volume.title || "")}
        </div>
        ${textareaField("goal", "卷目标", volume.goal || "")}
        ${textareaField("main_conflict", "主要冲突", volume.main_conflict || "")}
        ${textareaField("turning_points", "关键转折", arrayText(volume.turning_points))}
        ${textareaField("ending", "结尾状态", volume.ending || "")}
      </div>
    `;
    return;
  }
  const chapter = chapterByNumber(selection.chapter_number) || { chapter_number: selection.chapter_number || 1 };
  const detail = chapterDetail(chapter);
  $("outlineEditorTitle").textContent = `章节：第 ${chapter.chapter_number} 章`;
  $("outlineEditorHint").textContent = "";
  editor.innerHTML = `
    <div class="outline-form">
      <div class="grid two">
        ${inputField("chapter_number", "章节号", chapter.chapter_number || "", "number")}
        ${inputField("volume_number", "所属卷", detail.volume_number || volumeForChapter(chapter), "number")}
        ${inputField("title", "章节名", chapter.title || "")}
      </div>
      ${textareaField("outline", "细纲", detail.outline || chapter.outline || "", 8)}
      ${CHAPTER_FIELDS.map(([key, label]) => textareaField(key, label, valueText(detail[key]), 3)).join("")}
      ${textareaField("ending_hook", "结尾钩子", detail.ending_hook || chapter.ending_hook || "", 3)}
      <div>
        <div class="button-row"><h3>场景卡</h3><button type="button" id="addSceneBtn">添加场景</button></div>
        <div class="scene-list" id="sceneList">${renderSceneCards(detail.scene_cards || [])}</div>
      </div>
    </div>
  `;
  $("addSceneBtn").addEventListener("click", () => {
    const list = $("sceneList");
    list.insertAdjacentHTML("beforeend", renderSceneCards([{}], list.children.length));
  });
}

function inputField(name, label, value, type = "text") {
  return `<label>${label}<input data-field="${name}" type="${type}" value="${escapeHtml(value)}"></label>`;
}

function textareaField(name, label, value, rows = 4) {
  return `<label>${label}<textarea data-field="${name}" rows="${rows}">${escapeHtml(value || "")}</textarea></label>`;
}

function renderSceneCards(cards, startIndex = 0) {
  return (cards.length ? cards : [{}]).map((card, offset) => {
    const index = startIndex + offset + 1;
    return `
      <div class="scene-card" data-scene>
        <b>场景 ${index}</b>
        ${textareaField("scene_goal", "场景目标", card.scene_goal || "", 2)}
        ${textareaField("obstacle", "阻碍", card.obstacle || "", 2)}
        ${textareaField("information_gain", "信息增量", card.information_gain || "", 2)}
        ${textareaField("emotional_shift", "情绪变化", card.emotional_shift || "", 2)}
        ${textareaField("scene_exit", "场景出口", card.scene_exit || "", 2)}
      </div>
    `;
  }).join("");
}

function commitOutlineEditor() {
  const selection = state.outlineSelection || { type: "full" };
  const editor = $("outlineEditor");
  if (!editor) return;
  if (selection.type === "full") {
    const node = $("outlineFullEdit");
    if (node) state.outline.full_outline = node.value.trim();
    return;
  }
  const values = collectFields(editor);
  if (selection.type === "volume") {
    state.outline.volume_outline[selection.index] = {
      ...state.outline.volume_outline[selection.index],
      ...values,
      volume_number: Number(values.volume_number || selection.index + 1),
      turning_points: lines(values.turning_points),
    };
    return;
  }
  if (selection.type === "chapter") {
    const chapter = chapterByNumber(selection.chapter_number);
    if (!chapter) return;
    Object.assign(chapter, values);
    chapter.chapter_number = Number(values.chapter_number || chapter.chapter_number);
    chapter.volume_number = Number(values.volume_number || volumeForChapter(chapter));
    chapter.title = values.title || chapter.title || "";
    chapter.outline = values.outline || "";
    chapter.ending_hook = values.ending_hook || "";
    chapter.scene_cards = collectSceneCards();
  }
}

function collectFields(root) {
  const values = {};
  root.querySelectorAll("[data-field]").forEach((node) => {
    if (node.closest("[data-scene]")) return;
    values[node.dataset.field] = node.value;
  });
  return values;
}

function collectSceneCards() {
  return [...document.querySelectorAll("#sceneList [data-scene]")].map((scene) => {
    const card = {};
    scene.querySelectorAll("[data-field]").forEach((node) => {
      card[node.dataset.field] = node.value.trim();
    });
    return card;
  }).filter((card) => Object.values(card).some(Boolean));
}

async function generateOutline() {
  if (!requireWork()) return;
  if (state.task) {
    notify("请先等待当前任务结束，或点击停止生成。", "warning");
    return;
  }
  const task = startTask("outline", "生成全书大纲", "策划 AI 正在梳理全书主线、分卷目标和阶段推进。");
  try {
    log("策划 AI 正在生成全书大纲...");
    const data = await api(`/api/works/${state.selectedWorkId}/outline`, {
      method: "POST",
      body: { task_id: task.id },
      signal: task.controller.signal,
    });
    if (taskWasStopped(task)) return;
    applyWorkState(data);
    log("全书大纲已生成。");
    notify("全书大纲已生成。", "success");
  } catch (error) {
    if (taskWasStopped(task)) notify("全书大纲生成已停止。", "warning");
    else showError(error);
  } finally {
    finishTask("outline");
  }
}

async function saveOutline() {
  if (!requireWork()) return;
  commitOutlineEditor();
  try {
    const data = await persistOutline();
    applyWorkState(data);
    log("大纲已保存。");
  } catch (error) {
    showError(error);
  }
}

async function persistOutline() {
  for (const chapter of state.outline.chapters || []) {
    await saveChapterOutlineData(chapter);
  }
  return api(`/api/works/${state.selectedWorkId}/outline`, {
    method: "PUT",
    body: {
      full_outline: state.outline.full_outline || "",
      volume_outline: state.outline.volume_outline || [],
    },
  });
}

async function saveChapterOutlineData(chapter) {
  if (!chapter) return;
  await api(`/api/works/${state.selectedWorkId}/chapters/${Number(chapter.chapter_number)}/outline`, {
    method: "PUT",
    body: chapterPayload(chapter),
  });
}

function chapterPayload(chapter) {
  const detail = chapterDetail(chapter);
  return {
    ...detail,
    chapter_number: Number(chapter.chapter_number),
    volume_number: Number(chapter.volume_number || detail.volume_number || volumeForChapter(chapter)),
    title: chapter.title || "",
    outline: chapter.outline || detail.outline || "",
    ending_hook: chapter.ending_hook || detail.ending_hook || "",
    scene_cards: chapter.scene_cards || detail.scene_cards || [],
  };
}

async function generateChapterOutlines() {
  if (!requireWork()) return;
  if (state.task) {
    notify("请先等待当前任务结束，或点击停止生成。", "warning");
    return;
  }
  commitOutlineEditor();
  updateOutlineGenerateControls();
  const start = Number($("chapterStartInput").value || 1);
  const count = Number($("chapterCountInput").value || 3);
  const volumeNumber = currentOutlineTargetVolume();
  const task = startTask("chapterOutlines", "生成章节细纲", `策划 AI 正在生成第 ${volumeNumber} 卷，第 ${start} 章起的 ${count} 章任务单。`);
  try {
    await persistOutline();
    if (taskWasStopped(task)) return;
    log(`策划 AI 正在生成第 ${volumeNumber} 卷，第 ${start} 章起的 ${count} 章细纲...`);
    const data = await api(`/api/works/${state.selectedWorkId}/chapter-outlines`, {
      method: "POST",
      body: { start_chapter: start, count, volume_number: volumeNumber, task_id: task.id },
      signal: task.controller.signal,
    });
    if (taskWasStopped(task)) return;
    applyWorkState(data);
    state.outlineTargetVolume = volumeNumber;
    ensureExpanded(volumeNumber);
    renderOutlineTree();
    setNextChapterStart();
    updateOutlineGenerateControls();
    log("章节细纲已生成。");
    notify("章节细纲已生成。", "success");
  } catch (error) {
    if (taskWasStopped(task)) notify("章节细纲生成已停止。", "warning");
    else showError(error);
  } finally {
    finishTask("chapterOutlines");
  }
}

function addVolume() {
  commitOutlineEditor();
  const next = Math.max(0, ...state.outline.volume_outline.map((v) => Number(v.volume_number || 0))) + 1;
  state.outline.volume_outline.push({ volume_number: next, title: `第${next}卷`, goal: "", main_conflict: "", turning_points: [], ending: "" });
  state.outlineTargetVolume = next;
  ensureExpanded(next);
  state.outlineSelection = { type: "volume", index: state.outline.volume_outline.length - 1 };
  renderOutlineTree();
  renderOutlineEditor();
  updateOutlineGenerateControls();
  updateProgress();
}

function addChapter() {
  commitOutlineEditor();
  const next = Math.max(0, ...state.outline.chapters.map((c) => Number(c.chapter_number || 0))) + 1;
  const volumeNumber = currentOutlineTargetVolume();
  const chapter = { chapter_number: next, volume_number: volumeNumber, title: `第${next}章`, outline: "", ending_hook: "", scene_cards: [] };
  state.outline.chapters.push(chapter);
  state.outlineSelection = { type: "chapter", chapter_number: next, index: state.outline.chapters.length - 1 };
  state.outlineTargetVolume = volumeNumber;
  ensureExpanded(volumeNumber);
  renderOutlineTree();
  renderOutlineEditor();
  renderChapterLists();
  setNextChapterStart();
  updateProgress();
}

async function deleteOutlineSelection() {
  const selection = state.outlineSelection;
  if (!selection || selection.type === "full") return;
  if (selection.type === "volume") {
    const ok = await confirmAction("确定删除当前分卷吗？", "删除分卷", "删除");
    if (!ok) return;
    const deleted = state.outline.volume_outline[selection.index] || {};
    const deletedNumber = Number(deleted.volume_number || selection.index + 1);
    state.outline.volume_outline.splice(selection.index, 1);
    const fallbackVolume = state.outline.volume_outline[Math.min(selection.index, state.outline.volume_outline.length - 1)];
    const fallbackNumber = Number(fallbackVolume?.volume_number || 1);
    for (const chapter of state.outline.chapters || []) {
      if (Number(chapter.volume_number || volumeForChapter(chapter)) === deletedNumber) {
        chapter.volume_number = fallbackNumber;
      }
    }
    state.outlineExpandedVolumes = state.outlineExpandedVolumes.filter((number) => Number(number) !== deletedNumber);
    state.outlineTargetVolume = state.outline.volume_outline.length ? fallbackNumber : 1;
    ensureExpanded(state.outlineTargetVolume);
    state.outlineSelection = { type: "full" };
    renderOutlineTree();
    renderOutlineEditor();
    updateOutlineGenerateControls();
    updateProgress();
    notify("分卷已删除，记得保存当前大纲。", "success");
    return;
  }
  if (selection.type === "chapter") {
    await deleteChapterByNumber(selection.chapter_number);
  }
}

function chapterByNumber(number) {
  return (state.outline.chapters || []).find((chapter) => Number(chapter.chapter_number) === Number(number));
}

function chapterDetail(chapter) {
  return {
    ...parseJson(chapter.outline_json, {}),
    ...chapter,
    scene_cards: parseJson(chapter.scene_cards_json, parseJson(chapter.outline_json, {}).scene_cards || chapter.scene_cards || []),
  };
}

function ensureChapterVolumeNumbers() {
  for (const chapter of state.outline.chapters || []) {
    const detail = parseJson(chapter.outline_json, {});
    if (!chapter.volume_number) chapter.volume_number = Number(detail.volume_number || volumeForChapter(chapter));
  }
}

function ensureOutlineExpandedVolumes() {
  const volumes = state.outline.volume_outline || [];
  if (!volumes.length) {
    state.outlineExpandedVolumes = [];
    state.outlineTargetVolume = 1;
    return;
  }
  const valid = new Set(volumes.map((volume, index) => Number(volume.volume_number || index + 1)));
  state.outlineExpandedVolumes = (state.outlineExpandedVolumes || [])
    .map((number) => Number(number))
    .filter((number) => valid.has(number));
  if (!valid.has(Number(state.outlineTargetVolume))) {
    state.outlineTargetVolume = Number(volumes[0].volume_number || 1);
  }
}

function isVolumeExpanded(volumeNumber) {
  return (state.outlineExpandedVolumes || []).map(Number).includes(Number(volumeNumber));
}

function ensureExpanded(volumeNumber) {
  const number = Number(volumeNumber || 1);
  if (!isVolumeExpanded(number)) state.outlineExpandedVolumes.push(number);
}

function toggleVolumeExpanded(volumeNumber) {
  const number = Number(volumeNumber || 1);
  if (isVolumeExpanded(number)) {
    state.outlineExpandedVolumes = state.outlineExpandedVolumes.filter((item) => Number(item) !== number);
  } else {
    state.outlineExpandedVolumes.push(number);
  }
}

function expandAllVolumes() {
  state.outlineExpandedVolumes = (state.outline.volume_outline || []).map((volume, index) => Number(volume.volume_number || index + 1));
  renderOutlineTree();
}

function collapseAllVolumes() {
  state.outlineExpandedVolumes = [];
  renderOutlineTree();
}

function currentOutlineTargetVolume() {
  const selection = state.outlineSelection || {};
  if (selection.type === "volume") {
    const volume = state.outline.volume_outline?.[selection.index];
    return Number(volume?.volume_number || selection.index + 1 || 1);
  }
  if (selection.type === "chapter") {
    const chapter = chapterByNumber(selection.chapter_number);
    return Number(chapter?.volume_number || volumeForChapter(chapter) || state.outlineTargetVolume || 1);
  }
  return Number(state.outlineTargetVolume || firstVolumeNumber());
}

function firstVolumeNumber() {
  const first = (state.outline.volume_outline || [])[0];
  return Number(first?.volume_number || 1);
}

function nextChapterNumber() {
  return Math.max(0, ...(state.outline.chapters || []).map((chapter) => Number(chapter.chapter_number || 0))) + 1;
}

function setNextChapterStart() {
  const input = $("chapterStartInput");
  if (input) input.value = String(nextChapterNumber());
}

function updateOutlineGenerateControls() {
  const volumeNumber = currentOutlineTargetVolume();
  const start = nextChapterNumber();
  const input = $("chapterStartInput");
  const target = $("outlineTargetText");
  if (target) {
    if (!state.selectedWorkId) {
      target.textContent = "生成目标：未选择文章";
    } else if (!(state.outline.volume_outline || []).length) {
      target.textContent = "生成目标：暂无分卷，请先添加或生成全书大纲";
    } else {
      const volume = (state.outline.volume_outline || []).find((item, index) => Number(item.volume_number || index + 1) === volumeNumber);
      target.textContent = volume
        ? `生成目标：第 ${volumeNumber} 卷 · ${volume.title || "未命名"}；默认从第 ${start} 章开始`
        : `生成目标：默认第 ${volumeNumber} 卷；默认从第 ${start} 章开始`;
    }
  }
  const button = $("generateChapterOutlinesBtn");
  if (button) button.textContent = `生成第 ${Number(input?.value || start)} 章起细纲`;
}

function volumeForChapter(chapter) {
  const explicit = Number(chapter?.volume_number || parseJson(chapter?.outline_json, {}).volume_number || 0);
  if (explicit) return explicit;
  const number = Number(chapter?.chapter_number || 1);
  const volumes = state.outline.volume_outline || [];
  if (!volumes.length) return 1;
  const perVolume = Math.max(1, Math.ceil(Math.max(1, state.outline.chapters.length) / volumes.length));
  const index = Math.min(volumes.length - 1, Math.floor((Math.max(1, number) - 1) / perVolume));
  return Number(volumes[index]?.volume_number || index + 1);
}

function chaptersForVolume(volumeNumber) {
  return (state.outline.chapters || []).filter((chapter) => Number(chapter.volume_number || volumeForChapter(chapter)) === Number(volumeNumber));
}

function outlineText(chapter) {
  const detail = chapterDetail(chapter);
  return [chapter.title, detail.outline, detail.chapter_goal, detail.conflict, detail.ending_hook].filter(Boolean).join("\n");
}

async function loadChapter(chapterNumber, targetTab) {
  if (!requireWork()) return;
  try {
    const data = await api(`/api/works/${state.selectedWorkId}/chapters/${chapterNumber}`);
    state.selectedChapter = chapterNumber;
    state.currentChapter = data.chapter;
    fillChapter(data);
    renderChapterLists();
    if (targetTab) setTab(targetTab);
    log(`已载入第 ${chapterNumber} 章。`);
  } catch (error) {
    showError(error);
  }
}

function renderChapterLists() {
  const chapters = state.outline.chapters || [];
  const keyword = ($("chapterSearchInput")?.value || "").trim().toLowerCase();
  const writingList = $("writingChapterList");
  writingList.innerHTML = "";
  const filtered = chapters.filter((chapter) => !keyword || outlineText(chapter).toLowerCase().includes(keyword));
  if (!filtered.length) {
    writingList.innerHTML = '<div class="empty">暂无章节。</div>';
    return;
  }
  for (const chapter of filtered) {
    const status = chapter.status === "memory" ? "已记忆" : chapter.status === "final" ? "已定稿" : chapter.status === "draft" ? "有草稿" : "待写作";
    const item = document.createElement("div");
    item.className = `chapter-item ${Number(chapter.chapter_number) === Number(state.selectedChapter) ? "active" : ""}`;
    item.innerHTML = `
      <div class="item-title">第 ${escapeHtml(chapter.chapter_number)} 章 · ${escapeHtml(chapter.title || "未命名")}</div>
      <div class="item-meta">第 ${escapeHtml(chapter.volume_number || volumeForChapter(chapter))} 卷 · ${status}</div>
    `;
    item.addEventListener("click", () => loadChapter(Number(chapter.chapter_number), "writing"));
    writingList.appendChild(item);
  }
}

function fillChapter(data) {
  const chapter = data.chapter || {};
  state.currentChapter = chapter;
  $("writingChapterNumberInput").value = chapter.chapter_number || state.selectedChapter || 1;
  $("chapterTitleInput").value = chapter.title || "";
  $("chapterTextInput").value = chapter.final_text || chapter.draft || "";
  $("chapterOutlinePreview").textContent = formatChapterTask(chapter) || data.outline_readable || "暂无任务单。";
  $("contextPreview").textContent = data.context_error
    ? `上下文构建失败：${data.context_error}`
    : formatPreviewObject(data.context, data.context_readable, "暂无上下文。");
  $("memoryPreview").textContent = formatPreviewObject(data.memory || parseJson(chapter.memory_json, null), data.memory_readable, "暂无记忆卡。");
  $("reviewPreview").textContent = "暂无审稿结果。";
  $("draftPreview").textContent = chapter.draft || "暂无初稿。";
  $("exportStartInput").value = chapter.chapter_number || 1;
  $("exportEndInput").value = chapter.chapter_number || 1;
}

function formatChapterTask(chapter) {
  if (!chapter) return "";
  const detail = chapterDetail(chapter);
  const lines = [];
  if (detail.chapter_number) lines.push(`章节：第 ${detail.chapter_number} 章`);
  if (detail.volume_number) lines.push(`所属卷：第 ${detail.volume_number} 卷`);
  if (detail.title) lines.push(`章节名：${detail.title}`);
  if (detail.outline) lines.push(`细纲：${detail.outline}`);
  for (const [key, label] of CHAPTER_FIELDS) {
    const text = valueText(detail[key]);
    if (text) lines.push(`${label}：${text}`);
  }
  if (detail.ending_hook) lines.push(`结尾钩子：${detail.ending_hook}`);
  if (Array.isArray(detail.scene_cards) && detail.scene_cards.length) {
    lines.push("场景卡：");
    detail.scene_cards.forEach((card, index) => {
      lines.push(`${index + 1}. ${valueText(card)}`);
    });
  }
  return lines.join("\n");
}

function formatPreviewObject(value, readable, emptyText) {
  if (value && !(typeof value === "object" && !Object.keys(value).length)) {
    const formatted = formatAny(value).trim();
    if (formatted) return formatted;
  }
  return readable || emptyText;
}

function switchInspector(event) {
  const button = event.target.closest("button[data-inspector]");
  if (!button) return;
  const name = button.dataset.inspector;
  document.querySelectorAll("#inspectorTabs button").forEach((node) => node.classList.toggle("active", node === button));
  document.querySelectorAll(".inspector-pane").forEach((pane) => pane.classList.toggle("active", pane.dataset.pane === name));
}

async function generateChapter() {
  if (!requireWork()) return;
  const chapterNumber = Number($("writingChapterNumberInput").value || state.selectedChapter || 1);
  if (state.task) {
    notify("请先等待当前任务结束，或点击停止生成。", "warning");
    return;
  }
  const task = startTask("chapter", "生成当前章", `写稿 AI 正在处理第 ${chapterNumber} 章。`);
  try {
    log(`写稿 AI 正在处理第 ${chapterNumber} 章...`);
    const data = await api(`/api/works/${state.selectedWorkId}/chapters/${chapterNumber}/generate`, {
      method: "POST",
      body: { mode: $("generateModeInput").value, do_memory: false, task_id: task.id },
      signal: task.controller.signal,
    });
    if (taskWasStopped(task)) return;
    if (data.final_text || data.draft) $("chapterTextInput").value = data.final_text || data.draft;
    $("reviewPreview").textContent = formatPreviewObject(data.review, data.review_readable, "暂无审稿结果。");
    $("memoryPreview").textContent = formatPreviewObject(data.memory, data.memory_readable, "暂无记忆卡。");
    $("draftPreview").textContent = data.draft || "暂无初稿。";
    if (data.work_state) applyWorkState(data.work_state);
    await loadChapter(chapterNumber, "writing");
    $("reviewPreview").textContent = formatPreviewObject(data.review, data.review_readable, "暂无审稿结果。");
    $("memoryPreview").textContent = formatPreviewObject(data.memory, data.memory_readable, $("memoryPreview").textContent || "暂无记忆卡。");
    log(`第 ${chapterNumber} 章生成完成。`);
    notify(`第 ${chapterNumber} 章生成完成。`, "success");
  } catch (error) {
    if (taskWasStopped(task)) notify(`第 ${chapterNumber} 章生成已停止。`, "warning");
    else showError(error);
  } finally {
    finishTask("chapter");
  }
}

async function saveChapterText() {
  if (!requireWork()) return;
  const chapterNumber = Number($("writingChapterNumberInput").value || state.selectedChapter || 1);
  const currentText = $("chapterTextInput").value;
  const previousText = state.currentChapter?.final_text || "";
  const hasMemory = Boolean(String(state.currentChapter?.memory_json || "").trim());
  let invalidateMemory = false;
  if (hasMemory && currentText !== previousText) {
    invalidateMemory = await confirmAction(
      "当前章节已经生成过记忆。正文发生变化后，旧记忆可能不准确。是否清空旧记忆，之后重新生成？",
      "正文已修改",
      "清空旧记忆"
    );
  }
  try {
    const data = await api(`/api/works/${state.selectedWorkId}/chapters/${chapterNumber}`, {
      method: "PUT",
      body: {
        title: $("chapterTitleInput").value.trim(),
        final_text: currentText,
        invalidate_memory: invalidateMemory,
      },
    });
    fillChapter(data);
    log(`第 ${chapterNumber} 章最终稿已保存。`);
  } catch (error) {
    showError(error);
  }
}

async function reviseWithInstruction() {
  if (!requireWork()) return;
  const chapterNumber = Number($("writingChapterNumberInput").value || state.selectedChapter || 1);
  const instruction = $("revisionInstructionInput").value.trim();
  if (!instruction) {
    notify("请先填写修改意见。", "warning");
    return;
  }
  if (state.task) {
    notify("请先等待当前任务结束，或点击停止生成。", "warning");
    return;
  }
  const task = startTask("revise", "按意见修订", `修订 AI 正在修改第 ${chapterNumber} 章。`);
  try {
    log("修订 AI 正在按意见修改正文...");
    const data = await api(`/api/works/${state.selectedWorkId}/chapters/${chapterNumber}/revise`, {
      method: "POST",
      body: { instruction, current_text: $("chapterTextInput").value, task_id: task.id },
      signal: task.controller.signal,
    });
    if (taskWasStopped(task)) return;
    $("chapterTextInput").value = data.revised_text || $("chapterTextInput").value;
    $("revisionInstructionInput").value = "";
    log("修订完成，满意后请保存最终稿。");
    notify("修订完成，满意后请保存最终稿。", "success");
  } catch (error) {
    if (taskWasStopped(task)) notify("修订任务已停止。", "warning");
    else showError(error);
  } finally {
    finishTask("revise");
  }
}

async function generateMemory() {
  if (!requireWork()) return;
  const chapterNumber = Number($("writingChapterNumberInput").value || state.selectedChapter || 1);
  if (state.task) {
    notify("请先等待当前任务结束，或点击停止生成。", "warning");
    return;
  }
  const task = startTask("memory", "生成章节记忆", `记忆 AI 正在整理第 ${chapterNumber} 章的接力信息。`);
  try {
    const data = await api(`/api/works/${state.selectedWorkId}/chapters/${chapterNumber}/memory`, {
      method: "POST",
      body: { task_id: task.id },
      signal: task.controller.signal,
    });
    if (taskWasStopped(task)) return;
    $("memoryPreview").textContent = formatPreviewObject(data.memory, data.memory_readable, "记忆卡已入库。");
    log(`第 ${chapterNumber} 章记忆已入库。`);
    notify(`第 ${chapterNumber} 章记忆已入库。`, "success");
  } catch (error) {
    if (taskWasStopped(task)) notify("记忆任务已停止。", "warning");
    else showError(error);
  } finally {
    finishTask("memory");
  }
}

async function deleteCurrentChapter() {
  const chapterNumber = Number($("writingChapterNumberInput").value || state.selectedChapter || 1);
  await deleteChapterByNumber(chapterNumber);
}

async function deleteChapterByNumber(chapterNumber) {
  if (!requireWork()) return;
  const ok = await confirmAction(`确定删除第 ${chapterNumber} 章吗？相关正文、记忆和资料副作用也会清理。`, "删除章节", "删除");
  if (!ok) return;
  try {
    const data = await api(`/api/works/${state.selectedWorkId}/chapters/${chapterNumber}`, { method: "DELETE" });
    state.outlineSelection = { type: "full" };
    applyWorkState(data);
    log(`第 ${chapterNumber} 章已删除。`);
  } catch (error) {
    showError(error);
  }
}

function buildLibraryTabs() {
  ensureLibraryKind();
  const tabs = $("libraryTabs");
  tabs.innerHTML = "";
  for (const [kind, def] of Object.entries(LIBRARY_CATEGORIES)) {
    const button = document.createElement("button");
    button.textContent = def.label;
    button.className = kind === state.libraryKind ? "active" : "";
    button.addEventListener("click", () => {
      state.libraryKind = kind;
      state.libraryItem = null;
      renderLibraryTabsActive();
      renderLibraryList();
      renderLibraryEditor();
    });
    tabs.appendChild(button);
  }
}

function renderLibraryTabsActive() {
  ensureLibraryKind();
  [...$("libraryTabs").children].forEach((button, index) => {
    button.classList.toggle("active", Object.keys(LIBRARY_CATEGORIES)[index] === state.libraryKind);
  });
}

function renderLibraryFromWork(data) {
  ensureLibraryKind();
  state.libraryData = {
    characters: data.characters || [],
    world_rules: data.world_rules || [],
    plot_threads: data.plot_threads || [],
    timeline: data.timeline || [],
  };
  renderLibraryList();
  renderLibraryEditor();
}

async function refreshLibrary() {
  if (!requireWork()) return;
  ensureLibraryKind();
  try {
    const data = await api(`/api/works/${state.selectedWorkId}/library`);
    renderLibraryFromWork(data);
    log("资料库已刷新。");
  } catch (error) {
    showError(error);
  }
}

function libraryItems(kind = state.libraryKind) {
  ensureLibraryKind();
  const data = state.libraryData || {};
  return data[kind] || [];
}

function ensureLibraryKind() {
  if (LIBRARY_CATEGORIES[state.libraryKind]) return;
  state.libraryKind = Object.keys(LIBRARY_CATEGORIES)[0] || "characters";
  state.libraryItem = null;
}

function renderLibraryList() {
  ensureLibraryKind();
  const list = $("libraryList");
  const kind = state.libraryKind;
  const def = LIBRARY_CATEGORIES[kind];
  const keyword = ($("librarySearchInput").value || "").trim().toLowerCase();
  const items = libraryItems(kind).filter((item) => !keyword || formatRecord(item).toLowerCase().includes(keyword));
  list.innerHTML = "";
  if (!items.length) {
    list.innerHTML = '<div class="empty">暂无资料。</div>';
    return;
  }
  if (!state.libraryItem || !items.some((item) => item.id === state.libraryItem.id)) {
    state.libraryItem = items[0];
  }
  for (const item of items) {
    const node = document.createElement("div");
    node.className = `library-item ${state.libraryItem && item.id === state.libraryItem.id ? "active" : ""}`;
    node.innerHTML = `<div class="item-title">${escapeHtml(def.title(item))}</div><div class="item-meta">ID ${escapeHtml(item.id || "-")}</div>`;
    node.addEventListener("click", () => {
      state.libraryItem = item;
      renderLibraryList();
      renderLibraryEditor();
    });
    list.appendChild(node);
  }
  renderLibraryEditor();
}

function renderLibraryEditor() {
  ensureLibraryKind();
  const kind = state.libraryKind;
  const def = LIBRARY_CATEGORIES[kind];
  if (!def) {
    $("libraryEditorTitle").textContent = "资料详情";
    $("libraryEditorHint").textContent = "请选择左侧资料分类。";
    $("libraryEditor").innerHTML = '<div class="empty">暂无可编辑资料。</div>';
    return;
  }
  const item = state.libraryItem || {};
  $("libraryEditorTitle").textContent = `${def.label}详情`;
  $("libraryEditorHint").textContent = def.help || (def.readonly ? "该分类只读，用于追踪程序自动写入的记录。" : "修改后点击“保存当前资料”。");
  const editor = $("libraryEditor");
  editor.innerHTML = `
    <div class="library-form">
      ${def.fields.map(([key, label, type]) => fieldHtml(key, label, item[key], type, def.readonly)).join("")}
    </div>
  `;
}

function fieldHtml(key, label, value, type = "input", readonly = false) {
  const attr = readonly ? "readonly disabled" : "";
  if (type === "textarea") {
    return `<label>${label}<textarea data-lib-field="${key}" rows="4" ${attr}>${escapeHtml(value || "")}</textarea></label>`;
  }
  return `<label>${label}<input data-lib-field="${key}" type="${type}" value="${escapeHtml(value || "")}" ${attr}></label>`;
}

function addLibraryItem() {
  ensureLibraryKind();
  const def = LIBRARY_CATEGORIES[state.libraryKind];
  if (def.readonly) {
    notify("当前分类是只读记录，不能手动新增。", "warning");
    return;
  }
  state.libraryItem = {};
  renderLibraryEditor();
}

async function saveLibraryItem() {
  if (!requireWork()) return;
  ensureLibraryKind();
  const kind = state.libraryKind;
  const def = LIBRARY_CATEGORIES[kind];
  if (def.readonly) {
    notify("当前分类是只读记录，不能保存。", "warning");
    return;
  }
  const body = { ...(state.libraryItem || {}) };
  $("libraryEditor").querySelectorAll("[data-lib-field]").forEach((node) => {
    body[node.dataset.libField] = node.type === "number" && node.value ? Number(node.value) : node.value;
  });
  try {
    const data = await api(`/api/works/${state.selectedWorkId}/library/${kind}`, { method: "POST", body });
    renderLibraryFromWork(data);
    log("资料已保存。");
  } catch (error) {
    showError(error);
  }
}

async function deleteLibraryItem() {
  if (!requireWork()) return;
  ensureLibraryKind();
  const kind = state.libraryKind;
  const def = LIBRARY_CATEGORIES[kind];
  if (def.readonly || def.single) {
    notify("当前分类不支持删除。", "warning");
    return;
  }
  if (!state.libraryItem?.id) return;
  const ok = await confirmAction("确定删除当前资料吗？", "删除资料", "删除");
  if (!ok) return;
  try {
    const data = await api(`/api/works/${state.selectedWorkId}/library/${kind}/${state.libraryItem.id}`, { method: "DELETE" });
    state.libraryItem = null;
    renderLibraryFromWork(data);
    log("资料已删除。");
  } catch (error) {
    showError(error);
  }
}

async function exportWork() {
  if (!requireWork()) return;
  try {
    const body = {
      scope: $("exportScopeInput").value,
      format: $("exportFormatInput").value,
      chapter_number: Number($("exportStartInput").value || state.selectedChapter || 1),
      start_chapter: Number($("exportStartInput").value || 1),
      end_chapter: Number($("exportEndInput").value || 1),
      include_draft: $("includeDraftInput").checked,
    };
    const data = await api(`/api/works/${state.selectedWorkId}/export`, { method: "POST", body });
    $("exportResult").textContent = `导出完成：\n${data.path}`;
    log("导出完成。");
  } catch (error) {
    showError(error);
  }
}

function updateExportDir(data) {
  $("exportDirText").textContent = data.export_dir || "未选择文章。";
  if (data.export_dir) $("exportResult").textContent = `默认导出位置：${data.export_dir}`;
}

async function chooseExportDir() {
  if (!requireWork()) return;
  try {
    const data = await api(`/api/works/${state.selectedWorkId}/export-dir/choose`, { method: "POST" });
    $("exportDirText").textContent = data.export_dir;
    log("已选择导出位置。");
  } catch (error) {
    showError(error);
  }
}

async function openExportDir() {
  if (!requireWork()) return;
  try {
    const data = await api(`/api/works/${state.selectedWorkId}/export-dir/open`, { method: "POST" });
    $("exportDirText").textContent = data.export_dir;
    log("已打开导出位置。");
  } catch (error) {
    showError(error);
  }
}

async function resetExportDir() {
  if (!requireWork()) return;
  try {
    const data = await api(`/api/works/${state.selectedWorkId}/export-dir/reset`, { method: "POST" });
    $("exportDirText").textContent = data.export_dir;
    log("导出位置已恢复默认。");
  } catch (error) {
    showError(error);
  }
}

function fillConfigForm() {
  const config = state.config || {};
  const agents = config.agent_models || {};
  $("modelProviderInput").value = config.model_provider || config.provider || "";
  $("baseUrlInput").value = config.base_url || "";
  $("wireApiInput").value = config.wire_api || "chat_completions";
  $("defaultModelInput").value = config.default_model || "";
  $("reviewModelInput").value = config.review_model || "";
  $("plannerModelInput").value = agents.planner || "";
  $("writerModelInput").value = agents.writer || "";
  $("reviewerModelInput").value = agents.reviewer || "";
  $("reviserModelInput").value = agents.reviser || "";
  $("memoryModelInput").value = agents.memory || "";
  $("apiKeyInput").value = config.api_key || "";
  $("timeoutInput").value = config.timeout || 300;
  $("maxRetriesInput").value = config.max_retries || 0;
  $("maxOutputTokensInput").value = config.max_output_tokens || 12000;
  $("contextWindowInput").value = config.model_context_window || 1000000;
  $("autoCompactInput").value = config.model_auto_compact_token_limit || 900000;
  $("reasoningEffortInput").value = config.model_reasoning_effort || "";
  $("mockModeInput").checked = Boolean(config.mock_mode);
  $("disableStorageInput").checked = Boolean(config.disable_response_storage);
  $("systemProxyInput").checked = Boolean(config.use_system_proxy);
  $("proxyUrlInput").value = config.proxy_url || "";
  const mainModel = config.default_model || "";
  $("singleModelInput").checked = ["planner", "writer", "reviewer", "reviser", "memory"].every((name) => !agents[name] || agents[name] === mainModel);
  setApiKeyVisible(false);
  syncSingleModelFields();
}

function setApiKeyVisible(visible) {
  const input = $("apiKeyInput");
  const button = $("toggleApiKeyBtn");
  input.type = visible ? "text" : "password";
  button.textContent = visible ? "隐藏" : "显示";
  button.setAttribute("aria-pressed", visible ? "true" : "false");
}

function toggleApiKeyVisibility() {
  setApiKeyVisible($("apiKeyInput").type === "password");
}

function syncSingleModelFields() {
  const enabled = $("singleModelInput").checked;
  const mainModel = $("defaultModelInput").value.trim();
  for (const id of ["reviewModelInput", "plannerModelInput", "writerModelInput", "reviewerModelInput", "reviserModelInput", "memoryModelInput"]) {
    $(id).disabled = enabled;
    if (enabled) $(id).value = mainModel;
  }
}

function collectConfigForm() {
  const provider = $("modelProviderInput").value.trim() || "OpenAI";
  const mainModel = $("defaultModelInput").value.trim();
  const single = $("singleModelInput").checked;
  return {
    provider,
    model_provider: provider,
    base_url: $("baseUrlInput").value.trim(),
    wire_api: $("wireApiInput").value,
    requires_openai_auth: true,
    api_key: $("apiKeyInput").value.trim(),
    default_model: mainModel,
    review_model: single ? mainModel : $("reviewModelInput").value.trim(),
    model_reasoning_effort: $("reasoningEffortInput").value,
    disable_response_storage: $("disableStorageInput").checked,
    timeout: Number($("timeoutInput").value || 300),
    max_retries: Number($("maxRetriesInput").value || 0),
    max_output_tokens: Number($("maxOutputTokensInput").value || 12000),
    model_context_window: Number($("contextWindowInput").value || 1000000),
    model_auto_compact_token_limit: Number($("autoCompactInput").value || 900000),
    use_system_proxy: $("systemProxyInput").checked,
    proxy_url: $("proxyUrlInput").value.trim(),
    mock_mode: $("mockModeInput").checked,
    network_access: "enabled",
    windows_wsl_setup_acknowledged: true,
    agent_models: single
      ? { planner: mainModel, writer: mainModel, reviewer: mainModel, reviser: mainModel, memory: mainModel }
      : {
          planner: $("plannerModelInput").value.trim(),
          writer: $("writerModelInput").value.trim(),
          reviewer: $("reviewerModelInput").value.trim(),
          reviser: $("reviserModelInput").value.trim(),
          memory: $("memoryModelInput").value.trim(),
        },
  };
}

async function saveConfig() {
  try {
    state.config = await api("/api/config", { method: "PUT", body: collectConfigForm() });
    fillConfigForm();
    await loadHealth();
    $("configResult").textContent = "设置已保存，会在下一次 AI 调用时生效。";
    log("设置已保存。");
  } catch (error) {
    showError(error);
  }
}

async function testApi() {
  try {
    $("configResult").textContent = "正在保存设置并测试 API...";
    state.config = await api("/api/config", { method: "PUT", body: collectConfigForm() });
    fillConfigForm();
    await loadHealth();
    const data = await api("/api/config/test", { method: "POST" });
    $("configResult").textContent = data.message || "连接成功。";
    log("API 测试完成。");
  } catch (error) {
    $("configResult").textContent = error.message || "测试失败。";
    showError(error);
  }
}

function formatRecord(record) {
  if (!record) return "";
  return Object.entries(record)
    .filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== "")
    .map(([key, value]) => `${labelFor(key)}：${valueText(value)}`)
    .join("\n");
}

function formatAny(value) {
  value = parsePossibleJson(value);
  if (Array.isArray(value)) {
    return value.map((item, index) => {
      const text = formatAny(item);
      return text.includes("\n") ? `${index + 1}.\n${text}` : `${index + 1}. ${text}`;
    }).join("\n");
  }
  if (value && typeof value === "object") return formatRecord(value);
  return String(value || "");
}

function valueText(value) {
  value = parsePossibleJson(value);
  if (Array.isArray(value)) return value.map((item) => valueText(item)).filter(Boolean).join("\n");
  if (value && typeof value === "object") return formatRecord(value);
  const text = String(value || "");
  return VALUE_LABELS[text.toLowerCase()] || text;
}

function parsePossibleJson(value) {
  if (typeof value !== "string") return value;
  const text = value.trim();
  if (!text.startsWith("{") && !text.startsWith("[")) return value;
  return parseJson(text, value);
}

function arrayText(value) {
  return Array.isArray(value) ? value.join("\n") : value || "";
}

function lines(value) {
  return String(value || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
}

function labelFor(key) {
  const labels = {
    ability: "能力",
    ability_changes: "能力变化",
    action: "动作",
    active_object: "承接物件/证据",
    actual_resolve_chapter: "实际回收章节",
    affected_characters: "影响人物",
    after: "变化后",
    agent_name: "智能体",
    arc_notes: "成长备注",
    arc_stage: "成长阶段",
    before: "变化前",
    category: "类别",
    chapter: "章节",
    chapter_goal: "本章目标",
    title: "标题",
    summary: "摘要",
    role: "定位",
    name: "姓名",
    personality: "性格",
    goal: "目标",
    content: "内容",
    absolute_red_lines: "绝对红线",
    context: "上下文",
    current_characters: "当前人物",
    current_conflict: "当前冲突",
    current_fear: "当前恐惧",
    current_goal: "当前目标",
    current_scene: "当前场景",
    current_state: "当前状态",
    current_time: "当前时间",
    description: "描述",
    details: "详情",
    ending_hook: "结尾钩子",
    ending_style: "结尾类型",
    event: "事件",
    first_chapter: "首次出现章节",
    forbidden_jump: "禁止跳转",
    forbidden_opening: "禁止开头",
    future_constraint: "后续约束",
    handoff: "下一章接力棒",
    historical_updates: "史实更新",
    impact: "影响",
    last_external_action: "末尾外部动作",
    last_spoken_line: "末尾关键对白",
    limitations: "限制",
    location: "地点",
    minimal_memory_pack: "最简记忆包",
    new_foreshadows: "新增伏笔",
    new_information: "新增信息",
    next_first_paragraph_task: "下一章第一段任务",
    next_opening_must_continue: "下一章开头必须承接",
    note: "备注",
    notes: "备注",
    old_value: "原值",
    open_conflict: "未闭合冲突",
    outline: "细纲",
    planned_resolve_chapter: "计划回收章节",
    problem: "问题",
    problems: "问题",
    reason: "原因",
    relationship: "关系",
    relationship_mainline: "关系主线",
    relationship_changes: "关系变化",
    relationship_stage: "关系阶段",
    resolved_foreshadows: "回收伏笔",
    review: "审稿",
    rule_content: "规则内容",
    rule_name: "规则名称",
    scene: "场景",
    scene_cards: "场景卡",
    secret: "秘密",
    secret_exposure: "秘密暴露",
    source: "来源",
    status: "状态",
    story_time: "故事时间",
    suggestions: "建议",
    target: "对象",
    protagonist_fantasy: "主角爽点",
    escalation_ladder: "升级阶梯",
    target_name: "对象名称",
    target_type: "对象类型",
    time: "时间",
    timeline_events: "时间线事件",
    type: "类型",
    unresolved_questions: "未解决问题",
    created_at: "创建时间",
    updated_at: "更新时间",
    chapter_number: "章节",
    volume_number: "所属卷",
    character: "人物",
    characters: "人物",
    character_changes: "人物变化",
    character_state_updates: "人物状态更新",
    characters_involved: "涉及人物",
  };
  return labels[key] || fallbackLabel(key);
}

const VALUE_LABELS = {
  active: "进行中",
  closed: "已关闭",
  none: "无",
  open: "未结束",
  pending: "待处理",
  resolved: "已回收",
  unknown: "未知",
};

function fallbackLabel(key) {
  const parts = String(key || "").split("_").filter(Boolean);
  const mapped = parts.map((part) => LABEL_PARTS[part]).filter(Boolean);
  return mapped.length ? mapped.join("") : "其他字段";
}

const LABEL_PARTS = {
  ability: "能力",
  active: "当前",
  action: "动作",
  after: "后",
  before: "前",
  card: "卡",
  chapter: "章节",
  character: "人物",
  conflict: "冲突",
  content: "内容",
  current: "当前",
  detail: "详情",
  emotion: "情绪",
  ending: "结尾",
  event: "事件",
  fact: "事实",
  facts: "事实",
  field: "字段",
  first: "首次",
  foreshadow: "伏笔",
  foreshadows: "伏笔",
  forbidden: "禁止",
  future: "后续",
  goal: "目标",
  hook: "钩子",
  impact: "影响",
  item: "条目",
  last: "最近",
  memory: "记忆",
  name: "名称",
  next: "下一章",
  note: "备注",
  notes: "备注",
  opening: "开头",
  outline: "大纲",
  paragraph: "段落",
  plan: "计划",
  planned: "计划",
  profile: "档案",
  question: "问题",
  questions: "问题",
  relation: "关系",
  relationship: "关系",
  resolve: "回收",
  resolved: "已回收",
  rhythm: "节奏",
  rule: "规则",
  scene: "场景",
  score: "评分",
  spoken: "对白",
  state: "状态",
  status: "状态",
  story: "故事",
  style: "风格",
  summary: "摘要",
  target: "对象",
  task: "任务",
  text: "文本",
  time: "时间",
  timeline: "时间线",
  title: "标题",
  type: "类型",
  update: "更新",
  updates: "更新",
  value: "值",
};

function updateProgress() {
  const track = $("progressTrack");
  if (!track) return;
  if (!state.selectedWorkId) {
    $("progressTitle").textContent = "等待选择文章";
    track.innerHTML = `
      <div class="workflow-card waiting">
        <div class="workflow-row compact">
          <div>
            <div class="workflow-title">当前流程：未开始</div>
            <div class="workflow-desc">先从左侧新建或选择文章。</div>
          </div>
          <span class="workflow-badge">等待选择</span>
        </div>
      </div>
    `;
    return;
  }
  const data = state.workData || {};
  const workflowState = data.workflow_state || {};
  const chapters = state.outline.chapters || [];
  const contractDone = Boolean(workflowState.has_contract || Object.values(data.book_contract || {}).some((value) => String(value || "").trim()));
  const settingDone = Boolean(workflowState.has_settings ?? (data.project_readable || (data.characters || []).length || (data.world_rules || []).length));
  const outlineDone = Boolean(workflowState.has_outline ?? (state.outline.full_outline || (state.outline.volume_outline || []).length));
  const plannedCount = Number(workflowState.planned_count ?? chapters.length);
  const draftCount = Number(workflowState.draft_count ?? chapters.filter((chapter) => ["draft", "final", "memory"].includes(chapter.status)).length);
  const finalCount = Number(workflowState.final_count ?? chapters.filter((chapter) => ["final", "memory"].includes(chapter.status)).length);
  const memoryCount = Number(workflowState.memory_count ?? chapters.filter((chapter) => chapter.status === "memory").length);
  const currentChapter = chapterByNumber(state.selectedChapter) || chapters.find((chapter) => !["memory"].includes(chapter.status)) || chapters[0];
  const currentLabel = currentChapter
    ? `第 ${currentChapter.chapter_number} 章`
    : "未拆章";
  const total = Math.max(plannedCount, 1);
  const plannedProgress = plannedCount ? 1 : 0;
  const progress = Math.round((
    (settingDone ? 1 : 0)
    + (outlineDone ? 1 : 0)
    + plannedProgress
    + (draftCount / total)
    + (finalCount / total)
    + (memoryCount / total)
  ) / 6 * 100);
  const flow = currentFlowState({
    contractDone,
    settingDone,
    outlineDone,
    plannedCount,
    draftCount,
    finalCount,
    memoryCount,
    currentChapter,
  });
  const steps = [
    {
      label: "设定",
      value: settingDone ? "完成" : "待确认",
      done: settingDone && contractDone,
    },
    {
      label: "大纲",
      value: outlineDone ? "完成" : "待生成",
      done: outlineDone,
    },
    {
      label: "细纲",
      value: `${plannedCount} 章`,
      done: plannedCount > 0,
    },
    {
      label: "正文",
      value: `${draftCount}/${plannedCount || 0}`,
      done: plannedCount > 0 && draftCount >= plannedCount,
    },
    {
      label: "定稿",
      value: `${finalCount}/${plannedCount || 0}`,
      done: plannedCount > 0 && finalCount >= plannedCount,
    },
    {
      label: "记忆",
      value: `${memoryCount}/${plannedCount || 0}`,
      done: plannedCount > 0 && memoryCount >= plannedCount,
    },
  ];
  $("progressTitle").textContent = `当前流程：${flow.title}`;
  track.innerHTML = `
    <div class="workflow-card ${flow.tone}">
      <div class="workflow-row compact">
        <div>
          <div class="workflow-title">${escapeHtml(flow.title)}</div>
          <div class="workflow-desc">${escapeHtml(flow.description)}</div>
        </div>
        <span class="workflow-badge">${escapeHtml(flow.badge)}</span>
      </div>
      <div class="workflow-progress-line">
        <div class="workflow-bar" aria-label="流程进度">
          <span style="width: ${progress}%"></span>
        </div>
        <strong>${progress}%</strong>
      </div>
      <div class="workflow-meta">当前动作：${escapeHtml(flow.action)} · 最近检查点：${escapeHtml(currentLabel)} / ${escapeHtml(currentChapter ? chapterStatusText(currentChapter.status) : "待规划")}</div>
      <div class="workflow-breakdown compact">
        ${steps.map((step) => `
          <div class="workflow-metric ${step.done ? "done" : ""}">
            <span>${escapeHtml(step.label)}</span>
            <b>${escapeHtml(step.value)}</b>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

function chapterStatusText(status) {
  if (status === "memory") return "记忆已入库";
  if (status === "final") return "最终稿已保存";
  if (status === "draft") return "已有草稿";
  return "等待写作";
}

function currentFlowState(input) {
  if (state.task) {
    return {
      title: state.task.title,
      description: state.task.stopped ? "已请求停止，迟到结果会被丢弃。" : state.task.detail,
      action: state.task.stopped ? "等待请求结束，迟到结果不会写入界面。" : state.task.detail,
      badge: state.task.stopped ? "停止中" : "运行中",
      tone: state.task.stopped ? "waiting" : "running",
    };
  }
  if (!input.settingDone) {
    return {
      title: "设定确认",
      description: "先保存基础信息，生成设定草稿，并确认采用入库。",
      action: "填写创意、题材和风格，点击生成设定草稿。",
      badge: "等待确认",
      tone: "waiting",
    };
  }
  if (!input.contractDone) {
    return {
      title: "整本契约",
      description: "基础设定已经可用，建议先写清楚主角爽点、升级阶梯、关系主线和绝对红线。",
      action: "在设定页填写整本契约，并点击保存基础信息。",
      badge: "待补齐",
      tone: "waiting",
    };
  }
  if (!input.outlineDone) {
    return {
      title: "全书大纲",
      description: "设定已经可用，下一步生成或编辑全书大纲。",
      action: "进入大纲与细纲页，生成全书大纲。",
      badge: "待推进",
      tone: "default",
    };
  }
  if (!input.plannedCount) {
    return {
      title: "章节细纲",
      description: "大纲已经可用，但还没有章节任务单。",
      action: "生成章节细纲，先拆出可写作的章节任务单。",
      badge: "待拆章",
      tone: "default",
    };
  }
  if (input.draftCount < input.plannedCount) {
    return {
      title: "正文生成",
      description: `已有 ${input.plannedCount} 章任务单，正文完成 ${input.draftCount} 章。`,
      action: `继续生成第 ${input.draftCount + 1} 章正文。`,
      badge: "待写作",
      tone: "default",
    };
  }
  if (input.finalCount < input.plannedCount) {
    return {
      title: "最终稿确认",
      description: `草稿已覆盖当前规划章节，仍有 ${input.plannedCount - input.finalCount} 章未定稿。`,
      action: `确认并保存第 ${input.finalCount + 1} 章最终稿。`,
      badge: "等待确认",
      tone: "waiting",
    };
  }
  if (input.memoryCount < input.plannedCount) {
    return {
      title: "记忆入库",
      description: `最终稿已保存，仍有 ${input.plannedCount - input.memoryCount} 章未生成记忆。`,
      action: `为第 ${input.memoryCount + 1} 章生成记忆并入库。`,
      badge: "待入库",
      tone: "default",
    };
  }
  return {
    title: "章节流程完成",
    description: "当前规划章节已经完成正文、定稿和记忆入库。",
    action: "可以继续规划后续章节，或进入导出页导出文稿。",
    badge: "已完成",
    tone: "done",
  };
}

init().catch(showError);
