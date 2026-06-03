CREATE TABLE IF NOT EXISTS task_runs (
  id TEXT PRIMARY KEY,
  work_id INTEGER,
  chapter_id INTEGER,
  kind TEXT,
  title TEXT,
  status TEXT,
  stage TEXT,
  input_json TEXT,
  output_preview TEXT,
  error TEXT,
  created_at TEXT,
  updated_at TEXT,
  finished_at TEXT,
  FOREIGN KEY(work_id) REFERENCES works(id) ON DELETE CASCADE,
  FOREIGN KEY(chapter_id) REFERENCES chapters(id) ON DELETE SET NULL
);
