export const statusLabels: Record<string, string> = {
  outline: "已有细纲",
  draft: "初稿",
  problem_draft: "问题稿",
  final: "最终稿",
  memory: "已入库",
  running: "进行中",
  done: "已完成",
  success: "成功",
  completed: "已完成",
  failed: "失败",
  error: "错误",
  interrupted: "意外中断",
  cancelled: "已停止",
  cancelling: "正在停止",
};

export function statusText(value: unknown): string {
  const key = String(value || "").toLowerCase();
  return statusLabels[key] || (key ? String(value) : "未开始");
}

export function wordCount(text: string): number {
  return String(text || "").replace(/\s/g, "").length;
}

export function safeJson(value: unknown, fallback: unknown = {}): any {
  if (typeof value !== "string") return value ?? fallback;
  if (!value.trim()) return fallback;
  try { return JSON.parse(value); } catch { return fallback; }
}

export function readable(value: unknown): string {
  if (value == null || value === "") return "暂无内容。";
  if (typeof value === "string") {
    const parsed = safeJson(value, value);
    if (parsed === value) return value;
    return readable(parsed);
  }
  if (Array.isArray(value)) return value.map((item, index) => `${index + 1}. ${readable(item)}`).join("\n");
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .filter(([key]) => !hiddenFields.has(key))
      .filter(([, item]) => item !== null && item !== undefined && String(item).trim() !== "")
      .map(([key, item]) => `${fieldLabel(key)}：${localizedValue(key, item)}`)
      .join("\n");
  }
  return String(value);
}

const fieldLabels: Record<string, string> = {
  title: "标题", summary: "摘要", outline: "细纲", chapter_goal: "本章目标", conflict: "主要冲突",
  chapter_payoff: "本章回报", ending_hook: "章尾动作", handoff: "下一章承接", continuity_debt: "承接任务",
  genre_core: "题材核心", reader_promise: "读者承诺", conflict_engine: "冲突发动机",
  opening_preference: "开头偏好", avoid: "避免事项", language_texture: "语言质感",
  status: "状态", reason: "原因", carry_over: "遗留线索", should_transition: "是否换卷",
  from_volume: "原卷", to_volume: "目标卷", agent_name: "智能体", prompt_name: "提示词",
  created_at: "开始时间", finished_at: "完成时间", output_preview: "结果", error: "错误",
  updated_at: "更新时间", duration_seconds: "用时（秒）", kind: "任务类型", stage: "执行阶段",
  model: "模型", chapter_number: "章节", estimated_input_tokens: "输入令牌估算",
  estimated_output_tokens: "输出令牌估算", estimated_total_tokens: "令牌总量估算", elapsed_seconds: "模型用时（秒）",
  input_chars: "输入字符数", output_chars: "输出字符数", finish_reason: "结束原因", message: "说明", volume_number: "所属卷",
  min_chapters: "最少章节", target_chapters: "目标章节", soft_max_chapters: "软上限",
  hard_max_chapters: "硬上限", exit_condition: "退出条件", required_milestones: "必经里程碑",
  record_type: "记录类型", input_json: "输入摘要", revision_check: "修订检查",
  opening_hook: "开篇触发", reader_expectation: "读者期待", main_scene: "核心场景",
  characters_present: "出场人物", clues: "线索推进", new_information: "新增信息",
  character_change: "人物变化", foreshadowing: "伏笔安排", emotional_turn: "情绪转折",
  emotional_rhythm: "情绪节奏", forbidden: "本章禁区", scene_cards: "场景任务",
  scene_goal: "场景目标", obstacle: "阻碍", information_gain: "信息增量",
  emotional_shift: "情绪变化", scene_exit: "场景出口",
};

const hiddenFields = new Set(["id", "work_id", "chapter_id", "recordType"]);
const internalValues: Record<string, string> = {
  task: "系统任务", agent: "模型调用", writer: "正文写作", reviewer: "质量检查", reviser: "正文修订",
  planner: "大纲策划", memory: "记忆整理", chapter: "正文生成", chapterOutlines: "细纲生成",
  standard: "正式生成", fast: "快速试稿", success: "成功", completed: "已完成", interrupted: "意外中断",
  web_user_instruction_rejected_style: "未通过验收的候选稿", web_user_instruction_candidate_style: "修订候选稿", web_user_instruction_first_pass: "第一轮修订稿",
};

function localizedValue(key: string, value: unknown): string {
  const raw = String(value ?? "");
  if (["agent_name", "prompt_name", "kind", "stage", "record_type", "status"].includes(key)) {
    const normalized = raw.replace(/_prompt(?:\.md)?$/i, "");
    return internalValues[raw] || internalValues[normalized] || statusText(raw);
  }
  return readable(value);
}

export function recordTitle(value: unknown): string {
  const raw = String(value || "操作记录");
  return internalValues[raw] || internalValues[raw.replace(/_prompt(?:\.md)?$/i, "")] || raw;
}

export function fieldLabel(key: string): string {
  return fieldLabels[key] || "其他信息";
}

export function formatTime(value: unknown): string {
  if (!value) return "";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN", { hour12: false });
}
