export type PageKey = "project" | "outline" | "writing" | "library" | "export" | "records" | "settings";

export interface Work {
  id: number;
  title: string;
  idea?: string;
  genre?: string;
  platform?: string;
  target_words?: number;
  style?: string;
  settings_locked?: number | boolean;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface ChapterSummary {
  id?: number;
  chapter_number: number;
  title?: string;
  status?: string;
  summary?: string;
  ending_hook?: string;
  volume_number?: number;
  volume_title?: string;
  outline?: string;
  outline_json?: string | Record<string, unknown>;
  scene_cards_json?: string | unknown[];
  updated_at?: string;
  [key: string]: unknown;
}

export interface Chapter extends ChapterSummary {
  final_text?: string;
  draft?: string;
  problem_draft?: string;
  memory_json?: string | Record<string, unknown>;
  revision?: number;
  handoff?: string;
  title_source?: string;
  title_locked?: number | boolean;
  title_reason?: string;
  title_status?: "provisional" | "pending" | "final" | "manual" | string;
  title_quality_json?: string | Record<string, unknown>;
}

export interface OutlineState {
  full_outline: string;
  volume_outline: Array<Record<string, unknown>>;
  chapters: ChapterSummary[];
}

export interface WorkState {
  work: Work;
  works?: Work[];
  chapters?: ChapterSummary[];
  book_contract?: Record<string, unknown>;
  workflow_state?: Record<string, unknown>;
  project_readable?: string;
  outline?: OutlineState;
  export_dir?: string;
  default_export_dir?: string;
  custom_export_dir?: boolean;
}

export interface TaskState {
  id: string;
  kind: string;
  title: string;
  detail: string;
  startedAt: number;
  remoteSeen?: boolean;
  controller: AbortController;
  workId?: number;
  chapterNumber?: number;
}

export interface Notice {
  id: number;
  message: string;
  tone: "info" | "success" | "warning" | "danger";
}

export interface PendingResult {
  id: number;
  workId: number;
  chapterNumber: number;
  title: string;
  detail: string;
}
