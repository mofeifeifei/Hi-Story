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

_PLOT_SUMMARY_PATTERNS = (
    re.compile(r"^.{0,8}(?:改成|改为|写成|记成|变成|定为).{1,10}$"),
    re.compile(r"(?:被|已|终于|随即|正式)(?:确认|查明|证实|解决|揭开|否决|驳回|撤销|封存)$"),
    re.compile(r"(?:问题|误会|身份|去向|真相|案子|记录|名单|账目)(?:得到|获得|已经|终于)?(?:解决|确认|查明|揭开|证实)$"),
)
_NOVEL_TITLE_ACTION_CHARS = set("拿扣逼问挡换护追救逃守认撕烧藏赌押借等见听说笑哭回望进退开合离留")

TITLE_GATE_PASS_SCORE = 82
_TITLE_GATE_MINIMUMS = {
    "text_fidelity": 18,
    "core_change": 18,
    "character_action": 8,
    "naturalness": 10,
}


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


def choose_title_gate_result(
    adjudication: Any,
    recent_titles: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the strongest title that cleared both semantic and local checks."""
    if not isinstance(adjudication, dict):
        return None
    assessments = adjudication.get("assessments")
    if not isinstance(assessments, list):
        return None
    recommended = _clean_title(adjudication.get("recommended_title"))
    accepted: list[dict[str, Any]] = []
    for index, item in enumerate(assessments):
        if not isinstance(item, dict):
            continue
        title = _clean_title(item.get("title"))
        scores = item.get("scores") if isinstance(item.get("scores"), dict) else {}
        local_blockers = title_blockers(title, recent_titles)
        is_plot_summary = item.get("is_plot_summary") is True
        is_novel_title = item.get("is_novel_title") is True
        if (
            not title
            or bool(item.get("hard_reject"))
            or not bool(item.get("accepted"))
            or local_blockers
            or not _title_gate_score_passes(scores)
            or is_plot_summary
            or not is_novel_title
        ):
            continue
        accepted.append(
            {
                "title": title,
                "evidence": str(item.get("evidence") or "").strip(),
                "scores": scores,
                "is_plot_summary": is_plot_summary,
                "is_novel_title": is_novel_title,
                "style_type": str(item.get("style_type") or "other"),
                "issues": item.get("issues") if isinstance(item.get("issues"), list) else [],
                "is_recommended": title == recommended,
                "index": index,
            }
        )
    if not accepted:
        return None
    accepted.sort(
        key=lambda item: (
            int(item["scores"].get("total") or 0),
            int(item["scores"].get("text_fidelity") or 0),
            int(item["scores"].get("core_change") or 0),
            int(item["scores"].get("naturalness") or 0),
            int(item["is_recommended"]),
            -int(item["index"]),
        ),
        reverse=True,
    )
    return accepted[0]


def title_gate_feedback(adjudication: Any, recent_titles: list[dict[str, Any]]) -> list[str]:
    """Produce concise, actionable reasons for one bounded regeneration pass."""
    feedback: list[str] = []
    if not isinstance(adjudication, dict):
        return ["标题研判结果无效，需从正文核心变化重新拟题。"]
    for item in adjudication.get("assessments", []) if isinstance(adjudication.get("assessments"), list) else []:
        if not isinstance(item, dict):
            continue
        title = _clean_title(item.get("title")) or "候选标题"
        reasons = [str(value).strip() for value in item.get("issues", []) if str(value).strip()]
        reasons.extend(title_blockers(title, recent_titles))
        scores = item.get("scores") if isinstance(item.get("scores"), dict) else {}
        if not _title_gate_score_passes(scores):
            reasons.append("没有同时概括正文事实、核心变化、人物行动和阅读回报。")
        if item.get("is_plot_summary") is True:
            reasons.append("标题像剧情摘要或案卷结果，需改成更自然的小说标题。")
        if item.get("is_novel_title") is not True:
            reasons.append("标题缺少小说标题感，不能只是地点、物件或抽象状态的标签。")
        if bool(item.get("hard_reject")):
            reasons.append("存在误导、无正文依据或泄露反转的风险。")
        for reason in dict.fromkeys(reasons):
            feedback.append(f"《{title}》：{reason}")
    return list(dict.fromkeys(feedback))[:8] or ["候选标题未能概括本章已经发生的核心行动和变化。"]


def title_gate_status_text(status: Any) -> str:
    value = str(status or "").strip().lower()
    return {
        "final": "标题已研判",
        "provisional": "暂定标题",
        "pending": "标题待确认",
        "manual": "手动标题",
    }.get(value, "标题待确认")


def _title_gate_score_passes(scores: Any) -> bool:
    if not isinstance(scores, dict):
        return False
    try:
        total = int(scores.get("total") or 0)
        return total >= TITLE_GATE_PASS_SCORE and all(
            int(scores.get(key) or 0) >= minimum
            for key, minimum in _TITLE_GATE_MINIMUMS.items()
        )
    except (TypeError, ValueError):
        return False


def title_blockers(title: Any, recent_titles: list[dict[str, Any]]) -> list[str]:
    cleaned = _clean_title(title)
    blockers: list[str] = []
    if len(cleaned) < 2 or len(cleaned) > 18:
        blockers.append("章节标题长度应为 2 到 18 个字符。")
    if cleaned in {_clean_title(item.get("title")) for item in recent_titles if isinstance(item, dict)}:
        blockers.append("章节标题与近章完全重复。")
    return list(dict.fromkeys(blockers))


def title_warnings(
    title: Any,
    recent_titles: list[dict[str, Any]],
    brief: dict[str, Any] | None = None,
) -> list[str]:
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
    if title_is_plot_summary(cleaned):
        warnings.append("标题带有剧情摘要腔，像在记录结果，而不是提炼本章的行动、选择或关系变化。")
    if brief is not None and not title_has_novel_anchor(cleaned, brief):
        warnings.append("标题缺少可感知的行动、选择、关系变化或具体意象。")
    return warnings


def title_is_plot_summary(title: Any) -> bool:
    """Detect result-report phrasing without banning ordinary genre vocabulary."""
    cleaned = _clean_title(title)
    if not cleaned:
        return False
    return any(pattern.search(cleaned) for pattern in _PLOT_SUMMARY_PATTERNS)


def title_has_novel_anchor(title: Any, brief: dict[str, Any]) -> bool:
    """Return whether a title carries an action, choice, relationship, or image anchor."""
    cleaned = _clean_title(title)
    if len(cleaned) < 3:
        return False
    if title_is_plot_summary(cleaned) or _looks_like_location_object_label(cleaned):
        return False
    if any(char in cleaned for char in _NOVEL_TITLE_ACTION_CHARS):
        return True
    contract = brief.get("outline_contract") if isinstance(brief, dict) else {}
    fact_card = brief.get("fact_card") if isinstance(brief, dict) else {}
    source = " ".join(
        str(value or "")
        for value in [
            *(contract.values() if isinstance(contract, dict) else []),
            *(fact_card.values() if isinstance(fact_card, dict) else []),
        ]
    )
    return bool(source and any(keyword in source for keyword in cleaned[:4]))


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
    if len(title) < 2 or len(title) > 18:
        score -= 50
    if title in _GENERIC_TITLES:
        score -= 18
    if title_is_plot_summary(title):
        score -= 30
    if _BUREAUCRATIC_PASSIVE_RE.search(title):
        score -= 55
    if _looks_like_location_object_label(title):
        score -= 25
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
