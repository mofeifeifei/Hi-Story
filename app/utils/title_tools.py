from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


_TITLE_NOISE_RE = re.compile(r"[\s\-—_·：:，,。！？!?\[\]【】()（）]+")
_GENERIC_TITLES = {"风波", "迷雾", "转机", "暗流", "余波", "变局", "前夜", "开端", "终局"}


def title_ledger(chapters: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, str | int]]:
    entries: list[dict[str, str | int]] = []
    for chapter in chapters[-limit:]:
        title = _clean_title(chapter.get("title"))
        if not title:
            continue
        entries.append(
            {
                "chapter_number": int(chapter.get("chapter_number") or 0),
                "title": title,
                "structure": title_structure(title),
                "keywords": "、".join(title_keywords(title)),
            }
        )
    return entries


def choose_chapter_title(
    candidates: Any,
    recent_titles: list[dict[str, Any]],
    fallback: Any,
) -> str:
    cleaned = _title_candidates(candidates)
    if not cleaned:
        return _clean_title(fallback)
    recent = [_clean_title(item.get("title")) for item in recent_titles if isinstance(item, dict)]
    recent = [title for title in recent if title]
    scored = [(title_score(title, recent), -index, title) for index, title in enumerate(cleaned)]
    best_score, _, best = max(scored)
    return best if best_score > -60 else _clean_title(fallback)


def title_warnings(title: Any, recent_titles: list[dict[str, Any]]) -> list[str]:
    cleaned = _clean_title(title)
    if not cleaned:
        return ["章节标题为空。"]
    warnings: list[str] = []
    recent = [_clean_title(item.get("title")) for item in recent_titles if isinstance(item, dict)]
    recent = [item for item in recent if item]
    if cleaned in recent:
        warnings.append("章节标题与近章重复。")
    structure = title_structure(cleaned)
    recent_structures = [title_structure(item) for item in recent[-5:]]
    if structure == "X之Y" and recent_structures.count(structure) >= 2:
        warnings.append("近五章已多次使用“X之Y”标题结构，本章应换成具体事件或人物选择。")
    if len(cleaned) <= 2 and cleaned in _GENERIC_TITLES:
        warnings.append("章节标题过于抽象，未概括本章核心变化。")
    return warnings


def title_structure(title: Any) -> str:
    cleaned = _clean_title(title)
    if not cleaned:
        return ""
    if cleaned.count("之") == 1 and 3 <= len(cleaned) <= 10:
        return "X之Y"
    if cleaned.endswith(("令", "信", "案", "局", "夜", "日")):
        return "名词收束"
    if any(token in cleaned for token in ("谁", "何", "为何", "怎会")):
        return "疑问"
    if any(token in cleaned for token in ("入", "出", "夺", "换", "破", "守", "追", "见", "失", "封")):
        return "动作/变化"
    return "其他"


def title_keywords(title: Any) -> list[str]:
    cleaned = _clean_title(title)
    if len(cleaned) < 2:
        return []
    ignored = {"之", "的", "与", "和", "在", "了", "一", "这", "那"}
    return list(dict.fromkeys(char for char in cleaned if char not in ignored))[:8]


def title_score(title: str, recent_titles: list[str]) -> int:
    score = 100
    if len(title) < 3 or len(title) > 18:
        score -= 50
    if title in _GENERIC_TITLES:
        score -= 45
    structure = title_structure(title)
    recent_structures = [title_structure(item) for item in recent_titles[-5:]]
    if structure == "X之Y":
        score -= 18 * recent_structures.count(structure)
    for recent in recent_titles:
        if title == recent:
            return -100
        if SequenceMatcher(None, _signature(title), _signature(recent)).ratio() >= 0.72:
            score -= 45
        elif _keyword_overlap(title, recent) >= 0.75:
            score -= 20
    return score


def _title_candidates(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else [value]
    candidates: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            item = item.get("title") or item.get("name") or item.get("text")
        title = _clean_title(item)
        if title and title not in candidates:
            candidates.append(title)
    return candidates[:8]


def _clean_title(value: Any) -> str:
    title = str(value or "").strip().strip("\"“”‘’")
    title = re.sub(r"^(?:第\s*[0-9一二三四五六七八九十百千]+\s*[章节回集]\s*[:：\-—]?|章节名\s*[:：]|标题\s*[:：])", "", title)
    return title.strip()


def _signature(title: str) -> str:
    return _TITLE_NOISE_RE.sub("", title)


def _keyword_overlap(left: str, right: str) -> float:
    left_keywords = set(title_keywords(left))
    right_keywords = set(title_keywords(right))
    if not left_keywords or not right_keywords:
        return 0.0
    return len(left_keywords & right_keywords) / min(len(left_keywords), len(right_keywords))
