from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from app.utils.json_parser import json_dumps, parse_json_object


CHAPTER_OUTLINE_FIELDS: list[tuple[str, str]] = [
    ("story_time", "故事时间"),
    ("opening_hook", "开篇钩子"),
    ("continuity_debt", "承接债"),
    ("debt_type", "承接类型"),
    ("opening_mode", "开头方式"),
    ("opening_subject", "开头主体"),
    ("opening_trigger", "开头触发事件"),
    ("time_or_environment_function", "时间/环境功能"),
    ("previous_anchor", "上一章锚点"),
    ("first_screen_conflict", "第一屏冲突"),
    ("forbidden_opening", "禁止开头"),
    ("reader_question_in", "入章问题"),
    ("reader_answer_out", "本章回答"),
    ("new_question_out", "新问题"),
    ("chapter_goal", "本章目标"),
    ("reader_expectation", "读者期待"),
    ("conflict", "核心冲突"),
    ("main_scene", "主要场景"),
    ("characters_present", "出场人物"),
    ("clues", "推进线索"),
    ("new_information", "新增信息"),
    ("chapter_payoff", "本章回报"),
    ("character_change", "人物变化"),
    ("foreshadowing", "伏笔安排"),
    ("emotional_turn", "情绪转折"),
    ("emotional_rhythm", "情绪节奏"),
    ("ending_external_anchor", "结尾外部锚点"),
    ("next_opening_action", "下一章开场动作"),
    ("next_continuity_debt", "下一章承接债"),
    ("handoff", "下一章接力棒"),
    ("forbidden", "本章禁止事项"),
]

SCENE_CARD_FIELDS: list[tuple[str, str]] = [
    ("scene_goal", "场景目标"),
    ("obstacle", "阻力"),
    ("information_gain", "信息增量"),
    ("emotional_shift", "情绪变化"),
    ("scene_exit", "场景出口"),
]

SCENE_CARD_LABELS = dict(SCENE_CARD_FIELDS)

GENERIC_OUTLINE_PHRASES = [
    "承接前文",
    "全书大纲",
    "推进本章核心冲突",
    "具体证据",
    "人物交锋",
    "章末钩子",
    "下一章钩子",
    "继续调查",
    "留下悬念",
]


def parse_outline_detail(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    parsed = parse_json_object(value, default={})
    return parsed if isinstance(parsed, dict) else {}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(_stringify(item) for item in value if _stringify(item))
    if isinstance(value, dict):
        return "\n".join(f"{key}：{_stringify(val)}" for key, val in value.items() if _stringify(val))
    return str(value).strip()


def _trim_join_punctuation(value: str) -> str:
    return value.strip().rstrip("。；;，,、")


def _scene_cards_from_value(value: Any) -> Any:
    if isinstance(value, str):
        parsed = parse_json_object(value, default=None)
        return parsed if parsed is not None else value.strip()
    return value or []


def _scene_card_parts(card: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    for key, label in SCENE_CARD_FIELDS:
        text = _trim_join_punctuation(_stringify(card.get(key)))
        if text:
            parts.append(f"{label}：{text}")
    for key, val in card.items():
        if key in SCENE_CARD_LABELS:
            continue
        text = _trim_join_punctuation(_stringify(val))
        if text:
            parts.append(f"{key}：{text}")
    return parts


def scene_cards_to_text(value: Any) -> str:
    cards = _scene_cards_from_value(value)
    if isinstance(cards, list):
        lines: list[str] = []
        for index, card in enumerate(cards, 1):
            if isinstance(card, dict):
                parts = _scene_card_parts(card)
                if parts:
                    lines.append(f"{index}. " + "；".join(parts))
            elif _stringify(card):
                lines.append(f"{index}. {_stringify(card)}")
        return "\n".join(lines)
    if isinstance(cards, dict):
        return "\n".join(_scene_card_parts(cards))
    return _stringify(cards)


def normalize_chapter_outline(chapter: dict[str, Any]) -> dict[str, Any]:
    detail = parse_outline_detail(chapter.get("outline_json"))
    normalized: dict[str, Any] = {}
    for key in ["id", "chapter_number", "volume_number", "title", "status"]:
        value = chapter.get(key)
        if value in (None, ""):
            value = detail.get(key)
        if value not in (None, ""):
            normalized[key] = value
    for key in ["outline", "ending_hook", *[field for field, _ in CHAPTER_OUTLINE_FIELDS]]:
        value = chapter.get(key)
        if value in (None, ""):
            value = detail.get(key)
        normalized[key] = _stringify(value)
    scene_cards = chapter.get("scene_cards")
    if scene_cards in (None, ""):
        scene_cards = chapter.get("scene_cards_json")
    if scene_cards in (None, ""):
        scene_cards = detail.get("scene_cards")
    normalized["scene_cards"] = _scene_cards_from_value(scene_cards)
    return normalized


def chapter_outline_payload(chapter: dict[str, Any]) -> dict[str, Any]:
    detail = normalize_chapter_outline(chapter)
    return {
        "chapter_number": detail.get("chapter_number", ""),
        "volume_number": detail.get("volume_number", ""),
        "title": detail.get("title", ""),
        "outline": detail.get("outline", ""),
        "ending_hook": detail.get("ending_hook", ""),
        "scene_cards": detail.get("scene_cards", []),
        **{key: detail.get(key, "") for key, _ in CHAPTER_OUTLINE_FIELDS},
    }


def chapter_outline_json(chapter: dict[str, Any]) -> str:
    return json_dumps(chapter_outline_payload(chapter))


def outline_text_for_prompt(chapter: dict[str, Any]) -> str:
    detail = normalize_chapter_outline(chapter)
    lines: list[str] = []
    if detail.get("volume_number"):
        lines.append(f"所属卷：第{detail['volume_number']}卷")
    if detail.get("chapter_number"):
        lines.append(f"章节：第{detail['chapter_number']}章")
    if detail.get("outline"):
        lines.append(f"细纲：{detail['outline']}")
    if detail.get("scene_cards"):
        lines.append("场景卡：")
        lines.append(scene_cards_to_text(detail.get("scene_cards")))
    for key, label in CHAPTER_OUTLINE_FIELDS:
        value = detail.get(key, "")
        if value:
            lines.append(f"{label}：{value}")
    if detail.get("ending_hook"):
        lines.append(f"结尾钩子：{detail['ending_hook']}")
    return "\n".join(lines)


def outline_quality_issues(chapter: dict[str, Any]) -> list[str]:
    detail = normalize_chapter_outline(chapter)
    outline = detail.get("outline", "")
    hook = detail.get("ending_hook", "")
    combined = outline_text_for_prompt(detail)
    issues: list[str] = []
    if not outline.strip():
        issues.append("细纲为空")
    if len(combined) < 80:
        issues.append("细纲过短，无法指导正文生成")
    if not hook.strip():
        issues.append("缺少结尾钩子")
    if not detail.get("conflict", "").strip() and "冲突" not in outline:
        issues.append("缺少明确核心冲突")
    if not detail.get("new_information", "").strip() and "线索" not in outline and "信息" not in outline:
        issues.append("缺少本章信息增量")
    if not detail.get("reader_expectation", "").strip():
        issues.append("缺少读者期待说明")
    if not detail.get("chapter_payoff", "").strip():
        issues.append("缺少本章阅读回报")
    scene_cards = _scene_cards_from_value(detail.get("scene_cards", ""))
    if not scene_cards_to_text(scene_cards).strip():
        issues.append("缺少章节场景卡")
    elif isinstance(scene_cards, list) and len(scene_cards) < 3:
        issues.append("章节场景卡少于 3 个")
    if not detail.get("opening_hook", "").strip():
        issues.append("缺少开篇钩子")
    if not detail.get("continuity_debt", "").strip() and int(detail.get("chapter_number") or 1) > 1:
        issues.append("缺少承接债")
    if not detail.get("opening_mode", "").strip():
        issues.append("缺少开头方式")
    if not detail.get("opening_trigger", "").strip():
        issues.append("缺少开头触发事件")
    if not detail.get("reader_question_in", "").strip():
        issues.append("缺少入章问题")
    if not detail.get("reader_answer_out", "").strip():
        issues.append("缺少本章回答")
    if not detail.get("new_question_out", "").strip():
        issues.append("缺少新问题")
    if not detail.get("next_continuity_debt", "").strip():
        issues.append("缺少下一章承接债")
    if not detail.get("handoff", "").strip():
        issues.append("缺少下一章接力棒")
    generic_hits = [phrase for phrase in GENERIC_OUTLINE_PHRASES if phrase in combined]
    if len(generic_hits) >= 3:
        issues.append("细纲包含过多占位式套话：" + "、".join(generic_hits[:4]))
    return issues


def blocking_outline_issues(chapter: dict[str, Any]) -> list[str]:
    issues = outline_quality_issues(chapter)
    blockers = []
    for issue in issues:
        if issue.startswith((
            "细纲为空",
            "细纲过短",
            "缺少结尾钩子",
            "缺少章节场景卡",
            "章节场景卡少于",
            "缺少开篇钩子",
            "缺少承接债",
            "缺少开头方式",
            "缺少开头触发事件",
            "缺少入章问题",
            "缺少本章回答",
            "缺少新问题",
            "缺少下一章承接债",
            "缺少下一章接力棒",
            "细纲包含过多",
        )):
            blockers.append(issue)
    return blockers


def duplicate_outline_groups(chapters: list[dict[str, Any]]) -> list[list[int]]:
    seen: dict[str, list[int]] = {}
    for chapter in chapters:
        detail = normalize_chapter_outline(chapter)
        text = outline_text_for_prompt(detail)
        text = re.sub(r"第\s*\d+\s*章", "第N章", text)
        text = re.sub(r"\d+", "N", text)
        signature = re.sub(r"\s+", "", text)
        if len(signature) < 40:
            continue
        number = int(detail.get("chapter_number") or 0)
        seen.setdefault(signature, []).append(number)
    return [numbers for numbers in seen.values() if len(numbers) > 1]


def repeat_risk_warnings(chapter: dict[str, Any], recent_chapters: list[dict[str, Any]]) -> list[str]:
    current = normalize_chapter_outline(chapter)
    current_text = _signature(outline_text_for_prompt(current))
    current_hook = _signature(current.get("ending_hook", ""))
    current_scene = _signature(current.get("main_scene", ""))
    warnings: list[str] = []
    for previous in recent_chapters:
        previous_detail = normalize_chapter_outline(previous)
        previous_number = previous_detail.get("chapter_number") or "前文"
        previous_text = _signature(outline_text_for_prompt(previous_detail))
        previous_hook = _signature(previous_detail.get("ending_hook", ""))
        previous_scene = _signature(previous_detail.get("main_scene", ""))
        if len(current_text) >= 40 and len(previous_text) >= 40:
            ratio = SequenceMatcher(None, current_text, previous_text).ratio()
            if ratio >= 0.62:
                warnings.append(f"第{previous_number}章与本章细纲结构相似度偏高")
        if current_hook and previous_hook and SequenceMatcher(None, current_hook, previous_hook).ratio() >= 0.7:
            warnings.append(f"第{previous_number}章与本章结尾钩子相似")
        if current_scene and previous_scene and current_scene == previous_scene:
            warnings.append(f"第{previous_number}章与本章主要场景相同，需要确保信息和阻力不同")
    return warnings


def _signature(text: Any) -> str:
    return re.sub(r"\s+", "", _stringify(text))
