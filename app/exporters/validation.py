from __future__ import annotations

from typing import Any


def chapter_text(chapter: dict[str, Any], *, include_draft: bool) -> str:
    text = str(chapter.get("final_text") or "")
    if include_draft and not text.strip():
        text = str(chapter.get("draft") or "")
    return text.strip()


def validate_export_chapters(
    chapters: list[dict[str, Any]],
    *,
    include_draft: bool,
    start: int | None = None,
    end: int | None = None,
) -> list[tuple[dict[str, Any], str]]:
    if not chapters:
        raise ValueError("没有可导出的章节正文。请先生成或保存最终稿。")
    numbers = {int(item.get("chapter_number") or 0) for item in chapters}
    if start is None:
        start = 1
    if end is None:
        end = max(numbers or {0})
    expected = set(range(max(1, int(start)), max(1, int(end)) + 1))
    missing = sorted(expected - numbers)
    if missing:
        raise ValueError("导出范围缺少章节：" + "、".join(str(number) for number in missing[:20]))

    empty = [
        int(item.get("chapter_number") or 0)
        for item in chapters
        if not chapter_text(item, include_draft=include_draft)
    ]
    if empty:
        raise ValueError("导出范围存在空章节：" + "、".join(str(number) for number in empty[:20]))
    return [(item, chapter_text(item, include_draft=include_draft)) for item in chapters]
