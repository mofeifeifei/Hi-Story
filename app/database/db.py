from __future__ import annotations

import sqlite3
from pathlib import Path

from app.database.migrator import apply_migrations
from app.utils.config import RESOURCE_DIR


SCHEMA_PATH = RESOURCE_DIR / "app" / "database" / "schema.sql"
MIGRATIONS_DIR = RESOURCE_DIR / "app" / "database" / "migrations"


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):  # type: ignore[no-untyped-def]
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    # WAL lets chapter reads continue while a short write transaction commits.
    # Read-only workspaces cannot change this persistent setting; keep reads
    # available there and let an actual write report the real permission error.
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(db_path: Path) -> None:
    with connect(db_path) as conn:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema)
        _ensure_column(conn, "chapters", "revision", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "chapters", "memory_revision", "INTEGER")
        # Existing projects predate title provenance. Mark them as legacy so
        # a later memory pass cannot silently replace a title the user may
        # already have edited.
        _ensure_column(conn, "chapters", "title_source", "TEXT NOT NULL DEFAULT 'legacy'")
        _ensure_column(conn, "chapters", "title_locked", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "chapters", "title_reason", "TEXT")
        _ensure_column(conn, "chapters", "title_status", "TEXT NOT NULL DEFAULT 'provisional'")
        _ensure_column(conn, "chapters", "title_quality_json", "TEXT")
        conn.execute(
            """
            UPDATE chapters
            SET title_status = CASE
                WHEN title_locked = 1 OR LOWER(COALESCE(title_source, '')) = 'manual' THEN 'manual'
                WHEN TRIM(COALESCE(final_text, '')) <> '' THEN 'pending'
                ELSE 'provisional'
            END
            WHERE title_status = 'provisional'
              AND (
                TRIM(COALESCE(final_text, '')) <> ''
                OR title_locked = 1
                OR LOWER(COALESCE(title_source, '')) = 'manual'
              )
            """
        )
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
        _ensure_column(conn, "versions", "candidate_number", "INTEGER")
        _backfill_candidate_numbers(conn)
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_versions_candidate_number
            ON versions(chapter_id, candidate_number)
            WHERE candidate_number IS NOT NULL
            """
        )
        for column, definition in [
            ("input_chars", "INTEGER DEFAULT 0"),
            ("output_chars", "INTEGER DEFAULT 0"),
            ("estimated_input_tokens", "INTEGER DEFAULT 0"),
            ("estimated_output_tokens", "INTEGER DEFAULT 0"),
            ("estimated_total_tokens", "INTEGER DEFAULT 0"),
            ("elapsed_seconds", "REAL DEFAULT 0"),
            ("finish_reason", "TEXT"),
        ]:
            _ensure_column(conn, "agent_runs", column, definition)
        for column, definition in [
            ("payoff_score", "INTEGER"),
            ("hook_score", "INTEGER"),
            ("historical_score", "INTEGER"),
            ("repeat_risk", "TEXT"),
            ("scene_coverage", "TEXT"),
            ("revision_plan", "TEXT"),
            ("revision_check", "TEXT"),
            ("reviewed_text_hash", "TEXT"),
            ("title_decision_json", "TEXT"),
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
        for column, definition in [
            ("current_ruler", "TEXT"),
            ("historical_stage", "TEXT"),
            ("central_official_system", "TEXT"),
            ("local_administration", "TEXT"),
            ("noble_titles", "TEXT"),
            ("exam_system", "TEXT"),
            ("military_ranks", "TEXT"),
            ("weapons", "TEXT"),
            ("currency", "TEXT"),
            ("measurements", "TEXT"),
            ("geo_notes", "TEXT"),
            ("travel_speed", "TEXT"),
            ("communication_speed", "TEXT"),
            ("address_terms", "TEXT"),
            ("fiction_boundary", "TEXT"),
        ]:
            _ensure_column(conn, "historical_profiles", column, definition)
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
        for column, definition in [
            ("name", "TEXT"),
            ("source_type", "TEXT"),
            ("certainty", "TEXT"),
            ("fictionalized", "INTEGER DEFAULT 0"),
            ("updated_at", "TEXT"),
        ]:
            _ensure_column(conn, "historical_facts", column, definition)
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


def _backfill_candidate_numbers(conn: sqlite3.Connection) -> None:
    """Assign permanent sequence numbers to legacy candidate versions once."""
    existing = conn.execute(
        """
        SELECT chapter_id, COALESCE(MAX(candidate_number), 0) AS maximum
        FROM versions
        WHERE candidate_number IS NOT NULL
        GROUP BY chapter_id
        """
    ).fetchall()
    counters = {int(row["chapter_id"]): int(row["maximum"] or 0) for row in existing}
    rows = conn.execute(
        """
        SELECT id, chapter_id
        FROM versions
        WHERE candidate_number IS NULL
          AND (
            version_name IN (
              'web_user_instruction_rejected_style',
              'web_user_instruction_candidate_style',
              'web_user_instruction_first_pass'
            )
            OR version_name LIKE 'reviser_rejected_style_%'
            OR version_name LIKE 'reviser_rejected_repeat_%'
          )
        ORDER BY chapter_id, created_at, id
        """
    ).fetchall()
    for row in rows:
        chapter_id = int(row["chapter_id"])
        counters[chapter_id] = counters.get(chapter_id, 0) + 1
        conn.execute(
            "UPDATE versions SET candidate_number = ? WHERE id = ?",
            (counters[chapter_id], int(row["id"])),
        )


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)
