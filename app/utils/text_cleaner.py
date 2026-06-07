from __future__ import annotations

import re
from typing import Any


_CHINESE_DIGITS = "零〇一二两三四五六七八九十百千万"
_HEADING_PREFIX_RE = re.compile(
    rf"^\s*(?:[#＃]+\s*)?(?:第\s*[\d{_CHINESE_DIGITS}]+\s*[章节回集卷幕]\s*)"
)


def strip_chapter_heading(text: str, chapter_number: int | None = None, chapter_title: Any = "") -> str:
    """Remove accidental chapter title lines from the beginning of manuscript text."""
    if not text:
        return ""
    title = _compact_heading(chapter_title)
    lines = str(text).splitlines()
    removed = 0
    while removed < min(3, len(lines)) and _is_heading_line(lines[removed], chapter_number, title):
        removed += 1
    return "\n".join(lines[removed:]).lstrip()


def _is_heading_line(line: str, chapter_number: int | None, title: str) -> bool:
    compact = _compact_heading(line)
    if not compact:
        return True
    without_markdown = _compact_heading(re.sub(r"^\s*[#＃]+\s*", "", line))
    if title and without_markdown == title:
        return True
    if _HEADING_PREFIX_RE.match(line) and len(compact) <= 30:
        return True
    if (
        chapter_number
        and len(compact) <= 30
        and re.match(rf"^\s*(?:[#＃]+\s*)?第\s*{int(chapter_number)}\s*[章节回集卷幕]", line)
    ):
        return True
    return False


def _compact_heading(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^\s*[#＃]+\s*", "", text)
    text = re.sub(r"[\s　:：,，.。;；、\-—_·《》〈〉「」『』【】\[\]()（）]+", "", text)
    return text
