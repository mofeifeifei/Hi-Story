from __future__ import annotations

import re
import sqlite3
from pathlib import Path


SCHEMA_VERSION_KEY = "schema_version"


def apply_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        )
        """
    )
    current_version = _schema_version(conn)
    for version, path in _migration_files(migrations_dir):
        if version <= current_version:
            continue
        sql = path.read_text(encoding="utf-8").strip()
        if sql:
            conn.executescript(sql)
        conn.execute(
            """
            INSERT INTO schema_meta (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (SCHEMA_VERSION_KEY, str(version)),
        )
        current_version = version


def _schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT value FROM schema_meta WHERE key = ?", (SCHEMA_VERSION_KEY,)).fetchone()
    if row is None:
        return 0
    try:
        return int(row["value"] if isinstance(row, sqlite3.Row) else row[0])
    except (TypeError, ValueError):
        return 0


def _migration_files(migrations_dir: Path) -> list[tuple[int, Path]]:
    if not migrations_dir.exists():
        return []
    migrations: list[tuple[int, Path]] = []
    for path in migrations_dir.glob("*.sql"):
        match = re.match(r"^(\d+)_", path.name)
        if match:
            migrations.append((int(match.group(1)), path))
    return sorted(migrations, key=lambda item: item[0])
