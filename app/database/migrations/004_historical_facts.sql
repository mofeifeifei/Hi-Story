CREATE TABLE IF NOT EXISTS historical_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  work_id INTEGER NOT NULL,
  chapter_number INTEGER,
  category TEXT,
  content TEXT,
  chapter_impact TEXT,
  future_constraint TEXT,
  created_at TEXT,
  FOREIGN KEY(work_id) REFERENCES works(id) ON DELETE CASCADE
);
