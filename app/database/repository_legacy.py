from __future__ import annotations

import json
import gc
import re
import shutil
import sqlite3
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from app.database.db import connect, init_db, row_to_dict
from app.exporters.naming import safe_filename
from app.core.contracts import normalize_work_plan
from app.utils.config import INDEX_DB_PATH, LEGACY_DB_PATH, ROOT_DIR, WORKS_DIR
from app.utils.history import (
    HISTORICAL_PROFILE_FIELDS,
    compact_historical_profile,
    default_historical_profile,
    is_historical_inputs,
)
from app.utils.json_parser import as_list, json_dumps
from app.utils.name_normalizer import (
    aliases_to_official_map,
    character_identity_key,
    normalize_character_name,
    normalize_names,
)
from app.utils.outline_utils import chapter_outline_json


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _duration_seconds(start: Any, end: Any = "", *, now: datetime | None = None) -> int | None:
    start_time = _parse_time(start)
    if start_time is None:
        return None
    end_time = _parse_time(end) or now or datetime.now()
    return max(0, int((end_time - start_time).total_seconds()))


INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS work_index (
  id INTEGER PRIMARY KEY,
  title TEXT,
  folder_name TEXT NOT NULL UNIQUE,
  db_path TEXT NOT NULL UNIQUE,
  status TEXT DEFAULT 'active',
  created_at TEXT,
  updated_at TEXT
);
"""


class Repository:
    def __init__(
        self,
        db_path: Path | None = None,
        *,
        index_path: Path | None = None,
        works_dir: Path | None = None,
        legacy_db_path: Path | None = None,
    ):
        self.index_path = index_path or db_path or INDEX_DB_PATH
        self.works_dir = works_dir or self.index_path.parent / "works"
        self.legacy_db_path = legacy_db_path or LEGACY_DB_PATH
        self._initialized = False
        self.last_folder_sync_message = ""

    def init(self) -> None:
        if self._initialized:
            return
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.works_dir.mkdir(parents=True, exist_ok=True)
        self._init_index_db()
        self._migrate_legacy_db_if_needed()
        self._cleanup_pending_deleted_dirs()
        self._upgrade_existing_work_dbs()
        self._initialized = True

    def create_work(self, inputs: dict[str, Any], plan: dict[str, Any]) -> int:
        self.init()
        plan = normalize_work_plan(plan)
        created_at = now_text()
        title_candidates = as_list(plan.get("title_candidates"))
        title = inputs.get("title") or (title_candidates[0] if title_candidates else inputs.get("idea", "未命名文章"))
        work_id, db_path = self._create_index_record(title, created_at)
        init_db(db_path)

        locked_facts = self._dedupe_text_items(
            [*self._locked_facts_from_inputs(inputs), *self._collect_locked_facts(plan)]
        )
        style = self._merge_style_and_controls(inputs)
        book_bible = self._book_bible_from_plan(inputs, plan, locked_facts)

        with connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO works (
                  id, title, idea, genre, platform, target_words, style, summary,
                  reader_profile, forbidden_tropes, protagonist_preference,
                  core_selling_points, book_bible_json, locked_facts, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    work_id,
                    title,
                    inputs.get("idea", ""),
                    inputs.get("genre", ""),
                    inputs.get("platform", ""),
                    int(inputs.get("target_words") or 0),
                    style,
                    plan.get("summary", ""),
                    inputs.get("reader_profile", ""),
                    inputs.get("forbidden_tropes", ""),
                    inputs.get("protagonist_preference", ""),
                    json_dumps(plan.get("core_selling_points", [])),
                    json_dumps(book_bible),
                    json_dumps(locked_facts),
                    created_at,
                    created_at,
                ),
            )

            protagonist = plan.get("protagonist")
            if isinstance(protagonist, dict):
                self._insert_character(conn, work_id, protagonist, created_at)
            for character in as_list(plan.get("supporting_characters")):
                if isinstance(character, dict):
                    self._insert_character(conn, work_id, character, created_at)
            for villain in as_list(plan.get("villains")):
                if isinstance(villain, dict):
                    self._insert_character(conn, work_id, villain, created_at)
            for rule in as_list(plan.get("world_rules")):
                if isinstance(rule, dict):
                    self._insert_world_rule(conn, work_id, rule, created_at)
            self._upsert_historical_profile_from_plan(conn, work_id, inputs, plan, created_at)

            conn.commit()
        return work_id

    def list_works(self) -> list[dict[str, Any]]:
        self.init()
        works: list[dict[str, Any]] = []
        for record in self._index_records():
            try:
                works.append(self.get_work(int(record["id"])))
            except ValueError:
                works.append(
                    {
                        "id": int(record["id"]),
                        "title": record.get("title") or "未命名文章",
                        "genre": "",
                        "platform": "",
                        "target_words": 0,
                        "created_at": record.get("created_at") or "",
                        "_folder_name": record.get("folder_name") or "",
                        "_missing_db": True,
                    }
                )
        return works

    def get_work(self, work_id: int) -> dict[str, Any]:
        self.init()
        record = self._work_record(work_id)
        db_path = self._db_path_from_record(record)
        with connect(db_path) as conn:
            row = conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
        result = row_to_dict(row)
        if result is None:
            raise ValueError(f"作品不存在: {work_id}")
        return self._with_work_metadata(result, record)

    def get_work_bundle(self, work_id: int) -> dict[str, Any]:
        work = self.get_work(work_id)
        return {
            "work": work,
            "book_contract": self.get_book_contract(work_id),
            "workflow_state": self.workflow_state(work_id),
            "book_bible": self._book_bible_for_work(work),
            "characters": self.list_characters(work_id),
            "world_rules": self.list_world_rules(work_id),
            "historical_profile": self.get_historical_profile(work_id),
            "historical_facts": self.list_historical_facts(work_id),
            "open_plot_threads": self.list_plot_threads(work_id, status="open"),
            "latest_timeline": self.list_timeline(work_id, limit=20),
            "chapter_notes": self.list_chapter_notes(work_id),
        }

    def get_book_contract(self, work_id: int) -> dict[str, Any]:
        return self._book_contract_from_work(self.get_work(work_id))

    def save_book_contract(self, work_id: int, contract: dict[str, Any]) -> None:
        timestamp = now_text()
        with connect(self._db_path_for_work(work_id)) as conn:
            row = conn.execute("SELECT settings_locked FROM works WHERE id = ?", (work_id,)).fetchone()
            if row is not None and int(row["settings_locked"] or 0):
                raise ValueError("项目设置已锁定，请先解锁后再保存。")
            conn.execute(
                """
                UPDATE works
                SET book_contract_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (json_dumps(self._normalize_book_contract(contract)), timestamp, work_id),
            )
            conn.commit()

    def workflow_state(self, work_id: int) -> dict[str, Any]:
        work = self.get_work(work_id)
        chapters = self.list_chapters(work_id)
        contract = self._book_contract_from_work(work)
        has_contract = any(str(value or "").strip() for value in contract.values())
        has_settings = bool(
            str(work.get("idea") or "").strip()
            or str(work.get("title") or "").strip()
            or str(work.get("genre") or "").strip()
        )
        has_outline = bool(str(work.get("full_outline") or "").strip() or str(work.get("volume_outline") or "").strip())
        planned_count = len(chapters)
        draft_count = sum(1 for chapter in chapters if chapter.get("status") in {"draft", "final", "memory"})
        final_count = sum(1 for chapter in chapters if chapter.get("status") in {"final", "memory"})
        memory_count = sum(1 for chapter in chapters if chapter.get("status") == "memory")
        if not str(work.get("idea") or "").strip():
            stage = "project_setup"
            next_action = "填写并保存一句话创意。"
        elif not has_contract:
            stage = "book_contract"
            next_action = "补全整本契约，明确主角爽点、升级阶梯、关系主线和绝对红线。"
        elif not has_outline:
            stage = "outline"
            next_action = "生成或编辑全书大纲。"
        elif planned_count == 0:
            stage = "chapter_planning"
            next_action = "生成章节细纲。"
        elif draft_count < planned_count:
            stage = "chapter_execution"
            next_action = f"继续生成第 {draft_count + 1} 章正文。"
        elif final_count < planned_count:
            stage = "finalize"
            next_action = f"确认并保存第 {final_count + 1} 章最终稿。"
        elif memory_count < planned_count:
            stage = "memory"
            next_action = f"为第 {memory_count + 1} 章生成记忆并入库。"
        else:
            stage = "completed"
            next_action = "当前规划章节已完成，可以继续规划后续章节或导出。"
        return {
            "stage": stage,
            "next_action": next_action,
            "has_settings": has_settings,
            "has_contract": has_contract,
            "has_outline": has_outline,
            "planned_count": planned_count,
            "draft_count": draft_count,
            "final_count": final_count,
            "memory_count": memory_count,
        }

    def create_empty_work(self, inputs: dict[str, Any]) -> int:
        self.init()
        timestamp = now_text()
        title = inputs.get("title") or inputs.get("idea") or "未命名文章"
        work_id, db_path = self._create_index_record(title, timestamp)
        init_db(db_path)
        with connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO works (
                  id, title, idea, genre, platform, target_words, style, summary,
                  reader_profile, forbidden_tropes, protagonist_preference,
                  book_bible_json, locked_facts, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    work_id,
                    title,
                    inputs.get("idea", ""),
                    inputs.get("genre", ""),
                    inputs.get("platform", ""),
                    int(inputs.get("target_words") or 0),
                    self._merge_style_and_controls(inputs),
                    inputs.get("summary", ""),
                    inputs.get("reader_profile", ""),
                    inputs.get("forbidden_tropes", ""),
                    inputs.get("protagonist_preference", ""),
                    json_dumps(self._book_bible_from_plan(inputs, {}, [])),
                    json_dumps(self._locked_facts_from_inputs(inputs)),
                    timestamp,
                    timestamp,
                ),
            )
            if is_historical_inputs(inputs):
                self._upsert_historical_profile(conn, work_id, default_historical_profile(inputs), timestamp)
            conn.commit()
        return work_id

    def update_work_basic(self, work_id: int, inputs: dict[str, Any]) -> None:
        updated_at = now_text()
        db_path = self._db_path_for_work(work_id)
        title = inputs.get("title", "") or "未命名文章"
        conn = connect(db_path)
        try:
            row = conn.execute("SELECT settings_locked FROM works WHERE id = ?", (work_id,)).fetchone()
            if row is not None and int(row["settings_locked"] or 0):
                raise ValueError("项目设置已锁定，请先解锁后再保存。")
            conn.execute(
                """
                UPDATE works
                SET title = ?, idea = ?, genre = ?, platform = ?, target_words = ?,
                    style = ?, reader_profile = ?, forbidden_tropes = ?,
                    protagonist_preference = ?, locked_facts = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    title,
                    inputs.get("idea", ""),
                    inputs.get("genre", ""),
                    inputs.get("platform", ""),
                    int(inputs.get("target_words") or 0),
                    self._merge_style_and_controls(inputs),
                    inputs.get("reader_profile", ""),
                    inputs.get("forbidden_tropes", ""),
                    inputs.get("protagonist_preference", ""),
                    json_dumps(self._locked_facts_from_inputs(inputs)),
                    updated_at,
                    work_id,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        self._sync_index_title(work_id, title, updated_at, rename_folder=True)

    def set_work_settings_locked(self, work_id: int, locked: bool) -> None:
        updated_at = now_text()
        with connect(self._db_path_for_work(work_id)) as conn:
            conn.execute(
                "UPDATE works SET settings_locked = ?, updated_at = ? WHERE id = ?",
                (1 if locked else 0, updated_at, work_id),
            )
            conn.commit()

    def delete_work(self, work_id: int) -> dict[str, Any]:
        self.init()
        record = self._work_record(work_id)
        work_dir = self._work_dir_from_record(record)
        with self._connect_index() as conn:
            conn.execute("DELETE FROM work_index WHERE id = ?", (work_id,))
            conn.commit()
        cleanup = self._delete_or_mark_work_dir(work_dir)
        return {
            "deleted": True,
            "work_id": work_id,
            "work_dir": str(work_dir),
            **cleanup,
        }

    def apply_plan_to_work(self, work_id: int, inputs: dict[str, Any], plan: dict[str, Any]) -> None:
        self.init()
        plan = normalize_work_plan(plan)
        timestamp = now_text()
        existing = self.get_work(work_id)
        if int(existing.get("settings_locked") or 0):
            raise ValueError("项目设置已锁定，请先解锁后再采用或编辑设定。")
        title_candidates = as_list(plan.get("title_candidates"))
        current_title = existing.get("title") or ""
        title = inputs.get("title") or current_title
        if (not title or title == "未命名文章") and title_candidates:
            title = str(title_candidates[0])

        input_locked_facts = self._locked_facts_from_inputs(inputs)
        if not input_locked_facts:
            input_locked_facts = self._stored_locked_facts(existing.get("locked_facts"))
        locked_facts = self._dedupe_text_items([*input_locked_facts, *self._collect_locked_facts(plan)])
        book_bible = self._book_bible_from_plan(inputs, plan, locked_facts)

        db_path = self._db_path_for_work(work_id)
        conn = connect(db_path)
        try:
            rename_events: list[tuple[int, str, str]] = []
            for character in self._plan_characters(plan):
                row = self._find_plan_character_row(conn, work_id, character)
                new_name = str(character.get("name", "") or "").strip() if isinstance(character, dict) else ""
                old_name = str(row["name"] or "").strip() if row is not None else ""
                if row is not None and old_name and new_name and old_name != new_name:
                    rename_events.append((int(row["id"]), old_name, new_name))

            conn.execute(
                """
                UPDATE works
                SET title = ?, idea = ?, genre = ?, platform = ?, target_words = ?,
                    style = ?, summary = ?, reader_profile = ?, forbidden_tropes = ?,
                    protagonist_preference = ?, core_selling_points = ?,
                    book_bible_json = ?, locked_facts = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    title or "未命名文章",
                    inputs.get("idea", ""),
                    inputs.get("genre", ""),
                    inputs.get("platform", ""),
                    int(inputs.get("target_words") or 0),
                    self._merge_style_and_controls(inputs),
                    plan.get("summary") or existing.get("summary") or "",
                    inputs.get("reader_profile", ""),
                    inputs.get("forbidden_tropes", ""),
                    inputs.get("protagonist_preference", ""),
                    json_dumps(plan.get("core_selling_points", [])),
                    json_dumps(book_bible),
                    json_dumps(locked_facts),
                    timestamp,
                    work_id,
                ),
            )

            protagonist = plan.get("protagonist")
            if isinstance(protagonist, dict):
                self._upsert_plan_character(conn, work_id, protagonist, timestamp)
            for character in as_list(plan.get("supporting_characters")):
                if isinstance(character, dict):
                    self._upsert_plan_character(conn, work_id, character, timestamp)
            for villain in as_list(plan.get("villains")):
                if isinstance(villain, dict):
                    self._upsert_plan_character(conn, work_id, villain, timestamp)
            for rule in as_list(plan.get("world_rules")):
                if isinstance(rule, dict):
                    self._upsert_plan_world_rule(conn, work_id, rule, timestamp)
            self._upsert_historical_profile_from_plan(conn, work_id, inputs, plan, timestamp)

            for character_id, old_name, new_name in rename_events:
                self._sync_character_rename_references(
                    conn,
                    work_id=work_id,
                    character_id=character_id,
                    old_name=old_name,
                    new_name=new_name,
                    timestamp=timestamp,
                )

            conn.commit()
        finally:
            conn.close()
        self._sync_index_title(work_id, title or "未命名文章", timestamp, rename_folder=True)

    def save_outline(self, work_id: int, outline: dict[str, Any]) -> None:
        outline = self.normalize_official_names(work_id, outline)
        updated_at = now_text()
        with connect(self._db_path_for_work(work_id)) as conn:
            conn.execute(
                """
                UPDATE works
                SET full_outline = ?, volume_outline = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    outline.get("full_outline", ""),
                    json_dumps(outline.get("volume_outline", [])),
                    updated_at,
                    work_id,
                ),
            )
            conn.commit()

    def upsert_chapter_outline(
        self,
        work_id: int,
        chapter_number: int,
        title: str,
        outline: str,
        ending_hook: str = "",
        outline_json: str | dict[str, Any] | None = None,
        protect_written: bool = False,
    ) -> int:
        self.init()
        title = self.normalize_official_names(work_id, title)
        outline = self.normalize_official_names(work_id, outline)
        ending_hook = self.normalize_official_names(work_id, ending_hook)
        outline_json = self.normalize_official_names(work_id, outline_json)
        timestamp = now_text()
        if isinstance(outline_json, dict):
            outline_json_text: str | None = chapter_outline_json(outline_json)
            scene_cards_json_text = self._scene_cards_json_from_outline(outline_json)
        else:
            outline_json_text = outline_json
            scene_cards_json_text = self._scene_cards_json_from_outline(outline_json)
        with connect(self._db_path_for_work(work_id)) as conn:
            if protect_written:
                existing = conn.execute(
                    """
                    SELECT id, draft, final_text, memory_json
                    FROM chapters
                    WHERE work_id = ? AND chapter_number = ?
                    """,
                    (work_id, chapter_number),
                ).fetchone()
                if existing is not None and (
                    str(existing["draft"] or "").strip()
                    or str(existing["final_text"] or "").strip()
                    or str(existing["memory_json"] or "").strip()
                ):
                    return int(existing["id"])
            conn.execute(
                """
                INSERT INTO chapters (
                  work_id, chapter_number, title, outline, outline_json, scene_cards_json, ending_hook, status,
                  created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'outline', ?, ?)
                ON CONFLICT(work_id, chapter_number) DO UPDATE SET
                  title = excluded.title,
                  outline = excluded.outline,
                  outline_json = COALESCE(excluded.outline_json, chapters.outline_json),
                  scene_cards_json = COALESCE(excluded.scene_cards_json, chapters.scene_cards_json),
                  ending_hook = excluded.ending_hook,
                  updated_at = excluded.updated_at
                """,
                (
                    work_id,
                    chapter_number,
                    title,
                    outline,
                    outline_json_text,
                    scene_cards_json_text,
                    ending_hook,
                    timestamp,
                    timestamp,
                ),
            )
            row = conn.execute(
                "SELECT id FROM chapters WHERE work_id = ? AND chapter_number = ?",
                (work_id, chapter_number),
            ).fetchone()
            conn.commit()
        self._sync_outline_characters(work_id, outline_json if isinstance(outline_json, dict) else None)
        return int(row["id"])

    def get_chapter(self, work_id: int, chapter_number: int) -> dict[str, Any]:
        self.init()
        with connect(self._db_path_for_work(work_id)) as conn:
            row = conn.execute(
                "SELECT * FROM chapters WHERE work_id = ? AND chapter_number = ?",
                (work_id, chapter_number),
            ).fetchone()
        result = row_to_dict(row)
        if result is None:
            raise ValueError(f"章节不存在: work_id={work_id}, chapter={chapter_number}")
        if str(result.get("memory_json") or "").strip():
            result["status"] = "memory"
        return result

    def list_chapters(self, work_id: int) -> list[dict[str, Any]]:
        self.init()
        with connect(self._db_path_for_work(work_id)) as conn:
            rows = conn.execute(
                """
                SELECT id, chapter_number, title,
                       CASE
                         WHEN memory_json IS NOT NULL AND TRIM(memory_json) != '' THEN 'memory'
                         WHEN final_text IS NOT NULL AND TRIM(final_text) != '' THEN 'final'
                         WHEN draft IS NOT NULL AND TRIM(draft) != '' THEN 'draft'
                         ELSE status
                       END AS status,
                       summary, ending_hook, updated_at
                FROM chapters
                WHERE work_id = ?
                ORDER BY chapter_number
                """,
                (work_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_chapter_outlines(self, work_id: int) -> list[dict[str, Any]]:
        self.init()
        with connect(self._db_path_for_work(work_id)) as conn:
            rows = conn.execute(
                """
                SELECT chapter_number, title, outline, outline_json, scene_cards_json, ending_hook,
                       CASE
                         WHEN memory_json IS NOT NULL AND TRIM(memory_json) != '' THEN 'memory'
                         WHEN final_text IS NOT NULL AND TRIM(final_text) != '' THEN 'final'
                         WHEN draft IS NOT NULL AND TRIM(draft) != '' THEN 'draft'
                         ELSE status
                       END AS status
                FROM chapters
                WHERE work_id = ?
                ORDER BY chapter_number
                """,
                (work_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_recent_chapter_outlines(self, work_id: int, before_chapter: int, limit: int = 5) -> list[dict[str, Any]]:
        with connect(self._db_path_for_work(work_id)) as conn:
            rows = conn.execute(
                """
                SELECT chapter_number, title, outline, outline_json, scene_cards_json, ending_hook,
                       CASE
                         WHEN memory_json IS NOT NULL AND TRIM(memory_json) != '' THEN 'memory'
                         WHEN final_text IS NOT NULL AND TRIM(final_text) != '' THEN 'final'
                         WHEN draft IS NOT NULL AND TRIM(draft) != '' THEN 'draft'
                         ELSE status
                       END AS status
                FROM chapters
                WHERE work_id = ? AND chapter_number < ?
                ORDER BY chapter_number DESC
                LIMIT ?
                """,
                (work_id, before_chapter, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def delete_chapter(self, work_id: int, chapter_number: int, *, delete_related: bool = True) -> bool:
        self.init()
        with connect(self._db_path_for_work(work_id)) as conn:
            row = conn.execute(
                "SELECT id FROM chapters WHERE work_id = ? AND chapter_number = ?",
                (work_id, chapter_number),
            ).fetchone()
            if row is None:
                return False
            chapter_id = int(row["id"])
            if delete_related:
                self._clear_chapter_memory_side_effects(conn, work_id, chapter_number, now_text())
                conn.execute(
                    "DELETE FROM chapter_notes WHERE work_id = ? AND chapter_number = ?",
                    (work_id, chapter_number),
                )
            conn.execute("DELETE FROM reviews WHERE chapter_id = ?", (chapter_id,))
            conn.execute("DELETE FROM versions WHERE chapter_id = ?", (chapter_id,))
            conn.execute("DELETE FROM agent_runs WHERE chapter_id = ?", (chapter_id,))
            conn.execute("DELETE FROM chapters WHERE id = ?", (chapter_id,))
            conn.commit()
        return True

    def list_characters(self, work_id: int) -> list[dict[str, Any]]:
        with connect(self._db_path_for_work(work_id)) as conn:
            rows = conn.execute(
                "SELECT * FROM characters WHERE work_id = ? ORDER BY id",
                (work_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_character(self, work_id: int, data: dict[str, Any]) -> int:
        timestamp = now_text()
        data = self._normalize_character_data(data)
        character_id = int(data.get("id") or 0)
        with connect(self._db_path_for_work(work_id)) as conn:
            if character_id:
                row = conn.execute(
                    "SELECT * FROM characters WHERE id = ? AND work_id = ?",
                    (character_id, work_id),
                ).fetchone()
                if row is not None:
                    duplicate = self._find_character_row_by_identity(conn, work_id, data, exclude_id=character_id)
                    if duplicate is not None:
                        target = self._merge_character_rows(dict(duplicate), dict(row), timestamp)
                        target = self._merge_character_rows(target, data, timestamp)
                        self._save_character_update(conn, work_id, int(duplicate["id"]), target, timestamp)
                        old_name = str(row["name"] or "").strip()
                        new_name = str(target.get("name") or duplicate["name"] or "").strip()
                        self._sync_character_rename_references(
                            conn,
                            work_id=work_id,
                            character_id=int(duplicate["id"]),
                            old_name=old_name,
                            new_name=new_name,
                            timestamp=timestamp,
                        )
                        conn.execute("DELETE FROM characters WHERE id = ? AND work_id = ?", (character_id, work_id))
                        conn.commit()
                        return int(duplicate["id"])
                    old_name = str(row["name"] or "").strip()
                    new_name = str(data.get("name", "") or "").strip()
                    aliases = self._aliases_with_old_name(data.get("aliases"), old_name, new_name)
                    data["aliases"] = aliases
                    self._save_character_update(conn, work_id, character_id, data, timestamp)
                    if old_name and new_name and old_name != new_name:
                        self._sync_character_rename_references(
                            conn,
                            work_id=work_id,
                            character_id=character_id,
                            old_name=old_name,
                            new_name=new_name,
                            timestamp=timestamp,
                        )
                    conn.commit()
                    return character_id

            existing = self._find_character_row_by_identity(conn, work_id, data)
            if existing is not None:
                merged = self._merge_character_rows(dict(existing), data, timestamp)
                self._save_character_update(conn, work_id, int(existing["id"]), merged, timestamp)
                conn.commit()
                return int(existing["id"])
            cur = self._insert_character(conn, work_id, data, timestamp)
            conn.commit()
            return int(cur.lastrowid)

    def delete_character(self, work_id: int, character_id: int) -> None:
        with connect(self._db_path_for_work(work_id)) as conn:
            conn.execute("DELETE FROM characters WHERE id = ? AND work_id = ?", (character_id, work_id))
            conn.commit()

    def list_chapter_notes(self, work_id: int, chapter_number: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM chapter_notes WHERE work_id = ?"
        params: list[Any] = [work_id]
        if chapter_number is not None:
            query += " AND (chapter_number = ? OR chapter_number IS NULL OR chapter_number = 0)"
            params.append(chapter_number)
        query += " ORDER BY COALESCE(chapter_number, 0), id"
        with connect(self._db_path_for_work(work_id)) as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def upsert_chapter_note(self, work_id: int, data: dict[str, Any]) -> int:
        timestamp = now_text()
        note_id = int(data.get("id") or 0)
        chapter_number = self._optional_int(data.get("chapter_number"))
        with connect(self._db_path_for_work(work_id)) as conn:
            if note_id:
                conn.execute(
                    """
                    UPDATE chapter_notes
                    SET chapter_number = ?, note_type = ?, content = ?, updated_at = ?
                    WHERE id = ? AND work_id = ?
                    """,
                    (
                        chapter_number,
                        data.get("note_type", ""),
                        data.get("content", ""),
                        timestamp,
                        note_id,
                        work_id,
                    ),
                )
                conn.commit()
                return note_id

            cur = conn.execute(
                """
                INSERT INTO chapter_notes (
                  work_id, chapter_number, note_type, content, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    work_id,
                    chapter_number,
                    data.get("note_type", ""),
                    data.get("content", ""),
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def delete_chapter_note(self, work_id: int, note_id: int) -> None:
        with connect(self._db_path_for_work(work_id)) as conn:
            conn.execute("DELETE FROM chapter_notes WHERE id = ? AND work_id = ?", (note_id, work_id))
            conn.commit()

    def list_world_rules(self, work_id: int) -> list[dict[str, Any]]:
        with connect(self._db_path_for_work(work_id)) as conn:
            rows = conn.execute(
                "SELECT * FROM world_rules WHERE work_id = ? ORDER BY id",
                (work_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_world_rule(self, work_id: int, data: dict[str, Any]) -> int:
        timestamp = now_text()
        rule_id = int(data.get("id") or 0)
        with connect(self._db_path_for_work(work_id)) as conn:
            if rule_id:
                conn.execute(
                    """
                    UPDATE world_rules
                    SET rule_name = ?, rule_content = ?, limitations = ?,
                        forbidden_changes = ?, updated_at = ?
                    WHERE id = ? AND work_id = ?
                    """,
                    (
                        data.get("rule_name", ""),
                        data.get("rule_content", ""),
                        data.get("limitations", ""),
                        data.get("forbidden_changes", ""),
                        timestamp,
                        rule_id,
                        work_id,
                    ),
                )
                conn.commit()
                return rule_id

            cur = conn.execute(
                """
                INSERT INTO world_rules (
                  work_id, rule_name, rule_content, limitations,
                  forbidden_changes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    work_id,
                    data.get("rule_name", ""),
                    data.get("rule_content", ""),
                    data.get("limitations", ""),
                    data.get("forbidden_changes", ""),
                    timestamp,
                    timestamp,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get_historical_profile(self, work_id: int) -> dict[str, Any]:
        with connect(self._db_path_for_work(work_id)) as conn:
            row = conn.execute(
                "SELECT * FROM historical_profiles WHERE work_id = ?",
                (work_id,),
            ).fetchone()
        result = row_to_dict(row)
        return result or {}

    def upsert_historical_profile(self, work_id: int, profile: dict[str, Any]) -> None:
        timestamp = now_text()
        profile = compact_historical_profile(profile)
        with connect(self._db_path_for_work(work_id)) as conn:
            self._upsert_historical_profile(conn, work_id, profile, timestamp)
            conn.commit()

    def list_historical_facts(self, work_id: int, limit: int = 80) -> list[dict[str, Any]]:
        with connect(self._db_path_for_work(work_id)) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM historical_facts
                WHERE work_id = ?
                ORDER BY chapter_number DESC, id DESC
                LIMIT ?
                """,
                (work_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def delete_world_rule(self, work_id: int, rule_id: int) -> None:
        with connect(self._db_path_for_work(work_id)) as conn:
            conn.execute("DELETE FROM world_rules WHERE id = ? AND work_id = ?", (rule_id, work_id))
            conn.commit()

    def delete_chapter_if_unwritten(self, work_id: int, chapter_number: int) -> bool:
        with connect(self._db_path_for_work(work_id)) as conn:
            row = conn.execute(
                """
                SELECT id, draft, final_text, memory_json
                FROM chapters
                WHERE work_id = ? AND chapter_number = ?
                """,
                (work_id, chapter_number),
            ).fetchone()
            if row is None:
                return True
            if (row["draft"] or "").strip() or (row["final_text"] or "").strip() or (row["memory_json"] or "").strip():
                return False
            chapter_id = int(row["id"])
            conn.execute("DELETE FROM reviews WHERE chapter_id = ?", (chapter_id,))
            conn.execute("DELETE FROM versions WHERE chapter_id = ?", (chapter_id,))
            conn.execute("DELETE FROM chapter_notes WHERE work_id = ? AND chapter_number = ?", (work_id, chapter_number))
            conn.execute("DELETE FROM chapters WHERE id = ? AND work_id = ?", (chapter_id, work_id))
            conn.commit()
            return True

    def list_plot_threads(self, work_id: int, status: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM plot_threads WHERE work_id = ?"
        params: list[Any] = [work_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY COALESCE(planned_resolve_chapter, 999999), id"
        with connect(self._db_path_for_work(work_id)) as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def upsert_plot_thread(self, work_id: int, data: dict[str, Any]) -> int:
        timestamp = now_text()
        thread_id = int(data.get("id") or 0)
        values = (
            self._optional_int(data.get("first_chapter")),
            data.get("content", ""),
            data.get("status", "open") or "open",
            self._optional_int(data.get("planned_resolve_chapter")),
            self._optional_int(data.get("actual_resolve_chapter")),
            timestamp,
        )
        with connect(self._db_path_for_work(work_id)) as conn:
            if thread_id:
                conn.execute(
                    """
                    UPDATE plot_threads
                    SET first_chapter = ?, content = ?, status = ?,
                        planned_resolve_chapter = ?, actual_resolve_chapter = ?,
                        updated_at = ?
                    WHERE id = ? AND work_id = ?
                    """,
                    (*values, thread_id, work_id),
                )
                conn.commit()
                return thread_id

            cur = conn.execute(
                """
                INSERT INTO plot_threads (
                  work_id, first_chapter, content, status,
                  planned_resolve_chapter, actual_resolve_chapter,
                  created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (work_id, *values[:5], timestamp, timestamp),
            )
            conn.commit()
            return int(cur.lastrowid)

    def delete_plot_thread(self, work_id: int, thread_id: int) -> None:
        with connect(self._db_path_for_work(work_id)) as conn:
            conn.execute("DELETE FROM plot_threads WHERE id = ? AND work_id = ?", (thread_id, work_id))
            conn.commit()

    def list_timeline(self, work_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM timeline WHERE work_id = ? ORDER BY id DESC"
        params: list[Any] = [work_id]
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        with connect(self._db_path_for_work(work_id)) as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def upsert_timeline_event(self, work_id: int, data: dict[str, Any]) -> int:
        event_id = int(data.get("id") or 0)
        with connect(self._db_path_for_work(work_id)) as conn:
            if event_id:
                conn.execute(
                    """
                    UPDATE timeline
                    SET chapter_number = ?, story_time = ?, event = ?, characters_involved = ?
                    WHERE id = ? AND work_id = ?
                    """,
                    (
                        self._optional_int(data.get("chapter_number")),
                        data.get("story_time", ""),
                        data.get("event", ""),
                        data.get("characters_involved", ""),
                        event_id,
                        work_id,
                    ),
                )
                conn.commit()
                return event_id

            cur = conn.execute(
                """
                INSERT INTO timeline (
                  work_id, chapter_number, story_time, event,
                  characters_involved, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    work_id,
                    self._optional_int(data.get("chapter_number")),
                    data.get("story_time", ""),
                    data.get("event", ""),
                    data.get("characters_involved", ""),
                    now_text(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def delete_timeline_event(self, work_id: int, event_id: int) -> None:
        with connect(self._db_path_for_work(work_id)) as conn:
            conn.execute("DELETE FROM timeline WHERE id = ? AND work_id = ?", (event_id, work_id))
            conn.commit()

    def list_sync_events(self, work_id: int, limit: int = 50) -> list[dict[str, Any]]:
        with connect(self._db_path_for_work(work_id)) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM sync_events
                WHERE work_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (work_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_recent_summaries(self, work_id: int, before_chapter: int, limit: int = 3) -> list[dict[str, Any]]:
        with connect(self._db_path_for_work(work_id)) as conn:
            rows = conn.execute(
                """
                SELECT chapter_number, title, summary, ending_hook, handoff
                FROM chapters
                WHERE work_id = ? AND chapter_number < ? AND summary IS NOT NULL AND summary != ''
                ORDER BY chapter_number DESC
                LIMIT ?
                """,
                (work_id, before_chapter, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def get_previous_chapter_context(self, work_id: int, chapter_number: int, tail_chars: int = 900) -> dict[str, Any] | None:
        with connect(self._db_path_for_work(work_id)) as conn:
            row = conn.execute(
                """
                SELECT chapter_number, title, final_text, draft, ending_hook, handoff
                FROM chapters
                WHERE work_id = ? AND chapter_number < ?
                ORDER BY chapter_number DESC
                LIMIT 1
                """,
                (work_id, chapter_number),
            ).fetchone()
        if row is None:
            return None
        data = dict(row)
        text = data.get("final_text") or data.get("draft") or ""
        data["tail"] = text[-tail_chars:]
        data.pop("final_text", None)
        data.pop("draft", None)
        return data

    def get_recent_chapter_texts(self, work_id: int, before_chapter: int, limit: int = 5) -> list[dict[str, Any]]:
        with connect(self._db_path_for_work(work_id)) as conn:
            rows = conn.execute(
                """
                SELECT chapter_number, title, final_text, draft
                FROM chapters
                WHERE work_id = ?
                  AND chapter_number < ?
                  AND ((final_text IS NOT NULL AND final_text != '') OR (draft IS NOT NULL AND draft != ''))
                ORDER BY chapter_number DESC
                LIMIT ?
                """,
                (work_id, before_chapter, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_draft(self, work_id: int, chapter_id: int, draft: str) -> None:
        draft = self.normalize_official_names(work_id, draft)
        self._update_chapter_text(work_id, chapter_id, draft=draft, status="draft")
        self.add_version(work_id, chapter_id, f"draft_ai_{now_text()}", draft)

    def save_final(
        self,
        work_id: int,
        chapter_id: int,
        final_text: str,
        *,
        title: str | None = None,
        ending_hook: str | None = None,
        handoff: str | None = None,
        memory_json: str | None = None,
    ) -> None:
        final_text = self.normalize_official_names(work_id, final_text)
        title = self.normalize_official_names(work_id, title)
        ending_hook = self.normalize_official_names(work_id, ending_hook)
        handoff = self.normalize_official_names(work_id, handoff)
        memory_json = self.normalize_official_names(work_id, memory_json)
        fields: dict[str, Any] = {
            "final_text": final_text,
            "ending_hook": ending_hook,
            "handoff": handoff,
            "memory_json": memory_json,
            "status": "final",
        }
        if title is not None:
            fields["title"] = title
        self._update_chapter_text(work_id, chapter_id, **fields)
        self.add_version(work_id, chapter_id, f"final_{now_text()}", final_text)

    def save_final_after_manual_edit(
        self,
        work_id: int,
        chapter_id: int,
        final_text: str,
        *,
        title: str | None = None,
        ending_hook: str | None = None,
        handoff: str | None = None,
        memory_json: str | None = None,
        invalidate_memory: bool = False,
    ) -> None:
        if invalidate_memory:
            self.clear_chapter_memory(work_id, chapter_id)
            handoff = ""
            memory_json = ""
        self.save_final(
            work_id,
            chapter_id,
            final_text,
            title=title,
            ending_hook=ending_hook,
            handoff=handoff,
            memory_json=memory_json,
        )

    def clear_chapter_memory(self, work_id: int, chapter_id: int) -> None:
        with connect(self._db_path_for_work(work_id)) as conn:
            row = conn.execute(
                "SELECT chapter_number FROM chapters WHERE id = ? AND work_id = ?",
                (chapter_id, work_id),
            ).fetchone()
            if row is None:
                return
            chapter_number = int(row["chapter_number"])
            self._clear_chapter_memory_side_effects(conn, work_id, chapter_number, now_text())
            conn.execute(
                """
                UPDATE chapters
                SET summary = '', handoff = '', memory_json = '', status = 'final', updated_at = ?
                WHERE id = ? AND work_id = ?
                """,
                (now_text(), chapter_id, work_id),
            )
            conn.commit()

    def save_review(self, work_id: int, chapter_id: int, review: dict[str, Any]) -> int:
        review = self.normalize_official_names(work_id, review)
        timestamp = now_text()
        with connect(self._db_path_for_work(work_id)) as conn:
            cur = conn.execute(
                """
                INSERT INTO reviews (
                  chapter_id, continuity_score, character_score, emotion_score,
                  rhythm_score, foreshadow_score, payoff_score, hook_score,
                  historical_score, repeat_risk, problems, suggestions, template_hits,
                  risk_flags, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chapter_id,
                    int(review.get("continuity_score") or 0),
                    int(review.get("character_score") or 0),
                    int(review.get("emotion_score") or 0),
                    int(review.get("rhythm_score") or 0),
                    int(review.get("foreshadow_score") or 0),
                    int(review.get("payoff_score") or 0),
                    int(review.get("hook_score") or 0),
                    int(review.get("historical_score") or 0),
                    json_dumps(review.get("repeat_risk", [])),
                    json_dumps(review.get("problems", [])),
                    json_dumps(review.get("suggestions", [])),
                    json_dumps(review.get("template_hits", [])),
                    json_dumps(review.get("risk_flags", [])),
                    timestamp,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def add_version(self, work_id: int, chapter_id: int, version_name: str, content: str) -> int:
        with connect(self._db_path_for_work(work_id)) as conn:
            cur = conn.execute(
                """
                INSERT INTO versions (chapter_id, version_name, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (chapter_id, version_name, content, now_text()),
            )
            conn.commit()
            return int(cur.lastrowid)

    def apply_memory_card(
        self,
        *,
        work_id: int,
        chapter_id: int,
        chapter_number: int,
        memory: dict[str, Any],
    ) -> None:
        memory = self.normalize_official_names(work_id, memory)
        timestamp = now_text()
        handoff = memory.get("handoff", {})
        handoff_text = json_dumps(handoff)
        with connect(self._db_path_for_work(work_id)) as conn:
            self._clear_chapter_memory_side_effects(conn, work_id, chapter_number, timestamp)
            conn.execute(
                """
                UPDATE chapters
                SET summary = ?, ending_hook = ?, handoff = ?, memory_json = ?, status = 'memory', updated_at = ?
                WHERE id = ?
                """,
                (
                    memory.get("summary", ""),
                    memory.get("ending_hook", ""),
                    handoff_text,
                    json_dumps(memory),
                    timestamp,
                    chapter_id,
                ),
            )

            for item in as_list(memory.get("character_state_updates")):
                if not isinstance(item, dict):
                    continue
                name = normalize_character_name(item.get("name"))
                if not name:
                    continue
                row = self._find_character_row_by_identity(conn, work_id, {"name": name})
                if row is None:
                    continue
                current = dict(row)
                old_values = {
                    key: current.get(key, "")
                    for key in [
                        "current_goal",
                        "current_fear",
                        "current_state",
                        "relationship_stage",
                        "secret_exposure",
                        "arc_stage",
                        "arc_notes",
                        "last_changed_chapter",
                    ]
                }
                new_values = {
                    "current_goal": item.get("current_goal") or current.get("current_goal", ""),
                    "current_fear": item.get("current_fear") or current.get("current_fear", ""),
                    "current_state": item.get("current_state") or current.get("current_state", ""),
                    "relationship_stage": item.get("relationship_stage") or current.get("relationship_stage", ""),
                    "secret_exposure": item.get("secret_exposure") or current.get("secret_exposure", ""),
                    "arc_stage": item.get("arc_stage") or current.get("arc_stage", ""),
                    "arc_notes": item.get("arc_notes") or current.get("arc_notes", ""),
                    "last_changed_chapter": chapter_number,
                }
                conn.execute(
                    """
                    UPDATE characters
                    SET current_goal = ?, current_fear = ?, current_state = ?,
                        relationship_stage = ?, secret_exposure = ?, arc_stage = ?,
                        arc_notes = ?, last_changed_chapter = ?, updated_at = ?
                    WHERE id = ? AND work_id = ?
                    """,
                    (
                        new_values["current_goal"],
                        new_values["current_fear"],
                        new_values["current_state"],
                        new_values["relationship_stage"],
                        new_values["secret_exposure"],
                        new_values["arc_stage"],
                        new_values["arc_notes"],
                        new_values["last_changed_chapter"],
                        timestamp,
                        current["id"],
                        work_id,
                    ),
                )
                self._insert_sync_event(
                    conn,
                    work_id=work_id,
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    source="memory_card",
                    target_type="character",
                    target_id=int(current["id"]),
                    target_name=str(current.get("name") or item.get("name") or "")[:80],
                    action="update_character_state",
                    details={"old_values": old_values, "new_values": new_values},
                    timestamp=timestamp,
                )

            for item in as_list(memory.get("new_foreshadows")):
                if not isinstance(item, dict) or not item.get("content"):
                    continue
                cur = conn.execute(
                    """
                    INSERT INTO plot_threads (
                      work_id, first_chapter, content, status,
                      planned_resolve_chapter, created_at, updated_at
                    ) VALUES (?, ?, ?, 'open', ?, ?, ?)
                    """,
                    (
                        work_id,
                        chapter_number,
                        item.get("content", ""),
                        item.get("planned_resolve_chapter"),
                        timestamp,
                        timestamp,
                    ),
                )
                self._insert_sync_event(
                    conn,
                    work_id=work_id,
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    source="memory_card",
                    target_type="plot_thread",
                    target_id=int(cur.lastrowid),
                    target_name=str(item.get("content", ""))[:80],
                    action="create_foreshadow",
                    details=item,
                    timestamp=timestamp,
                )

            for item in as_list(memory.get("resolved_foreshadows")):
                if not isinstance(item, dict) or not item.get("content"):
                    continue
                self._resolve_plot_thread(
                    conn,
                    work_id=work_id,
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    content=str(item.get("content", "")),
                    actual_chapter=item.get("actual_resolve_chapter") or chapter_number,
                    timestamp=timestamp,
                )

            for event in as_list(memory.get("timeline_events")):
                if not isinstance(event, dict) or not event.get("event"):
                    continue
                cur = conn.execute(
                    """
                    INSERT INTO timeline (
                      work_id, chapter_number, story_time, event,
                      characters_involved, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        work_id,
                        chapter_number,
                        event.get("story_time", ""),
                        event.get("event", ""),
                        event.get("characters_involved", ""),
                        timestamp,
                    ),
                )
                self._insert_sync_event(
                    conn,
                    work_id=work_id,
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    source="memory_card",
                    target_type="timeline",
                    target_id=int(cur.lastrowid),
                    target_name=str(event.get("event", ""))[:80],
                    action="create_timeline_event",
                    details=event,
                    timestamp=timestamp,
                )

            for item in as_list(memory.get("historical_updates")):
                if not isinstance(item, dict):
                    continue
                content = str(item.get("content", "") or "").strip()
                if not content:
                    continue
                cur = conn.execute(
                    """
                    INSERT INTO historical_facts (
                      work_id, chapter_number, category, content,
                      chapter_impact, future_constraint, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        work_id,
                        chapter_number,
                        item.get("category", ""),
                        content,
                        item.get("chapter_impact", ""),
                        item.get("future_constraint", ""),
                        timestamp,
                    ),
                )
                self._insert_sync_event(
                    conn,
                    work_id=work_id,
                    chapter_id=chapter_id,
                    chapter_number=chapter_number,
                    source="memory_card",
                    target_type="historical_fact",
                    target_id=int(cur.lastrowid),
                    target_name=content[:80],
                    action="create_historical_fact",
                    details=item,
                    timestamp=timestamp,
                )

            conn.commit()

    def official_name_map(self, work_id: int) -> dict[str, str]:
        return aliases_to_official_map(self.list_characters(work_id))

    def normalize_official_names(self, work_id: int, value: Any) -> Any:
        return normalize_names(value, self.official_name_map(work_id), strip_aliases=False)

    def chapters_for_export(self, work_id: int) -> list[dict[str, Any]]:
        with connect(self._db_path_for_work(work_id)) as conn:
            rows = conn.execute(
                """
                SELECT chapter_number, title, final_text, draft
                FROM chapters
                WHERE work_id = ?
                ORDER BY chapter_number
                """,
                (work_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def log_agent_run(
        self,
        *,
        work_id: int | None,
        chapter_id: int | None,
        agent_name: str,
        model: str,
        prompt_name: str,
        input_preview: str,
        output: str,
        status: str = "ok",
        error: str = "",
    ) -> int:
        if work_id is None:
            return 0
        with connect(self._db_path_for_work(work_id)) as conn:
            cur = conn.execute(
                """
                INSERT INTO agent_runs (
                  work_id, chapter_id, agent_name, model, prompt_name,
                  input_preview, output, status, error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    work_id,
                    chapter_id,
                    agent_name,
                    model,
                    prompt_name,
                    input_preview[:2000],
                    output,
                    status,
                    error,
                    now_text(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_agent_runs(self, work_id: int, limit: int = 100) -> list[dict[str, Any]]:
        self.init()
        with connect(self._db_path_for_work(work_id)) as conn:
            rows = conn.execute(
                """
                SELECT
                  agent_runs.*,
                  chapters.chapter_number AS chapter_number
                FROM agent_runs
                LEFT JOIN chapters ON chapters.id = agent_runs.chapter_id
                WHERE agent_runs.work_id = ?
                ORDER BY agent_runs.id DESC
                LIMIT ?
                """,
                (work_id, max(1, int(limit))),
            ).fetchall()
        return [dict(row) for row in rows]

    def log_task_run(
        self,
        *,
        task_id: str,
        work_id: int | None,
        chapter_id: int | None = None,
        kind: str = "",
        title: str = "",
        status: str = "running",
        stage: str = "",
        input_json: str = "",
        output_preview: str = "",
        error: str = "",
        finished_at: str = "",
    ) -> None:
        if not task_id or work_id is None:
            return
        timestamp = now_text()
        with connect(self._db_path_for_work(work_id)) as conn:
            conn.execute(
                """
                INSERT INTO task_runs (
                  id, work_id, chapter_id, kind, title, status, stage,
                  input_json, output_preview, error, created_at, updated_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  chapter_id = COALESCE(excluded.chapter_id, task_runs.chapter_id),
                  kind = COALESCE(NULLIF(excluded.kind, ''), task_runs.kind),
                  title = COALESCE(NULLIF(excluded.title, ''), task_runs.title),
                  status = excluded.status,
                  stage = COALESCE(NULLIF(excluded.stage, ''), task_runs.stage),
                  input_json = COALESCE(NULLIF(excluded.input_json, ''), task_runs.input_json),
                  output_preview = COALESCE(NULLIF(excluded.output_preview, ''), task_runs.output_preview),
                  error = excluded.error,
                  updated_at = excluded.updated_at,
                  finished_at = COALESCE(NULLIF(excluded.finished_at, ''), task_runs.finished_at)
                """,
                (
                    task_id,
                    work_id,
                    chapter_id,
                    kind,
                    title,
                    status,
                    stage,
                    input_json[:4000],
                    output_preview[:2000],
                    error[:1000],
                    timestamp,
                    timestamp,
                    finished_at,
                ),
            )
            conn.commit()

    def list_task_runs(self, work_id: int, *, limit: int = 120) -> list[dict[str, Any]]:
        with connect(self._db_path_for_work(work_id)) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM task_runs
                WHERE work_id = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (work_id, max(1, int(limit))),
            ).fetchall()
        now = datetime.now()
        result = []
        for row in rows:
            item = dict(row)
            if item.get("status") in {"running", "cancelling"}:
                end_time = ""
            else:
                end_time = item.get("finished_at") or item.get("updated_at") or ""
            item["duration_seconds"] = _duration_seconds(item.get("created_at"), end_time, now=now)
            result.append(item)
        return result

    def work_dir(self, work_id: int) -> Path:
        return self._work_dir_from_record(self._work_record(work_id))

    def export_dir(self, work_id: int) -> Path:
        return self.work_dir(work_id) / "exports"

    def _init_index_db(self) -> None:
        with self._connect_index() as conn:
            conn.executescript(INDEX_SCHEMA)
            conn.commit()

    def _connect_index(self) -> sqlite3.Connection:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.index_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _migrate_legacy_db_if_needed(self) -> None:
        if not self.legacy_db_path.exists():
            return
        with self._connect_index() as conn:
            count = conn.execute("SELECT COUNT(*) FROM work_index").fetchone()[0]
        if count:
            return

        try:
            with connect(self.legacy_db_path) as old_conn:
                old_works = old_conn.execute("SELECT * FROM works ORDER BY id").fetchall()
                if not old_works:
                    return
                for old_work in old_works:
                    self._migrate_one_legacy_work(old_conn, dict(old_work))
        except sqlite3.DatabaseError:
            return

    def _migrate_one_legacy_work(self, old_conn: sqlite3.Connection, old_work: dict[str, Any]) -> None:
        work_id = int(old_work["id"])
        title = old_work.get("title") or "未命名文章"
        folder_name = self._unique_folder_name(work_id, title)
        work_dir = self.works_dir / folder_name
        db_path = work_dir / "work.db"
        work_dir.mkdir(parents=True, exist_ok=True)
        init_db(db_path)

        chapter_rows = old_conn.execute("SELECT id FROM chapters WHERE work_id = ?", (work_id,)).fetchall()
        chapter_ids = [int(row["id"]) for row in chapter_rows]

        with connect(db_path) as new_conn:
            self._copy_rows(old_conn, new_conn, "works", "SELECT * FROM works WHERE id = ?", (work_id,))
            for table in [
                "characters",
                "world_rules",
                "historical_profiles",
                "historical_facts",
                "chapters",
                "plot_threads",
                "timeline",
                "chapter_notes",
                "agent_runs",
            ]:
                self._copy_rows(old_conn, new_conn, table, f"SELECT * FROM {table} WHERE work_id = ?", (work_id,))
            if chapter_ids:
                placeholders = ",".join("?" for _ in chapter_ids)
                self._copy_rows(
                    old_conn,
                    new_conn,
                    "reviews",
                    f"SELECT * FROM reviews WHERE chapter_id IN ({placeholders})",
                    tuple(chapter_ids),
                )
                self._copy_rows(
                    old_conn,
                    new_conn,
                    "versions",
                    f"SELECT * FROM versions WHERE chapter_id IN ({placeholders})",
                    tuple(chapter_ids),
                )
            new_conn.commit()

        created_at = old_work.get("created_at") or now_text()
        updated_at = old_work.get("updated_at") or created_at
        with self._connect_index() as conn:
            conn.execute(
                """
                INSERT INTO work_index (id, title, folder_name, db_path, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?)
                """,
                (work_id, title, folder_name, self._relative_path(db_path), created_at, updated_at),
            )
            conn.commit()

    @staticmethod
    def _copy_rows(
        old_conn: sqlite3.Connection,
        new_conn: sqlite3.Connection,
        table: str,
        query: str,
        params: tuple[Any, ...],
    ) -> None:
        try:
            rows = old_conn.execute(query, params).fetchall()
        except sqlite3.OperationalError:
            return
        if not rows:
            return
        columns = [row["name"] for row in old_conn.execute(f"PRAGMA table_info({table})").fetchall()]
        placeholders = ", ".join("?" for _ in columns)
        column_list = ", ".join(columns)
        new_conn.executemany(
            f"INSERT OR REPLACE INTO {table} ({column_list}) VALUES ({placeholders})",
            [[row[column] for column in columns] for row in rows],
        )

    def _create_index_record(self, title: str, timestamp: str) -> tuple[int, Path]:
        with self._connect_index() as conn:
            row = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM work_index").fetchone()
            work_id = int(row[0])
            folder_name = self._unique_folder_name(work_id, title)
            db_path = self.works_dir / folder_name / "work.db"
            conn.execute(
                """
                INSERT INTO work_index (id, title, folder_name, db_path, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'active', ?, ?)
                """,
                (work_id, title, folder_name, self._relative_path(db_path), timestamp, timestamp),
            )
            conn.commit()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return work_id, db_path

    def _index_records(self) -> list[dict[str, Any]]:
        with self._connect_index() as conn:
            rows = conn.execute(
                "SELECT * FROM work_index WHERE status = 'active' ORDER BY id ASC"
            ).fetchall()
        return [dict(row) for row in rows]

    def _cleanup_pending_deleted_dirs(self) -> None:
        if not self.works_dir.exists():
            return
        for path in self.works_dir.iterdir():
            if not path.is_dir():
                continue
            if ".deleted-" not in path.name and not (path / ".pending-delete").exists():
                continue
            try:
                self._assert_inside_works_dir(path)
                self._rmtree_with_retry(path)
            except OSError:
                continue

    def _upgrade_existing_work_dbs(self) -> None:
        for record in self._index_records():
            db_path = self._db_path_from_record(record)
            if db_path.exists():
                init_db(db_path)
                try:
                    self._repair_chapter_memory_statuses(db_path)
                    self._repair_work_style_controls(db_path)
                    self._repair_duplicate_characters(db_path, int(record["id"]))
                    self._repair_official_names(db_path, int(record["id"]))
                except (OSError, sqlite3.Error):
                    pass
                self._repair_folder_name_if_needed(record)

    @staticmethod
    def _repair_chapter_memory_statuses(db_path: Path) -> None:
        with connect(db_path) as conn:
            conn.execute(
                """
                UPDATE chapters
                SET status = 'memory'
                WHERE memory_json IS NOT NULL
                  AND TRIM(memory_json) != ''
                  AND COALESCE(status, '') != 'memory'
                """
            )
            conn.commit()

    @staticmethod
    def _repair_work_style_controls(db_path: Path) -> None:
        with connect(db_path) as conn:
            rows = conn.execute("SELECT id, style, locked_facts FROM works").fetchall()
            for row in rows:
                style = str(row["style"] or "")
                normalized = Repository._normalize_style_controls_text(style)
                normalized, extracted_locked = Repository._extract_locked_facts_from_style(normalized)
                stored_locked = Repository._stored_locked_facts(row["locked_facts"])
                locked_facts = Repository._dedupe_text_items([*stored_locked, *extracted_locked])
                if normalized != style or locked_facts != stored_locked:
                    conn.execute(
                        "UPDATE works SET style = ?, locked_facts = ?, updated_at = ? WHERE id = ?",
                        (normalized, json_dumps(locked_facts), now_text(), int(row["id"])),
                    )
            conn.commit()

    @staticmethod
    def _repair_duplicate_characters(db_path: Path, work_id: int) -> None:
        with connect(db_path) as conn:
            rows = [dict(row) for row in conn.execute("SELECT * FROM characters WHERE work_id = ? ORDER BY id", (work_id,)).fetchall()]
            if not rows:
                return
            timestamp = now_text()
            groups: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                key = character_identity_key(row.get("name"))
                if key:
                    groups.setdefault(key, []).append(row)

            for group in groups.values():
                keep = group[0]
                keep_id = int(keep["id"])
                keep_name = normalize_character_name(keep.get("name")) or str(keep.get("name") or "").strip()
                merged = Repository._normalize_character_data({**keep, "name": keep_name})
                old_keep_name = str(keep.get("name") or "").strip()
                if old_keep_name and old_keep_name != keep_name:
                    Repository._sync_character_rename_references(
                        conn,
                        work_id=work_id,
                        character_id=keep_id,
                        old_name=old_keep_name,
                        new_name=keep_name,
                        timestamp=timestamp,
                    )
                for duplicate in group[1:]:
                    duplicate_id = int(duplicate["id"])
                    duplicate_name = str(duplicate.get("name") or "").strip()
                    merged = Repository._merge_character_rows(merged, duplicate, timestamp)
                    if duplicate_name and duplicate_name != keep_name:
                        Repository._sync_character_rename_references(
                            conn,
                            work_id=work_id,
                            character_id=keep_id,
                            old_name=duplicate_name,
                            new_name=keep_name,
                            timestamp=timestamp,
                        )
                    conn.execute(
                        """
                        UPDATE sync_events
                        SET target_id = ?, target_name = ?
                        WHERE work_id = ? AND target_type = 'character' AND target_id = ?
                        """,
                        (keep_id, keep_name, work_id, duplicate_id),
                    )
                    conn.execute("DELETE FROM characters WHERE id = ? AND work_id = ?", (duplicate_id, work_id))
                merged["name"] = keep_name
                Repository._save_character_update(conn, work_id, keep_id, merged, timestamp)
            conn.commit()

    @staticmethod
    def _repair_official_names(db_path: Path, work_id: int) -> None:
        with connect(db_path) as conn:
            characters = [dict(row) for row in conn.execute("SELECT * FROM characters WHERE work_id = ?", (work_id,)).fetchall()]
            mapping = aliases_to_official_map(characters)
            if not mapping:
                return
            timestamp = now_text()

            def update_table(table: str, columns: list[str], where: str, params: list[Any]) -> None:
                rows = conn.execute(f"SELECT * FROM {table} WHERE {where}", params).fetchall()
                for row in rows:
                    updates: dict[str, Any] = {}
                    for column in columns:
                        replaced = normalize_names(row[column] or "", mapping)
                        if replaced != (row[column] or ""):
                            updates[column] = replaced
                    if updates and "updated_at" in row.keys():
                        updates["updated_at"] = timestamp
                    if updates:
                        Repository._update_row(conn, table, updates, "id = ?", [int(row["id"])])

            update_table(
                "works",
                [
                    "summary",
                    "reader_profile",
                    "protagonist_preference",
                    "core_selling_points",
                    "book_bible_json",
                    "full_outline",
                    "volume_outline",
                    "locked_facts",
                ],
                "id = ?",
                [work_id],
            )
            update_table(
                "characters",
                [
                    "personality",
                    "goal",
                    "secret",
                    "speaking_style",
                    "relationship",
                    "locked_rules",
                    "current_goal",
                    "current_fear",
                    "current_state",
                    "relationship_stage",
                    "secret_exposure",
                    "arc_stage",
                    "arc_notes",
                ],
                "work_id = ?",
                [work_id],
            )
            update_table(
                "world_rules",
                ["rule_name", "rule_content", "limitations", "forbidden_changes"],
                "work_id = ?",
                [work_id],
            )
            update_table(
                "historical_profiles",
                [
                    "dynasty",
                    "period",
                    "year_range",
                    "political_context",
                    "official_system",
                    "military_system",
                    "social_order",
                    "daily_life",
                    "language_style",
                    "taboo_words",
                    "allowed_fiction",
                    "locked_facts",
                    "source_notes",
                ],
                "work_id = ?",
                [work_id],
            )
            update_table(
                "historical_facts",
                [
                    "category",
                    "content",
                    "chapter_impact",
                    "future_constraint",
                ],
                "work_id = ?",
                [work_id],
            )
            update_table(
                "chapters",
                [
                    "title",
                    "outline",
                    "outline_json",
                    "scene_cards_json",
                    "draft",
                    "final_text",
                    "summary",
                    "ending_hook",
                    "handoff",
                    "memory_json",
                ],
                "work_id = ?",
                [work_id],
            )
            update_table(
                "plot_threads",
                ["content"],
                "work_id = ?",
                [work_id],
            )
            update_table(
                "timeline",
                ["story_time", "event", "characters_involved"],
                "work_id = ?",
                [work_id],
            )
            update_table(
                "chapter_notes",
                ["content"],
                "work_id = ?",
                [work_id],
            )
            conn.commit()

    def _work_record(self, work_id: int) -> dict[str, Any]:
        self.init()
        with self._connect_index() as conn:
            row = conn.execute(
                "SELECT * FROM work_index WHERE id = ? AND status = 'active'",
                (work_id,),
            ).fetchone()
        result = row_to_dict(row)
        if result is None:
            raise ValueError(f"作品不存在: {work_id}")
        return result

    def _db_path_for_work(self, work_id: int) -> Path:
        return self._db_path_from_record(self._work_record(work_id))

    def _db_path_from_record(self, record: dict[str, Any]) -> Path:
        db_path = Path(record["db_path"])
        if db_path.is_absolute():
            return db_path
        return ROOT_DIR / db_path

    def _work_dir_from_record(self, record: dict[str, Any]) -> Path:
        return self._db_path_from_record(record).parent

    def _with_work_metadata(self, work: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        work_dir = self._work_dir_from_record(record)
        work.update(
            {
                "_folder_name": record.get("folder_name") or "",
                "_db_path": str(self._db_path_from_record(record)),
                "_work_dir": str(work_dir),
                "_export_dir": str(work_dir / "exports"),
            }
        )
        return work

    def _sync_index_title(self, work_id: int, title: str, updated_at: str, *, rename_folder: bool) -> None:
        record = self._work_record(work_id)
        folder_name = record["folder_name"]
        db_path = self._db_path_from_record(record)
        self.last_folder_sync_message = ""
        if rename_folder:
            desired_folder = self._folder_name(work_id, title)
            if desired_folder != folder_name:
                old_dir = db_path.parent
                if not old_dir.exists():
                    found_dir = self._find_work_dir_by_id(work_id)
                    if found_dir is not None:
                        folder_name = found_dir.name
                        db_path = found_dir / "work.db"
                        self.last_folder_sync_message = f"作品名称已保存，并重新关联作品文件夹：{folder_name}"
                    else:
                        self.last_folder_sync_message = f"作品名称已保存，但原作品文件夹不存在：{old_dir}"
                else:
                    target_folder, new_dir = self._unique_folder_name_for_rename(work_id, title, current_dir=old_dir)
                    ok, error = self._rename_work_dir_with_retry(old_dir, new_dir)
                    if not ok:
                        self.last_folder_sync_message = (
                            "作品名称已保存，但文件夹暂时被占用，重命名失败。"
                            f"程序会在下次启动或刷新时自动重试。\n原始错误：{error}"
                        )
                    else:
                        folder_name = target_folder
                        db_path = new_dir / "work.db"
                        if target_folder == desired_folder:
                            self.last_folder_sync_message = f"作品文件夹已重命名为：{folder_name}"
                        else:
                            self.last_folder_sync_message = f"目标文件夹已存在，作品文件夹已重命名为：{folder_name}"

        with self._connect_index() as conn:
            conn.execute(
                """
                UPDATE work_index
                SET title = ?, folder_name = ?, db_path = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, folder_name, self._relative_path(db_path), updated_at, work_id),
            )
            conn.commit()

    def _repair_folder_name_if_needed(self, record: dict[str, Any]) -> None:
        db_path = self._db_path_from_record(record)
        title = self._work_title_from_db(db_path, int(record["id"])) or str(record.get("title") or "未命名文章")
        folder_name = str(record.get("folder_name") or "")
        desired_folder = self._folder_name(int(record["id"]), title)
        if not folder_name:
            return
        if folder_name == desired_folder and str(record.get("title") or "") == title:
            return
        old_dir = db_path.parent
        if folder_name != desired_folder:
            if not old_dir.exists():
                return
            self._assert_inside_works_dir(old_dir)
            desired_folder, new_dir = self._unique_folder_name_for_rename(int(record["id"]), title, current_dir=old_dir)
            ok, _ = self._rename_work_dir_with_retry(old_dir, new_dir)
            if not ok:
                return
            db_path = new_dir / "work.db"
        with self._connect_index() as conn:
            conn.execute(
                """
                UPDATE work_index
                SET title = ?, folder_name = ?, db_path = ?
                WHERE id = ?
                """,
                (title, desired_folder, self._relative_path(db_path), record["id"]),
            )
            conn.commit()

    def _unique_folder_name_for_rename(self, work_id: int, title: str, *, current_dir: Path) -> tuple[str, Path]:
        base = self._folder_name(work_id, title)
        current_resolved = current_dir.resolve()
        candidate = base
        counter = 2
        while True:
            path = (self.works_dir / candidate).resolve()
            if path == current_resolved or not path.exists():
                return candidate, path
            counter += 1
            candidate = f"{base}-{counter}"

    def _rename_work_dir_with_retry(self, old_dir: Path, new_dir: Path) -> tuple[bool, str]:
        self._assert_inside_works_dir(old_dir)
        self._assert_inside_works_dir(new_dir)
        last_error: OSError | None = None
        for attempt in range(10):
            try:
                gc.collect()
                old_dir.rename(new_dir)
                return True, ""
            except OSError as exc:
                last_error = exc
                time.sleep(min(0.2 + attempt * 0.15, 1.0))
        return False, str(last_error or "未知错误")

    def _find_work_dir_by_id(self, work_id: int) -> Path | None:
        prefix = f"{work_id:06d}-"
        if not self.works_dir.exists():
            return None
        for path in self.works_dir.iterdir():
            if not path.is_dir() or not path.name.startswith(prefix):
                continue
            db_path = path / "work.db"
            if self._work_db_has_id(db_path, work_id):
                return path.resolve()
        return None

    @staticmethod
    def _work_db_has_id(db_path: Path, work_id: int) -> bool:
        if not db_path.exists():
            return False
        try:
            with connect(db_path) as conn:
                row = conn.execute("SELECT 1 FROM works WHERE id = ? LIMIT 1", (work_id,)).fetchone()
        except sqlite3.Error:
            return False
        return row is not None

    @staticmethod
    def _work_title_from_db(db_path: Path, work_id: int) -> str:
        if not db_path.exists():
            return ""
        try:
            with connect(db_path) as conn:
                row = conn.execute("SELECT title FROM works WHERE id = ?", (work_id,)).fetchone()
        except sqlite3.Error:
            return ""
        return str(row["title"] or "").strip() if row is not None else ""

    def _unique_folder_name(self, work_id: int, title: str) -> str:
        base = self._folder_name(work_id, title)
        candidate = base
        counter = 2
        while (self.works_dir / candidate).exists():
            candidate = f"{base}-{counter}"
            counter += 1
        return candidate

    @staticmethod
    def _folder_name(work_id: int, title: str) -> str:
        return f"{work_id:06d}-{safe_filename(title, '未命名文章')}"

    def _delete_or_mark_work_dir(self, work_dir: Path) -> dict[str, Any]:
        if not work_dir.exists():
            return {"directory_deleted": True}
        self._assert_inside_works_dir(work_dir)
        try:
            self._rmtree_with_retry(work_dir)
            return {"directory_deleted": True}
        except OSError as exc:
            pending_dir = self._pending_deleted_dir(work_dir)
            try:
                work_dir.rename(pending_dir)
                try:
                    self._rmtree_with_retry(pending_dir)
                    return {"directory_deleted": True}
                except OSError as cleanup_exc:
                    return {
                        "directory_deleted": False,
                        "pending_delete_dir": str(pending_dir),
                        "cleanup_warning": f"作品已从列表移除，但目录暂时被占用，稍后会自动清理：{pending_dir}。原因：{cleanup_exc}",
                    }
            except OSError as rename_exc:
                self._mark_pending_delete(work_dir, rename_exc)
                return {
                    "directory_deleted": False,
                    "pending_delete_dir": str(work_dir),
                    "cleanup_warning": f"作品已从列表移除，但目录仍被占用，请关闭相关程序后手动删除：{work_dir}。原因：{rename_exc}",
                    "cleanup_error": str(exc),
                }

    @staticmethod
    def _mark_pending_delete(work_dir: Path, error: OSError) -> None:
        try:
            (work_dir / ".pending-delete").write_text(
                f"pending delete since {now_text()}\n{error}\n",
                encoding="utf-8",
            )
        except OSError:
            return

    def _pending_deleted_dir(self, work_dir: Path) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        base = work_dir.with_name(f"{work_dir.name}.deleted-{timestamp}")
        candidate = base
        counter = 2
        while candidate.exists():
            candidate = work_dir.with_name(f"{base.name}-{counter}")
            counter += 1
        self._assert_inside_works_dir(candidate)
        return candidate

    @staticmethod
    def _relative_path(path: Path) -> str:
        try:
            return str(path.resolve().relative_to(ROOT_DIR.resolve()))
        except ValueError:
            return str(path)

    def _assert_inside_works_dir(self, path: Path) -> None:
        works_root = self.works_dir.resolve()
        target = path.resolve()
        if target == works_root or works_root not in target.parents:
            raise ValueError(f"拒绝删除非文章目录: {target}")

    @staticmethod
    def _rmtree_with_retry(path: Path) -> None:
        last_error: OSError | None = None
        for _ in range(5):
            try:
                gc.collect()
                shutil.rmtree(path)
                return
            except OSError as exc:
                last_error = exc
                time.sleep(0.15)
        if last_error is not None:
            raise last_error

    @staticmethod
    def _load_json_list(value: Any) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        try:
            parsed = json.loads(str(value))
        except (TypeError, json.JSONDecodeError):
            return [str(value)]
        return [str(item) for item in as_list(parsed) if str(item).strip()]

    @staticmethod
    def _normalize_book_contract(contract: dict[str, Any]) -> dict[str, str]:
        fields = [
            "protagonist_fantasy",
            "escalation_ladder",
            "relationship_mainline",
            "absolute_red_lines",
        ]
        return {field: str(contract.get(field) or "").strip() for field in fields}

    def _book_contract_from_work(self, work: dict[str, Any]) -> dict[str, str]:
        raw = work.get("book_contract_json")
        data: dict[str, Any] = {}
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    data = parsed
            except json.JSONDecodeError:
                data = {}
        return self._normalize_book_contract(data)

    @staticmethod
    def _locked_facts_from_inputs(inputs: dict[str, Any]) -> list[str]:
        value = inputs.get("locked_facts")
        if isinstance(value, list):
            return Repository._dedupe_text_items(value)
        return Repository._dedupe_text_items(str(value or "").splitlines())

    @staticmethod
    def _stored_locked_facts(value: Any) -> list[str]:
        lines: list[str] = []
        for item in Repository._load_json_list(value):
            lines.extend(str(item or "").splitlines())
        return Repository._dedupe_text_items(lines)

    @staticmethod
    def _dedupe_text_items(values: Any) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in as_list(values):
            text = str(value or "").strip()
            if not text:
                continue
            key = re.sub(r"\s+", "", text)
            if key in seen:
                continue
            seen.add(key)
            result.append(text)
        return result

    @staticmethod
    def _aliases_with_old_name(value: Any, old_name: str, new_name: str) -> list[str]:
        aliases = Repository._load_json_list(value)
        for alias in [old_name]:
            alias = str(alias or "").strip()
            if alias and alias != new_name and alias not in aliases:
                aliases.append(alias)
        return aliases

    @staticmethod
    def _replace_name_refs(value: Any, old_name: str, new_name: str) -> Any:
        if isinstance(value, str):
            return value.replace(old_name, new_name)
        if isinstance(value, list):
            return [Repository._replace_name_refs(item, old_name, new_name) for item in value]
        if isinstance(value, dict):
            return {key: Repository._replace_name_refs(item, old_name, new_name) for key, item in value.items()}
        return value

    @staticmethod
    def _sync_character_rename_references(
        conn: sqlite3.Connection,
        *,
        work_id: int,
        character_id: int,
        old_name: str,
        new_name: str,
        timestamp: str,
    ) -> int:
        if not old_name or not new_name or old_name == new_name:
            return 0
        changed = 0

        work = conn.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
        if work is not None:
            work_updates: dict[str, Any] = {}
            for column in ["summary", "reader_profile", "protagonist_preference", "locked_facts", "full_outline", "volume_outline"]:
                replaced = Repository._replace_name_refs(work[column] or "", old_name, new_name)
                if replaced != (work[column] or ""):
                    work_updates[column] = replaced
            bible = Repository._replace_json_text(work["book_bible_json"], old_name, new_name)
            if bible is not None and bible != (work["book_bible_json"] or ""):
                work_updates["book_bible_json"] = bible
            points = Repository._replace_json_text(work["core_selling_points"], old_name, new_name)
            if points is not None and points != (work["core_selling_points"] or ""):
                work_updates["core_selling_points"] = points
            if work_updates:
                work_updates["updated_at"] = timestamp
                Repository._update_row(conn, "works", work_updates, "id = ?", [work_id])
                changed += 1

        for row in conn.execute("SELECT * FROM characters WHERE work_id = ?", (work_id,)).fetchall():
            row_id = int(row["id"])
            updates: dict[str, Any] = {}
            for column in [
                "personality",
                "goal",
                "secret",
                "speaking_style",
                "relationship",
                "locked_rules",
                "current_goal",
                "current_fear",
                "current_state",
                "relationship_stage",
                "secret_exposure",
                "arc_stage",
                "arc_notes",
            ]:
                replaced = Repository._replace_name_refs(row[column] or "", old_name, new_name)
                if replaced != (row[column] or ""):
                    updates[column] = replaced
            aliases = Repository._aliases_with_old_name(row["aliases"] if "aliases" in row.keys() else "", old_name, new_name)
            if row_id == character_id:
                updates["aliases"] = json_dumps(aliases)
            if updates:
                updates["updated_at"] = timestamp
                Repository._update_row(conn, "characters", updates, "id = ? AND work_id = ?", [row_id, work_id])
                changed += 1

        for row in conn.execute("SELECT * FROM world_rules WHERE work_id = ?", (work_id,)).fetchall():
            updates = {}
            for column in ["rule_name", "rule_content", "limitations", "forbidden_changes"]:
                replaced = Repository._replace_name_refs(row[column] or "", old_name, new_name)
                if replaced != (row[column] or ""):
                    updates[column] = replaced
            if updates:
                updates["updated_at"] = timestamp
                Repository._update_row(conn, "world_rules", updates, "id = ? AND work_id = ?", [int(row["id"]), work_id])
                changed += 1

        for row in conn.execute("SELECT * FROM plot_threads WHERE work_id = ?", (work_id,)).fetchall():
            replaced = Repository._replace_name_refs(row["content"] or "", old_name, new_name)
            if replaced != (row["content"] or ""):
                Repository._update_row(
                    conn,
                    "plot_threads",
                    {"content": replaced, "updated_at": timestamp},
                    "id = ? AND work_id = ?",
                    [int(row["id"]), work_id],
                )
                changed += 1

        for row in conn.execute("SELECT * FROM timeline WHERE work_id = ?", (work_id,)).fetchall():
            updates = {}
            for column in ["story_time", "event", "characters_involved"]:
                replaced = Repository._replace_name_refs(row[column] or "", old_name, new_name)
                if replaced != (row[column] or ""):
                    updates[column] = replaced
            if updates:
                Repository._update_row(conn, "timeline", updates, "id = ? AND work_id = ?", [int(row["id"]), work_id])
                changed += 1

        for row in conn.execute("SELECT * FROM chapter_notes WHERE work_id = ?", (work_id,)).fetchall():
            replaced = Repository._replace_name_refs(row["content"] or "", old_name, new_name)
            if replaced != (row["content"] or ""):
                Repository._update_row(
                    conn,
                    "chapter_notes",
                    {"content": replaced, "updated_at": timestamp},
                    "id = ? AND work_id = ?",
                    [int(row["id"]), work_id],
                )
                changed += 1

        for row in conn.execute("SELECT * FROM chapters WHERE work_id = ?", (work_id,)).fetchall():
            has_written_text = bool(
                str(row["draft"] or "").strip()
                or str(row["final_text"] or "").strip()
                or str(row["memory_json"] or "").strip()
            )
            updates = {}
            for column in ["title", "outline", "ending_hook"]:
                replaced = Repository._replace_name_refs(row[column] or "", old_name, new_name)
                if replaced != (row[column] or ""):
                    updates[column] = replaced
            for column in ["outline_json", "scene_cards_json"]:
                replaced = Repository._replace_json_text(row[column], old_name, new_name)
                if replaced is not None and replaced != (row[column] or ""):
                    updates[column] = replaced
            if not has_written_text:
                handoff = Repository._replace_name_refs(row["handoff"] or "", old_name, new_name)
                if handoff != (row["handoff"] or ""):
                    updates["handoff"] = handoff
            if updates:
                updates["updated_at"] = timestamp
                Repository._update_row(conn, "chapters", updates, "id = ? AND work_id = ?", [int(row["id"]), work_id])
                changed += 1

        Repository._insert_sync_event(
            conn,
            work_id=work_id,
            chapter_id=None,
            chapter_number=None,
            source="character_rename",
            target_type="character",
            target_id=character_id,
            target_name=new_name,
            action="rename_character",
            details={"old_name": old_name, "new_name": new_name, "changed_rows": changed},
            timestamp=timestamp,
        )
        return changed

    @staticmethod
    def _replace_json_text(value: Any, old_name: str, new_name: str) -> str | None:
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            replaced = Repository._replace_name_refs(value, old_name, new_name)
            return json_dumps(replaced)
        stripped = value.strip()
        if not stripped:
            return None
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            replaced = Repository._replace_name_refs(value, old_name, new_name)
            return replaced if replaced != value else None
        replaced = Repository._replace_name_refs(parsed, old_name, new_name)
        return json_dumps(replaced)

    @staticmethod
    def _update_row(
        conn: sqlite3.Connection,
        table: str,
        updates: dict[str, Any],
        where_clause: str,
        where_params: list[Any],
    ) -> None:
        if not updates:
            return
        assignments = ", ".join(f"{column} = ?" for column in updates)
        conn.execute(
            f"UPDATE {table} SET {assignments} WHERE {where_clause}",
            [*updates.values(), *where_params],
        )

    @staticmethod
    def _collect_locked_facts(plan: dict[str, Any]) -> list[str]:
        facts: list[str] = []
        protagonist = plan.get("protagonist")
        if isinstance(protagonist, dict) and protagonist.get("locked_rules"):
            facts.append(str(protagonist["locked_rules"]))
        for rule in as_list(plan.get("world_rules")):
            if isinstance(rule, dict) and rule.get("forbidden_changes"):
                facts.append(str(rule["forbidden_changes"]))
        return facts

    @staticmethod
    def _book_bible_from_plan(inputs: dict[str, Any], plan: dict[str, Any], locked_facts: list[str]) -> dict[str, Any]:
        bible = plan.get("book_bible")
        if isinstance(bible, dict) and bible:
            return bible
        return {
            "core_reading_promise": str(plan.get("summary") or inputs.get("idea") or ""),
            "primary_genre": str(inputs.get("genre", "") or ""),
            "secondary_genres": [],
            "emotional_tone": str(inputs.get("style") or inputs.get("reader_profile") or ""),
            "narrative_driver": str(plan.get("main_goal") or inputs.get("idea") or ""),
            "protagonist_end_goal": str(plan.get("main_goal") or ""),
            "long_form_engine": "人物目标、阻力、伏笔、关系变化和章末钩子共同驱动长篇。",
            "must_keep_rules": locked_facts,
            "forbidden_drift": [],
            "ending_direction": str(plan.get("first_volume_direction") or ""),
        }

    @staticmethod
    def _book_bible_for_work(work: dict[str, Any]) -> dict[str, Any]:
        value = work.get("book_bible_json")
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _scene_cards_json_from_outline(value: Any) -> str | None:
        source: Any = None
        if isinstance(value, dict):
            source = value.get("scene_cards")
        elif isinstance(value, str) and value.strip():
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None
            if isinstance(parsed, dict):
                source = parsed.get("scene_cards")
        if not source:
            return None
        return json_dumps(source)

    @staticmethod
    def _merge_style_and_controls(inputs: dict[str, Any]) -> str:
        style = Repository._dedupe_text_lines(
            str(inputs.get("style", "") or "").split("\n\n写作控制：", 1)[0]
        )
        controls = Repository._dedupe_text_lines(inputs.get("writing_controls", ""))
        style = Repository._remove_overlapping_lines(style, controls)
        if style and controls and Repository._compact_text(style) == Repository._compact_text(controls):
            return f"\n\n写作控制：\n{controls}"
        if style and controls:
            return f"{style}\n\n写作控制：\n{controls}"
        if controls:
            return f"\n\n写作控制：\n{controls}"
        return style

    @staticmethod
    def _normalize_style_controls_text(value: Any) -> str:
        text = str(value or "")
        if "\n\n写作控制：" not in text:
            return Repository._dedupe_text_lines(text)
        style, controls = text.split("\n\n写作控制：", 1)
        style = Repository._dedupe_text_lines(style)
        controls = Repository._dedupe_text_lines(controls)
        style = Repository._remove_overlapping_lines(style, controls)
        if style and controls and Repository._compact_text(style) == Repository._compact_text(controls):
            style = ""
        if style and controls:
            return f"{style}\n\n写作控制：\n{controls}"
        if controls:
            return f"\n\n写作控制：\n{controls}"
        return style

    @staticmethod
    def _extract_locked_facts_from_style(value: str) -> tuple[str, list[str]]:
        lines = str(value or "").splitlines()
        kept: list[str] = []
        locked: list[str] = []
        capturing_locked = False
        control_prefixes = ("单章字数：", "叙事视角：", "节奏控制：", "悬疑强度：", "情绪强度：")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("锁定设定："):
                text = stripped.split("：", 1)[1].strip()
                if text:
                    locked.append(text)
                capturing_locked = True
                continue
            if capturing_locked:
                if stripped.startswith(control_prefixes) or stripped == "写作控制：":
                    capturing_locked = False
                    kept.append(line)
                elif stripped:
                    locked.append(stripped)
                continue
            kept.append(line)
        return Repository._normalize_style_controls_text("\n".join(kept)), Repository._dedupe_text_items(locked)

    @staticmethod
    def _compact_text(value: Any) -> str:
        return re.sub(r"\s+", "", str(value or ""))

    @staticmethod
    def _remove_overlapping_lines(style: str, controls: str) -> str:
        control_keys = {
            Repository._compact_text(line)
            for line in str(controls or "").splitlines()
            if str(line).strip()
        }
        kept = [
            line
            for line in str(style or "").splitlines()
            if not str(line).strip() or Repository._compact_text(line) not in control_keys
        ]
        return Repository._dedupe_text_lines("\n".join(kept))

    @staticmethod
    def _dedupe_text_lines(value: Any) -> str:
        seen: set[str] = set()
        lines: list[str] = []
        for raw_line in str(value or "").splitlines():
            line = raw_line.strip()
            if not line:
                if lines and lines[-1]:
                    lines.append("")
                continue
            key = re.sub(r"\s+", "", line)
            if key in seen:
                continue
            seen.add(key)
            lines.append(line)
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)

    @staticmethod
    def _normalize_character_data(data: dict[str, Any]) -> dict[str, Any]:
        result = dict(data)
        raw_name = str(result.get("name", "") or "").strip()
        normalized_name = normalize_character_name(raw_name)
        result["name"] = normalized_name
        aliases = Repository._aliases_with_old_name(result.get("aliases"), raw_name, normalized_name)
        normalized_aliases: list[str] = []
        for alias in aliases:
            alias = str(alias or "").strip()
            if alias and alias != normalized_name and alias not in normalized_aliases:
                normalized_aliases.append(alias)
            cleaned = normalize_character_name(alias)
            if cleaned and cleaned != normalized_name and cleaned not in normalized_aliases:
                normalized_aliases.append(cleaned)
        result["aliases"] = normalized_aliases
        return result

    @staticmethod
    def _character_identity_values(data: dict[str, Any]) -> set[str]:
        values = {character_identity_key(data.get("name"))}
        for alias in Repository._load_json_list(data.get("aliases")):
            values.add(character_identity_key(alias))
        return {value for value in values if value}

    @staticmethod
    def _find_character_row_by_identity(
        conn: sqlite3.Connection,
        work_id: int,
        data: dict[str, Any],
        *,
        exclude_id: int = 0,
    ) -> sqlite3.Row | None:
        target_keys = Repository._character_identity_values(data)
        if not target_keys:
            return None
        rows = conn.execute(
            "SELECT * FROM characters WHERE work_id = ? ORDER BY id",
            (work_id,),
        ).fetchall()
        for row in rows:
            if exclude_id and int(row["id"]) == int(exclude_id):
                continue
            row_data = dict(row)
            if target_keys.intersection(Repository._character_identity_values(row_data)):
                return row
        return None

    @staticmethod
    def _merge_character_rows(base: dict[str, Any], incoming: dict[str, Any], timestamp: str) -> dict[str, Any]:
        result = Repository._normalize_character_data(base)
        incoming = Repository._normalize_character_data(incoming)
        for key in [
            "role",
            "personality",
            "goal",
            "secret",
            "speaking_style",
            "relationship",
            "locked_rules",
            "current_goal",
            "current_fear",
            "current_state",
            "relationship_stage",
            "secret_exposure",
            "arc_stage",
            "arc_notes",
        ]:
            current = str(result.get(key) or "").strip()
            new_value = str(incoming.get(key) or "").strip()
            if (not current or current == "待补充") and new_value:
                result[key] = new_value
        current_chapter = Repository._optional_int(result.get("last_changed_chapter"))
        incoming_chapter = Repository._optional_int(incoming.get("last_changed_chapter"))
        result["last_changed_chapter"] = max(current_chapter or 0, incoming_chapter or 0) or ""
        aliases: list[str] = []
        for value in [
            base.get("name"),
            incoming.get("name"),
            *Repository._load_json_list(base.get("aliases")),
            *Repository._load_json_list(incoming.get("aliases")),
        ]:
            value = str(value or "").strip()
            if value and value != result.get("name") and value not in aliases:
                aliases.append(value)
        result["aliases"] = aliases
        result["updated_at"] = timestamp
        return result

    @staticmethod
    def _save_character_update(
        conn: sqlite3.Connection,
        work_id: int,
        character_id: int,
        data: dict[str, Any],
        timestamp: str,
    ) -> None:
        data = Repository._normalize_character_data(data)
        conn.execute(
            """
            UPDATE characters
            SET name = ?, role = ?, aliases = ?, personality = ?, goal = ?, secret = ?,
                speaking_style = ?, relationship = ?, locked_rules = ?,
                current_goal = ?, current_fear = ?, current_state = ?,
                relationship_stage = ?, secret_exposure = ?, arc_stage = ?,
                arc_notes = ?, last_changed_chapter = ?, updated_at = ?
            WHERE id = ? AND work_id = ?
            """,
            (
                data.get("name", ""),
                data.get("role", ""),
                json_dumps(data.get("aliases", [])),
                data.get("personality", ""),
                data.get("goal", ""),
                data.get("secret", ""),
                data.get("speaking_style", ""),
                data.get("relationship", ""),
                data.get("locked_rules", ""),
                data.get("current_goal", ""),
                data.get("current_fear", ""),
                data.get("current_state", ""),
                data.get("relationship_stage", ""),
                data.get("secret_exposure", ""),
                data.get("arc_stage", ""),
                data.get("arc_notes", ""),
                Repository._optional_int(data.get("last_changed_chapter")),
                timestamp,
                character_id,
                work_id,
            ),
        )

    @staticmethod
    def _insert_character(conn: sqlite3.Connection, work_id: int, data: dict[str, Any], timestamp: str) -> sqlite3.Cursor:
        data = Repository._normalize_character_data(data)
        aliases = Repository._aliases_with_old_name(
            data.get("aliases"),
            "",
            str(data.get("name", "") or "").strip(),
        )
        return conn.execute(
            """
            INSERT INTO characters (
              work_id, name, role, aliases, personality, goal, secret,
              speaking_style, relationship, locked_rules,
              current_goal, current_fear, current_state,
              relationship_stage, secret_exposure, arc_stage,
              arc_notes, last_changed_chapter, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                work_id,
                data.get("name", ""),
                data.get("role", ""),
                json_dumps(aliases),
                data.get("personality", ""),
                data.get("goal", ""),
                data.get("secret", ""),
                data.get("speaking_style", ""),
                data.get("relationship", ""),
                data.get("locked_rules", ""),
                data.get("current_goal", ""),
                data.get("current_fear", ""),
                data.get("current_state", ""),
                data.get("relationship_stage", ""),
                data.get("secret_exposure", ""),
                data.get("arc_stage", ""),
                data.get("arc_notes", ""),
                Repository._optional_int(data.get("last_changed_chapter")),
                timestamp,
                timestamp,
            ),
        )

    @staticmethod
    def _upsert_plan_character(conn: sqlite3.Connection, work_id: int, data: dict[str, Any], timestamp: str) -> None:
        data = Repository._normalize_character_data(data)
        name = str(data.get("name", "") or "").strip()
        if not name:
            return
        row = Repository._find_plan_character_row(conn, work_id, data)
        if row is None:
            Repository._insert_character(conn, work_id, data, timestamp)
            return
        old_row = conn.execute(
            "SELECT * FROM characters WHERE id = ? AND work_id = ?",
            (row["id"], work_id),
        ).fetchone()
        old_name = str(old_row["name"] or "").strip() if old_row is not None else ""
        aliases = Repository._aliases_with_old_name(data.get("aliases"), old_name, name)
        data["aliases"] = aliases
        merged = Repository._merge_character_rows(dict(old_row), data, timestamp) if old_row is not None else data
        Repository._save_character_update(conn, work_id, int(row["id"]), merged, timestamp)
        if old_name and old_name != name:
            Repository._sync_character_rename_references(
                conn,
                work_id=work_id,
                character_id=int(row["id"]),
                old_name=old_name,
                new_name=name,
                timestamp=timestamp,
            )

    @staticmethod
    def _plan_characters(plan: dict[str, Any]) -> list[dict[str, Any]]:
        characters: list[dict[str, Any]] = []
        protagonist = plan.get("protagonist")
        if isinstance(protagonist, dict):
            characters.append(protagonist)
        for key in ["supporting_characters", "villains"]:
            for character in as_list(plan.get(key)):
                if isinstance(character, dict):
                    characters.append(character)
        return characters

    @staticmethod
    def _find_plan_character_row(
        conn: sqlite3.Connection,
        work_id: int,
        data: dict[str, Any],
    ) -> sqlite3.Row | None:
        row = None
        character_id = Repository._optional_int(data.get("id"))
        if character_id:
            row = conn.execute(
                "SELECT * FROM characters WHERE work_id = ? AND id = ?",
                (work_id, character_id),
            ).fetchone()
        if row is None:
            row = Repository._find_character_row_by_identity(conn, work_id, data)
        if row is None and Repository._role_contains(data, "主角"):
            row = conn.execute(
                """
                SELECT id, name, role
                FROM characters
                WHERE work_id = ?
                  AND (
                    role LIKE '%主角%' OR name LIKE '%主角%'
                    OR lower(role) LIKE '%protagonist%'
                  )
                ORDER BY id
                LIMIT 1
                """,
                (work_id,),
            ).fetchone()
        return row

    def _sync_outline_characters(self, work_id: int, outline: dict[str, Any] | None) -> None:
        if not outline:
            return
        names = self._character_names_from_outline(outline)
        if not names:
            return
        timestamp = now_text()
        with connect(self._db_path_for_work(work_id)) as conn:
            for name in names:
                name = normalize_character_name(name)
                if not name:
                    continue
                row = self._find_character_row_by_identity(conn, work_id, {"name": name})
                if row is not None:
                    continue
                cur = self._insert_character(
                    conn,
                    work_id,
                    {
                        "name": name,
                        "role": "待补充",
                        "personality": "",
                        "goal": "",
                        "relationship": "由章节细纲自动发现，请补充设定。",
                    },
                    timestamp,
                )
                self._insert_sync_event(
                    conn,
                    work_id=work_id,
                    chapter_id=None,
                    chapter_number=self._optional_int(outline.get("chapter_number")),
                    source="chapter_outline",
                    target_type="character",
                    target_id=int(cur.lastrowid),
                    target_name=name,
                    action="create_outline_character",
                    details={"name": name},
                    timestamp=timestamp,
                )
            conn.commit()

    @staticmethod
    def _character_names_from_outline(outline: dict[str, Any]) -> list[str]:
        raw = outline.get("characters_present") or ""
        if isinstance(raw, list):
            parts = [str(item) for item in raw]
        else:
            parts = re.split(r"[、,，/；;和与\s]+", str(raw))
        names: list[str] = []
        stop_words = {
            "主角",
            "配角",
            "反派",
            "男主",
            "女主",
            "角色",
            "人物",
            "相关人物",
            "本章目标相关的人物",
            "案件相关证人",
            "相关证人",
            "众人",
            "警方",
            "群众",
            "未知人物",
            "待补充",
        }
        for part in parts:
            name = part.strip()
            if not name or name in stop_words:
                continue
            if any(token in name for token in ["相关", "未知", "人物", "角色", "众人", "证人"]):
                continue
            if len(name) > 12:
                continue
            if name not in names:
                names.append(name)
        return names[:12]

    @staticmethod
    def _role_contains(character: dict[str, Any], keyword: str) -> bool:
        role = str(character.get("role") or "")
        name = str(character.get("name") or "")
        if keyword == "主角":
            return keyword in role or keyword in name or "protagonist" in role.lower()
        return keyword in role or keyword in name

    @staticmethod
    def _resolve_plot_thread(
        conn: sqlite3.Connection,
        *,
        work_id: int,
        chapter_id: int | None,
        chapter_number: int,
        content: str,
        actual_chapter: int,
        timestamp: str,
    ) -> None:
        rows = conn.execute(
            "SELECT id, content FROM plot_threads WHERE work_id = ? AND status = 'open'",
            (work_id,),
        ).fetchall()
        target_id: int | None = None
        best_ratio = 0.0
        for row in rows:
            existing = str(row["content"] or "")
            if not existing:
                continue
            if content in existing or existing in content:
                target_id = int(row["id"])
                break
            ratio = SequenceMatcher(None, existing, content).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                target_id = int(row["id"])
        if target_id is None or best_ratio < 0.45 and not any(content in str(row["content"] or "") or str(row["content"] or "") in content for row in rows):
            return
        conn.execute(
            """
            UPDATE plot_threads
            SET status = 'resolved', actual_resolve_chapter = ?, updated_at = ?
            WHERE id = ? AND work_id = ?
            """,
            (actual_chapter, timestamp, target_id, work_id),
        )
        Repository._insert_sync_event(
            conn,
            work_id=work_id,
            chapter_id=chapter_id,
            chapter_number=chapter_number,
            source="memory_card",
            target_type="plot_thread",
            target_id=target_id,
            target_name=content[:80],
            action="resolve_foreshadow",
            details={"content": content, "actual_resolve_chapter": actual_chapter},
            timestamp=timestamp,
        )

    @staticmethod
    def _insert_sync_event(
        conn: sqlite3.Connection,
        *,
        work_id: int,
        chapter_id: int | None,
        chapter_number: int | None,
        source: str,
        target_type: str,
        target_id: int | None,
        target_name: str,
        action: str,
        details: Any,
        timestamp: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO sync_events (
              work_id, chapter_id, chapter_number, source, target_type,
              target_id, target_name, action, details, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                work_id,
                chapter_id,
                chapter_number,
                source,
                target_type,
                target_id,
                target_name,
                action,
                json_dumps(details),
                timestamp,
            ),
        )

    @staticmethod
    def _clear_chapter_memory_side_effects(
        conn: sqlite3.Connection,
        work_id: int,
        chapter_number: int,
        timestamp: str,
    ) -> None:
        rows = conn.execute(
            """
            SELECT target_type, target_id, action, details
            FROM sync_events
            WHERE work_id = ?
              AND chapter_number = ?
              AND source = 'memory_card'
              AND target_id IS NOT NULL
            """,
            (work_id, chapter_number),
        ).fetchall()
        created_thread_ids = [
            int(row["target_id"])
            for row in rows
            if row["target_type"] == "plot_thread"
            and row["action"] == "create_foreshadow"
            and row["target_id"] is not None
        ]
        resolved_thread_ids = [
            int(row["target_id"])
            for row in rows
            if row["target_type"] == "plot_thread"
            and row["action"] == "resolve_foreshadow"
            and row["target_id"] is not None
        ]
        timeline_ids = [
            int(row["target_id"])
            for row in rows
            if row["target_type"] == "timeline"
            and row["action"] == "create_timeline_event"
            and row["target_id"] is not None
        ]
        historical_fact_ids = [
            int(row["target_id"])
            for row in rows
            if row["target_type"] == "historical_fact"
            and row["action"] == "create_historical_fact"
            and row["target_id"] is not None
        ]
        for thread_id in resolved_thread_ids:
            conn.execute(
                """
                UPDATE plot_threads
                SET status = 'open', actual_resolve_chapter = NULL, updated_at = ?
                WHERE id = ?
                  AND work_id = ?
                  AND status = 'resolved'
                  AND actual_resolve_chapter = ?
                """,
                (timestamp, thread_id, work_id, chapter_number),
            )
        for thread_id in created_thread_ids:
            conn.execute(
                "DELETE FROM plot_threads WHERE id = ? AND work_id = ?",
                (thread_id, work_id),
            )
        for timeline_id in timeline_ids:
            conn.execute(
                "DELETE FROM timeline WHERE id = ? AND work_id = ?",
                (timeline_id, work_id),
            )
        for fact_id in historical_fact_ids:
            conn.execute(
                "DELETE FROM historical_facts WHERE id = ? AND work_id = ?",
                (fact_id, work_id),
            )
        for row in rows:
            if row["target_type"] != "character" or row["action"] != "update_character_state":
                continue
            character_id = int(row["target_id"])
            try:
                details = json.loads(row["details"] or "{}")
            except json.JSONDecodeError:
                continue
            old_values = details.get("old_values") if isinstance(details, dict) else None
            if not isinstance(old_values, dict):
                continue
            current = conn.execute(
                """
                SELECT last_changed_chapter
                FROM characters
                WHERE id = ? AND work_id = ?
                """,
                (character_id, work_id),
            ).fetchone()
            if current is None or Repository._optional_int(current["last_changed_chapter"]) != chapter_number:
                continue
            conn.execute(
                """
                UPDATE characters
                SET current_goal = ?, current_fear = ?, current_state = ?,
                    relationship_stage = ?, secret_exposure = ?, arc_stage = ?,
                    arc_notes = ?, last_changed_chapter = ?, updated_at = ?
                WHERE id = ? AND work_id = ?
                """,
                (
                    old_values.get("current_goal", ""),
                    old_values.get("current_fear", ""),
                    old_values.get("current_state", ""),
                    old_values.get("relationship_stage", ""),
                    old_values.get("secret_exposure", ""),
                    old_values.get("arc_stage", ""),
                    old_values.get("arc_notes", ""),
                    Repository._optional_int(old_values.get("last_changed_chapter")),
                    timestamp,
                    character_id,
                    work_id,
                ),
            )
        conn.execute(
            """
            DELETE FROM sync_events
            WHERE work_id = ? AND chapter_number = ? AND source = 'memory_card'
            """,
            (work_id, chapter_number),
        )

    @staticmethod
    def _insert_world_rule(conn: sqlite3.Connection, work_id: int, data: dict[str, Any], timestamp: str) -> None:
        conn.execute(
            """
            INSERT INTO world_rules (
              work_id, rule_name, rule_content, limitations,
              forbidden_changes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                work_id,
                data.get("rule_name", ""),
                data.get("rule_content", ""),
                data.get("limitations", ""),
                data.get("forbidden_changes", ""),
                timestamp,
                timestamp,
            ),
        )

    @staticmethod
    def _upsert_historical_profile_from_plan(
        conn: sqlite3.Connection,
        work_id: int,
        inputs: dict[str, Any],
        plan: dict[str, Any],
        timestamp: str,
    ) -> None:
        profile = plan.get("historical_profile")
        if isinstance(profile, dict) and any(str(profile.get(key) or "").strip() for key in HISTORICAL_PROFILE_FIELDS):
            Repository._upsert_historical_profile(conn, work_id, profile, timestamp)
        elif is_historical_inputs(inputs):
            Repository._upsert_historical_profile(conn, work_id, default_historical_profile(inputs, plan), timestamp)

    @staticmethod
    def _upsert_historical_profile(
        conn: sqlite3.Connection,
        work_id: int,
        profile: dict[str, Any],
        timestamp: str,
    ) -> None:
        profile = compact_historical_profile(profile)
        conn.execute(
            """
            INSERT INTO historical_profiles (
              work_id, dynasty, period, year_range, political_context,
              official_system, military_system, social_order, daily_life,
              language_style, taboo_words, allowed_fiction, locked_facts,
              source_notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(work_id) DO UPDATE SET
              dynasty = excluded.dynasty,
              period = excluded.period,
              year_range = excluded.year_range,
              political_context = excluded.political_context,
              official_system = excluded.official_system,
              military_system = excluded.military_system,
              social_order = excluded.social_order,
              daily_life = excluded.daily_life,
              language_style = excluded.language_style,
              taboo_words = excluded.taboo_words,
              allowed_fiction = excluded.allowed_fiction,
              locked_facts = excluded.locked_facts,
              source_notes = excluded.source_notes,
              updated_at = excluded.updated_at
            """,
            (
                work_id,
                profile.get("dynasty", ""),
                profile.get("period", ""),
                profile.get("year_range", ""),
                profile.get("political_context", ""),
                profile.get("official_system", ""),
                profile.get("military_system", ""),
                profile.get("social_order", ""),
                profile.get("daily_life", ""),
                profile.get("language_style", ""),
                profile.get("taboo_words", ""),
                profile.get("allowed_fiction", ""),
                profile.get("locked_facts", ""),
                profile.get("source_notes", ""),
                timestamp,
                timestamp,
            ),
        )

    @staticmethod
    def _upsert_plan_world_rule(conn: sqlite3.Connection, work_id: int, data: dict[str, Any], timestamp: str) -> None:
        rule_name = str(data.get("rule_name", "") or "").strip()
        if not rule_name:
            return
        row = None
        rule_id = Repository._optional_int(data.get("id"))
        if rule_id:
            row = conn.execute(
                "SELECT id FROM world_rules WHERE work_id = ? AND id = ?",
                (work_id, rule_id),
            ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT id FROM world_rules WHERE work_id = ? AND rule_name = ?",
                (work_id, rule_name),
            ).fetchone()
        if row is None:
            Repository._insert_world_rule(conn, work_id, data, timestamp)
            return
        conn.execute(
            """
            UPDATE world_rules
            SET rule_name = ?, rule_content = ?, limitations = ?, forbidden_changes = ?,
                updated_at = ?
            WHERE id = ? AND work_id = ?
            """,
            (
                rule_name,
                data.get("rule_content", ""),
                data.get("limitations", ""),
                data.get("forbidden_changes", ""),
                timestamp,
                row["id"],
                work_id,
            ),
        )

    def _update_chapter_text(self, work_id: int, chapter_id: int, **fields: Any) -> None:
        allowed = {"title", "draft", "final_text", "ending_hook", "handoff", "memory_json", "status"}
        updates = {key: value for key, value in fields.items() if key in allowed and value is not None}
        updates["updated_at"] = now_text()
        assignments = ", ".join(f"{key} = ?" for key in updates)
        params = list(updates.values()) + [chapter_id]
        with connect(self._db_path_for_work(work_id)) as conn:
            conn.execute(f"UPDATE chapters SET {assignments} WHERE id = ?", params)
            conn.commit()

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
