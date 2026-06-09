PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS works (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT,
  idea TEXT,
  genre TEXT,
  platform TEXT,
  target_words INTEGER,
  style TEXT,
  summary TEXT,
  reader_profile TEXT,
  forbidden_tropes TEXT,
  protagonist_preference TEXT,
  core_selling_points TEXT,
  book_bible_json TEXT,
  book_contract_json TEXT,
  full_outline TEXT,
  volume_outline TEXT,
  locked_facts TEXT,
  settings_locked INTEGER DEFAULT 0,
  created_at TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS characters (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  work_id INTEGER NOT NULL,
  name TEXT,
  role TEXT,
  aliases TEXT,
  personality TEXT,
  goal TEXT,
  secret TEXT,
  speaking_style TEXT,
  relationship TEXT,
  locked_rules TEXT,
  current_goal TEXT,
  current_fear TEXT,
  current_state TEXT,
  relationship_stage TEXT,
  secret_exposure TEXT,
  arc_stage TEXT,
  arc_notes TEXT,
  last_changed_chapter INTEGER,
  created_at TEXT,
  updated_at TEXT,
  FOREIGN KEY(work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS world_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  work_id INTEGER NOT NULL,
  rule_name TEXT,
  rule_content TEXT,
  limitations TEXT,
  forbidden_changes TEXT,
  created_at TEXT,
  updated_at TEXT,
  FOREIGN KEY(work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS historical_profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  work_id INTEGER NOT NULL UNIQUE,
  dynasty TEXT,
  period TEXT,
  year_range TEXT,
  current_ruler TEXT,
  historical_stage TEXT,
  political_context TEXT,
  official_system TEXT,
  central_official_system TEXT,
  local_administration TEXT,
  noble_titles TEXT,
  exam_system TEXT,
  military_system TEXT,
  military_ranks TEXT,
  weapons TEXT,
  social_order TEXT,
  daily_life TEXT,
  currency TEXT,
  measurements TEXT,
  geo_notes TEXT,
  travel_speed TEXT,
  communication_speed TEXT,
  language_style TEXT,
  address_terms TEXT,
  taboo_words TEXT,
  allowed_fiction TEXT,
  fiction_boundary TEXT,
  locked_facts TEXT,
  source_notes TEXT,
  created_at TEXT,
  updated_at TEXT,
  FOREIGN KEY(work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS historical_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  work_id INTEGER NOT NULL,
  chapter_number INTEGER,
  category TEXT,
  name TEXT,
  content TEXT,
  source_type TEXT,
  certainty TEXT,
  fictionalized INTEGER DEFAULT 0,
  chapter_impact TEXT,
  future_constraint TEXT,
  created_at TEXT,
  updated_at TEXT,
  FOREIGN KEY(work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chapters (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  work_id INTEGER NOT NULL,
  chapter_number INTEGER NOT NULL,
  title TEXT,
  outline TEXT,
  outline_json TEXT,
  scene_cards_json TEXT,
  draft TEXT,
  final_text TEXT,
  summary TEXT,
  ending_hook TEXT,
  handoff TEXT,
  memory_json TEXT,
  status TEXT DEFAULT 'outline',
  created_at TEXT,
  updated_at TEXT,
  UNIQUE(work_id, chapter_number),
  FOREIGN KEY(work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS plot_threads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  work_id INTEGER NOT NULL,
  first_chapter INTEGER,
  content TEXT,
  status TEXT DEFAULT 'open',
  planned_resolve_chapter INTEGER,
  actual_resolve_chapter INTEGER,
  created_at TEXT,
  updated_at TEXT,
  FOREIGN KEY(work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS timeline (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  work_id INTEGER NOT NULL,
  chapter_number INTEGER,
  story_time TEXT,
  event TEXT,
  characters_involved TEXT,
  created_at TEXT,
  FOREIGN KEY(work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chapter_id INTEGER NOT NULL,
  continuity_score INTEGER,
  character_score INTEGER,
  emotion_score INTEGER,
  rhythm_score INTEGER,
  foreshadow_score INTEGER,
  payoff_score INTEGER,
  hook_score INTEGER,
  historical_score INTEGER,
  repeat_risk TEXT,
  problems TEXT,
  suggestions TEXT,
  template_hits TEXT,
  risk_flags TEXT,
  created_at TEXT,
  FOREIGN KEY(chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chapter_id INTEGER NOT NULL,
  version_name TEXT,
  content TEXT,
  created_at TEXT,
  FOREIGN KEY(chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chapter_notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  work_id INTEGER NOT NULL,
  chapter_number INTEGER,
  note_type TEXT,
  content TEXT,
  created_at TEXT,
  updated_at TEXT,
  FOREIGN KEY(work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  work_id INTEGER,
  chapter_id INTEGER,
  agent_name TEXT,
  model TEXT,
  prompt_name TEXT,
  input_preview TEXT,
  output TEXT,
  input_chars INTEGER DEFAULT 0,
  output_chars INTEGER DEFAULT 0,
  estimated_input_tokens INTEGER DEFAULT 0,
  estimated_output_tokens INTEGER DEFAULT 0,
  estimated_total_tokens INTEGER DEFAULT 0,
  elapsed_seconds REAL DEFAULT 0,
  status TEXT,
  error TEXT,
  created_at TEXT,
  FOREIGN KEY(work_id) REFERENCES works(id) ON DELETE CASCADE,
  FOREIGN KEY(chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);

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
