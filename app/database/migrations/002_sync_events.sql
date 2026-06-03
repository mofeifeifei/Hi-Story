CREATE TABLE IF NOT EXISTS sync_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  work_id INTEGER NOT NULL,
  chapter_id INTEGER,
  chapter_number INTEGER,
  source TEXT,
  target_type TEXT,
  target_id INTEGER,
  target_name TEXT,
  action TEXT,
  details TEXT,
  created_at TEXT,
  FOREIGN KEY(work_id) REFERENCES works(id) ON DELETE CASCADE,
  FOREIGN KEY(chapter_id) REFERENCES chapters(id) ON DELETE SET NULL
);
