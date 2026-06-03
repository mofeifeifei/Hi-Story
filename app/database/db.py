from __future__ import annotations

import sqlite3
from pathlib import Path

from app.database.migrator import apply_migrations
from app.utils.config import RESOURCE_DIR


SCHEMA_PATH = RESOURCE_DIR / "app" / "database" / "schema.sql"
MIGRATIONS_DIR = RESOURCE_DIR / "app" / "database" / "migrations"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema)
        apply_migrations(conn, MIGRATIONS_DIR)
        _ensure_column(conn, "works", "book_bible_json", "TEXT")
        _ensure_column(conn, "works", "settings_locked", "INTEGER DEFAULT 0")
        _ensure_column(conn, "works", "book_contract_json", "TEXT")
        for column, definition in [
            ("aliases", "TEXT"),
            ("current_goal", "TEXT"),
            ("current_fear", "TEXT"),
            ("current_state", "TEXT"),
            ("relationship_stage", "TEXT"),
            ("secret_exposure", "TEXT"),
            ("arc_stage", "TEXT"),
            ("arc_notes", "TEXT"),
            ("last_changed_chapter", "INTEGER"),
        ]:
            _ensure_column(conn, "characters", column, definition)
        _ensure_column(conn, "chapters", "outline_json", "TEXT")
        _ensure_column(conn, "chapters", "scene_cards_json", "TEXT")
        for column, definition in [
            ("payoff_score", "INTEGER"),
            ("hook_score", "INTEGER"),
            ("historical_score", "INTEGER"),
            ("repeat_risk", "TEXT"),
        ]:
            _ensure_column(conn, "reviews", column, definition)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historical_profiles (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              work_id INTEGER NOT NULL UNIQUE,
              dynasty TEXT,
              period TEXT,
              year_range TEXT,
              political_context TEXT,
              official_system TEXT,
              military_system TEXT,
              social_order TEXT,
              daily_life TEXT,
              language_style TEXT,
              taboo_words TEXT,
              allowed_fiction TEXT,
              locked_facts TEXT,
              source_notes TEXT,
              created_at TEXT,
              updated_at TEXT,
              FOREIGN KEY(work_id) REFERENCES works(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
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
            )
            """
        )
        conn.execute(
            """
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
            )
            """
        )
        conn.execute(
            """
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
            )
            """
        )
        conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)
