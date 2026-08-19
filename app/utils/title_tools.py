from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any


_TITLE_NOISE_RE = re.compile(r"[\s\-—_·：:，,。！？!?\[\]【】()（）]+")
_GENERIC_TITLES = {
    "风波",
    "迷雾",
    "转机",
    "暗流",
    "余波",
    "变局",
    "前夜",
    "开端",
    "终局",
    "风起",
    "落子",
    "棋局",
    "暗线",
    "疑云",
    "夜宴",
    "抉择",
    "真相",
}
_BUREAUCRATIC_PASSIVE_RE = re.compile(
    r"(?:被|遭)(?:发回|退回|驳回|否决|撤销|取消|查封|并查|拒绝)$"
)
_TITLE_ACTION_CHARS = set("逼查开退归杀救取送逃拒改烧寻问还赢败破守追见失封夺换入出截拦扣验录留并锁携挡保")
_OBJECT_ENDINGS = (
    "门",
    "墙",
    "箱",
    "箱笼",
    "院",
    "房",
    "案",
    "纸",
    "灯",
    "信",
    "册",
    "刀",
    "剑",
    "车",
    "船",
)


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
    decision = candidates if isinstance(candidates, dict) else {}
    recommended = _clean_title(decision.get("recommended_title")) if decision else ""
    raw_candidates = decision.get("candidates") if decision else candidates
    cleaned = _title_candidates(raw_candidates)
    if not cleaned:
        return _clean_title(fallback)
    if recommended and recommended not in cleaned:
        cleaned.insert(0, recommended)
    recent = [_clean_title(item.get("title")) for item in recent_titles if isinstance(item, dict)]
    recent = [title for title in recent if title]

    if recommended:
        ranked = [recommended, *[title for title in cleaned if title != recommended]]
        for title in ranked:
            if not title_blockers(title, recent_titles):
                return title
        return _clean_title(fallback)

    scored = [(title_score(title, recent), -index, title) for index, title in enumerate(cleaned)]
    scored.sort(reverse=True)
    best_score, _, best = scored[0]
    # Legacy responses did not identify a semantic winner. When several
    # candidates are equally novel, preserve the planned title instead of
    # letting JSON array order make the editorial decision.
    tied = len(scored) > 1 and scored[1][0] == best_score
    fallback_title = _clean_title(fallback)
    if tied and fallback_title:
        return fallback_title
    return best if best_score > -60 else fallback_title


def title_blockers(title: Any, recent_titles: list[dict[str, Any]]) -> list[str]:
    cleaned = _clean_title(title)
    blockers: list[str] = []
    if len(cleaned) < 3 or len(cleaned) > 18:
        blockers.append("章节标题长度应为 3 到 18 个字符。")
    blockers.extend(title_warnings(cleaned, recent_titles))
    return list(dict.fromkeys(blockers))


def title_warnings(title: Any, recent_titles: list[dict[str, Any]]) -> list[str]:
    cleaned = _clean_title(title)
    if not cleaned:
        return ["章节标题为空。"]
    warnings: list[str] = []
    recent = [_clean_title(item.get("title")) for item in recent_titles if isinstance(item, dict)]
    recent = [item for item in recent if item]
    if cleaned in recent:
        warnings.append("章节标题与近章重复。")
    for recent_title in recent[-20:]:
        if cleaned == recent_title:
            continue
        if SequenceMatcher(None, _signature(cleaned), _signature(recent_title)).ratio() >= 0.72:
            warnings.append(f"章节标题与近章《{recent_title}》过于相似，应改用本章独有行动、发现或代价。")
            break
    structure = title_structure(cleaned)
    recent_structures = [title_structure(item) for item in recent[-5:]]
    if structure == "X之Y" and recent_structures.count(structure) >= 2:
        warnings.append("近五章已多次使用“X之Y”标题结构，本章应换成具体事件或人物选择。")
    if cleaned in _GENERIC_TITLES:
        warnings.append("章节标题过于抽象，未概括本章独有行动、发现、选择或代价。")
    if _BUREAUCRATIC_PASSIVE_RE.search(cleaned):
        warnings.append("章节标题像公文处理状态，缺少自然的小说语言。")
    if _looks_like_location_object_label(cleaned):
        warnings.append("章节标题只组合了地点方位和物件，未概括本章发生的核心变化。")
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
    if _BUREAUCRATIC_PASSIVE_RE.search(title):
        score -= 55
    if _looks_like_location_object_label(title):
        score -= 55
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


def _looks_like_location_object_label(title: str) -> bool:
    if any(char in title for char in _TITLE_ACTION_CHARS):
        return False
    if any(token in title for token in ("的", "之", "谁", "何", "为何", "怎会")):
        return False
    has_location = any(token in title for token in ("门内", "门外", "墙内", "墙外", "院内", "院外", "楼上", "楼下", "城内", "城外"))
    return bool(has_location and title.endswith(_OBJECT_ENDINGS))


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
