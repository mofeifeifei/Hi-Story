from __future__ import annotations

import re
from pathlib import Path
from typing import Any


INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]+')
SPACE_CHARS = re.compile(r"\s+")


def safe_filename(value: str, fallback: str = "未命名") -> str:
    cleaned = INVALID_FILENAME_CHARS.sub("-", value or "")
    cleaned = SPACE_CHARS.sub(" ", cleaned).strip(" .")
    return cleaned or fallback


def work_export_dir(work: dict[str, Any], root: Path | str | None = None) -> Path:
    if root is None and work.get("_export_dir"):
        return Path(str(work["_export_dir"]))
    root = root or "exports"
    title = safe_filename(work.get("title") or "未命名作品")
    return Path(root) / title


def book_export_path(work: dict[str, Any], extension: str, root: Path | str | None = None) -> Path:
    title = safe_filename(work.get("title") or "未命名作品")
    return work_export_dir(work, root) / f"{title}-整本导出.{extension.lstrip('.')}"


def chapter_export_path(
    work: dict[str, Any],
    chapter: dict[str, Any],
    extension: str,
    root: Path | str | None = None,
) -> Path:
    work_title = safe_filename(work.get("title") or "未命名作品")
    chapter_number = int(chapter.get("chapter_number") or 0)
    chapter_title = safe_filename(chapter.get("title") or f"第{chapter_number}章")
    file_name = f"{work_title}-第{chapter_number:03d}章-{chapter_title}.{extension.lstrip('.')}"
    return work_export_dir(work, root) / file_name


def chapter_range_export_path(
    work: dict[str, Any],
    start_chapter: int,
    end_chapter: int,
    extension: str,
    root: Path | str | None = None,
) -> Path:
    work_title = safe_filename(work.get("title") or "未命名作品")
    file_name = f"{work_title}-第{start_chapter:03d}-{end_chapter:03d}章.{extension.lstrip('.')}"
    return work_export_dir(work, root) / file_name
