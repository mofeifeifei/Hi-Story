from __future__ import annotations

from ast import literal_eval
from copy import deepcopy
import re
from typing import Any, Callable

from app.utils.name_normalizer import character_identity_key, normalize_character_name
from app.utils.validators import (
    validate_chapter_outlines,
    validate_memory_card,
    validate_outline,
    validate_review,
    validate_work_plan,
)


Validator = Callable[[Any], list[str]]


class ContractError(ValueError):
    pass


def normalize_work_plan(data: Any) -> dict[str, Any]:
    plan = _object_or_empty(data)
    plan.setdefault("book_bible", {})
    plan.setdefault("book_contract", {})
    plan.setdefault("title_candidates", [])
    plan.setdefault("summary", "")
    plan.setdefault("core_selling_points", [])
    plan.setdefault("target_readers", "")
    plan.setdefault("protagonist", {})
    plan.setdefault("supporting_characters", [])
    plan.setdefault("villains", [])
    plan.setdefault("world_rules", [])
    plan.setdefault("main_goal", "")
    plan.setdefault("first_volume_direction", "")
    plan.setdefault("historical_profile", {})
    plan.setdefault("warnings", [])
    _normalize_plan_characters(plan)
    return plan


def normalize_outline(data: Any) -> dict[str, Any]:
    outline = _object_or_empty(data)
    outline.setdefault("full_outline", "")
    outline.setdefault("volume_outline", [])
    if isinstance(outline["volume_outline"], list):
        normalized_volumes = []
        for volume in outline["volume_outline"]:
            if not isinstance(volume, dict):
                continue
            item = dict(volume)
            item.setdefault("target_chapters", "")
            item.setdefault("min_chapters", "")
            item.setdefault("soft_max_chapters", "")
            item.setdefault("hard_max_chapters", "")
            item.setdefault("entry_condition", "")
            item.setdefault("exit_condition", "")
            item.setdefault("required_milestones", [])
            normalized_volumes.append(item)
        outline["volume_outline"] = normalized_volumes
    return outline


def normalize_chapter_outlines(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        data = {"chapters": data}
    result = _object_or_empty(data)
    if "chapters" not in result:
        for key in ["chapter_outlines", "chapterOutlines", "items"]:
            if isinstance(result.get(key), list):
                result["chapters"] = result[key]
                break
    decision = result.get("volume_decision")
    if not isinstance(decision, dict):
        decision = {}
    for key in [
        "should_transition",
        "from_volume",
        "to_volume",
        "reason",
        "completed_milestones",
        "unfinished_milestones",
        "carry_over",
        "next_volume_opening_focus",
    ]:
        default: Any = [] if key in {"completed_milestones", "unfinished_milestones", "carry_over"} else ""
        if key == "should_transition":
            default = False
        decision.setdefault(key, default)
    for key in ["completed_milestones", "unfinished_milestones", "carry_over"]:
        if not isinstance(decision.get(key), list):
            decision[key] = []
    result["volume_decision"] = decision
    chapters = result.get("chapters")
    if not isinstance(chapters, list):
        result["chapters"] = []
        return result
    normalized_chapters: list[dict[str, Any]] = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        item = dict(chapter)
        item.setdefault("volume_number", "")
        item.setdefault("scene_cards", [])
        item.setdefault("sequence_id", "")
        item.setdefault("sequence_goal", "")
        item.setdefault("sequence_position", "")
        item.setdefault("scene_id", "")
        item.setdefault("continuity_mode", "direct")
        item.setdefault("story_time", "")
        item.setdefault("opening_hook", "")
        item.setdefault("continuity_debt", "")
        item.setdefault("debt_type", "")
        item.setdefault("opening_mode", "")
        item.setdefault("opening_subject", "")
        item.setdefault("allowed_shift", False)
        item.setdefault("shift_reason", "")
        item.setdefault("opening_trigger", "")
        item.setdefault("time_or_environment_function", "")
        item.setdefault("previous_anchor", "")
        item.setdefault("first_screen_conflict", "")
        item.setdefault("forbidden_opening", "")
        item.setdefault("reader_question_in", "")
        item.setdefault("reader_answer_out", "")
        item.setdefault("new_question_out", "")
        item.setdefault("chapter_goal", "")
        item.setdefault("reader_expectation", "")
        item.setdefault("conflict", "")
        item.setdefault("main_scene", "")
        item.setdefault("characters_present", "")
        item.setdefault("clues", "")
        item.setdefault("new_information", "")
        item.setdefault("chapter_payoff", "")
        item.setdefault("character_change", "")
        item.setdefault("foreshadowing", "")
        item.setdefault("emotional_turn", "")
        item.setdefault("emotional_rhythm", "")
        item.setdefault("ending_external_anchor", "")
        item.setdefault("next_opening_action", "")
        item.setdefault("next_continuity_debt", "")
        item.setdefault("ending_hook", "")
        item.setdefault("cut_reason", "")
        item.setdefault("handoff", "")
        item.setdefault("forbidden", "")
        for key in ["chapter_goal", "chapter_payoff", "opening_hook", "ending_hook"]:
            item[key] = _remove_visible_protocol_labels(item.get(key))
        item = localize_visible_protocol_terms(item)
        _fill_missing_ending_hook(item)
        normalized_chapters.append(item)
    result["chapters"] = normalized_chapters
    return result


def _fill_missing_ending_hook(item: dict[str, Any]) -> None:
    if str(item.get("ending_hook") or "").strip():
        return
    anchor = (
        str(item.get("ending_external_anchor") or "").strip()
        or str(item.get("next_continuity_debt") or "").strip()
        or str(item.get("next_opening_action") or "").strip()
        or str(item.get("handoff") or "").strip()
    )
    if anchor:
        item["ending_hook"] = f"承接压力：{anchor}"


def normalize_review(data: Any, *, template_hits: list[str] | None = None) -> dict[str, Any]:
    review = _object_or_empty(data)
    for key in [
        "continuity_score",
        "character_score",
        "emotion_score",
        "rhythm_score",
        "foreshadow_score",
        "payoff_score",
        "hook_score",
        "historical_score",
        "readability_score",
        "length_score",
    ]:
        review.setdefault(key, 0)
    review.setdefault("length_problem", "")
    review.setdefault("repeat_risk", [])
    review["problems"] = _normalize_review_problems(review.get("problems"))
    review["suggestions"] = _normalize_review_suggestions(review.get("suggestions"))
    review["revision_plan"] = _normalize_revision_plan(review.get("revision_plan"))
    review.setdefault("revision_check", {})
    if not isinstance(review["revision_check"], dict):
        review["revision_check"] = {}
    review.setdefault("template_hits", template_hits or [])
    review.setdefault("risk_flags", [])
    review.setdefault("title_candidates", [])
    if not isinstance(review["title_candidates"], list):
        review["title_candidates"] = []
    return review


def _normalize_review_problems(value: Any) -> list[Any]:
    normalized: list[Any] = []
    for item in value if isinstance(value, list) else ([] if value in (None, "") else [value]):
        item = _review_mapping(item) or item
        if isinstance(item, dict):
            evidence = str(item.get("evidence") or "").strip()
            why_it_matters = str(item.get("why_it_matters") or "").strip()
            problem_type = str(item.get("type") or "narrative").strip() or "narrative"
            severity = str(item.get("severity") or "medium").strip().lower()
        else:
            normalized.append(item)
            continue
        if not evidence:
            continue
        if severity not in {"low", "medium", "high"}:
            severity = "medium"
        normalized.append(
            {
                "type": problem_type,
                "severity": severity,
                "evidence": evidence,
                "why_it_matters": why_it_matters or "该问题会削弱章节的连贯性、推进感或阅读体验。",
            }
        )
    return normalized


def _normalize_review_suggestions(value: Any) -> list[Any]:
    normalized: list[Any] = []
    for item in value if isinstance(value, list) else ([] if value in (None, "") else [value]):
        item = _review_mapping(item) or item
        if isinstance(item, dict):
            target = str(item.get("target") or "").strip()
            action = str(item.get("action") or "").strip()
            keep = str(item.get("keep") or "").strip()
            avoid = str(item.get("avoid") or "").strip()
        else:
            normalized.append(item)
            continue
        if not action:
            normalized.append(item)
            continue
        normalized.append(
            {
                "target": target,
                "action": action,
                "keep": keep,
                "avoid": avoid,
            }
        )
    return normalized


def _normalize_revision_plan(value: Any) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    values = value if isinstance(value, list) else []
    for item in values:
        item = _review_mapping(item)
        if not item:
            continue
        action = str(item.get("action") or "").strip()
        if not action:
            continue
        normalized.append(
            {
                "type": str(item.get("type") or "structure").strip() or "structure",
                "priority": str(item.get("priority") or "").strip(),
                "target": str(item.get("target") or "").strip(),
                "evidence": str(item.get("evidence") or "").strip(),
                "action": action,
                "keep": str(item.get("keep") or "").strip(),
                "avoid": str(item.get("avoid") or "").strip(),
            }
        )
    return normalized


def _review_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text.startswith("{") or len(text) > 20_000:
        return None
    try:
        parsed = literal_eval(text)
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return None
    return parsed if isinstance(parsed, dict) else None


def normalize_memory_card(data: Any) -> dict[str, Any]:
    memory = _object_or_empty(data)
    memory.setdefault("summary", "")
    memory.setdefault("character_changes", [])
    memory.setdefault("new_foreshadows", [])
    memory.setdefault("character_state_updates", [])
    memory.setdefault("resolved_foreshadows", [])
    memory.setdefault("timeline_events", [])
    memory.setdefault("ability_changes", [])
    memory.setdefault("relationship_changes", [])
    memory.setdefault("historical_updates", [])
    memory.setdefault("chapter_result_card", {})
    result_card = memory.get("chapter_result_card")
    if not isinstance(result_card, dict):
        result_card = {}
    for key in ["core_change", "reader_payoff", "key_action", "key_cost", "title_reason"]:
        result_card.setdefault(key, "")
    result_card.setdefault("title_candidates", [])
    if not isinstance(result_card["title_candidates"], list):
        result_card["title_candidates"] = []
    memory["chapter_result_card"] = result_card
    if isinstance(memory["historical_updates"], list):
        normalized_history = []
        for item in memory["historical_updates"]:
            if not isinstance(item, dict):
                continue
            update = dict(item)
            update.setdefault("category", "")
            update.setdefault("name", "")
            update.setdefault("content", "")
            update.setdefault("source_type", "memory_card")
            update.setdefault("certainty", "")
            update.setdefault("fictionalized", False)
            update.setdefault("chapter_impact", "")
            update.setdefault("future_constraint", "")
            normalized_history.append(update)
        memory["historical_updates"] = normalized_history
    memory.setdefault("ending_hook", "")
    memory["ending_hook"] = _remove_visible_protocol_labels(memory.get("ending_hook"))
    ending_hook = str(memory.get("ending_hook") or "").strip()
    handoff = memory.get("handoff")
    if not isinstance(handoff, dict):
        handoff = {}
    handoff.setdefault("current_scene", "")
    handoff.setdefault("current_time", "")
    handoff.setdefault("current_characters", [])
    handoff.setdefault("current_conflict", "")
    handoff.setdefault("unresolved_questions", [])
    handoff.setdefault("next_opening_must_continue", "")
    handoff.setdefault("forbidden_jump", "")
    handoff.setdefault("last_external_action", "")
    handoff.setdefault("last_spoken_line", "")
    handoff.setdefault("active_object", "")
    handoff.setdefault("open_conflict", handoff.get("current_conflict", ""))
    handoff.setdefault("next_first_paragraph_task", handoff.get("next_opening_must_continue", ""))
    handoff.setdefault("forbidden_opening", handoff.get("forbidden_jump", ""))
    handoff.setdefault("ending_style", "")
    handoff.setdefault("next_continuity_debt", handoff.get("next_first_paragraph_task", ""))
    handoff.setdefault("suggested_opening_modes", [])
    handoff.setdefault("forbidden_next_opening", handoff.get("forbidden_opening", ""))
    for key in [
        "next_opening_must_continue",
        "last_external_action",
        "active_object",
        "open_conflict",
        "next_first_paragraph_task",
        "ending_style",
        "last_visible_anchor",
        "next_opening_action",
        "ending_anchor_type",
        "next_continuity_debt",
    ]:
        if key in handoff:
            handoff[key] = _remove_visible_protocol_labels(handoff.get(key))
    if ending_hook and not str(handoff.get("next_opening_must_continue") or "").strip():
        handoff["next_opening_must_continue"] = f"承接本章结尾钩子：{ending_hook}"
    if not str(handoff.get("next_first_paragraph_task") or "").strip():
        handoff["next_first_paragraph_task"] = handoff.get("next_opening_must_continue", "")
    if not str(handoff.get("forbidden_opening") or "").strip():
        handoff["forbidden_opening"] = handoff.get("forbidden_jump") or "禁止跳过上一章结尾，禁止先写天气、时间跳转、回忆或背景说明。"
    if not str(handoff.get("forbidden_next_opening") or "").strip():
        handoff["forbidden_next_opening"] = handoff.get("forbidden_opening", "")
    if not str(handoff.get("open_conflict") or "").strip():
        handoff["open_conflict"] = handoff.get("current_conflict", "")
    if not str(handoff.get("last_visible_anchor") or "").strip():
        handoff["last_visible_anchor"] = (
            handoff.get("last_external_action")
            or handoff.get("active_object")
            or handoff.get("last_spoken_line")
            or handoff.get("open_conflict")
            or ""
        )
    if not str(handoff.get("next_opening_action") or "").strip():
        handoff["next_opening_action"] = handoff.get("next_first_paragraph_task") or handoff.get("next_opening_must_continue", "")
    if not str(handoff.get("next_continuity_debt") or "").strip():
        handoff["next_continuity_debt"] = handoff.get("next_opening_action") or handoff.get("next_opening_must_continue", "")
    if not str(handoff.get("ending_anchor_type") or "").strip():
        handoff["ending_anchor_type"] = handoff.get("ending_style", "")
    if not isinstance(handoff.get("suggested_opening_modes"), list):
        handoff["suggested_opening_modes"] = []
    memory["handoff"] = handoff
    return memory


def validate_contract(data: Any, validator: Validator) -> list[str]:
    return validator(data)


def assert_contract(data: Any, validator: Validator) -> None:
    issues = validator(data)
    if issues:
        raise ContractError("AI 输出未通过契约校验：" + "；".join(issues))


def _object_or_empty(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        return deepcopy(data)
    return {}


_VISIBLE_PROTOCOL_LABEL_RE = re.compile(r"^【(?P<label>目的词|回报类型|章首钩子|章尾钩子)：(?P<value>[^】]+)】")
_VISIBLE_STRENGTH_LABEL_RE = re.compile(r"^【强度：[^】]+】")
_INTERNAL_PROTOCOL_LABELS = {
    "allowed_shift": "允许转视角或跨阶段",
    "chapter_bridge_pack": "上一章承接包",
    "chapter_execution_card": "章节执行卡",
    "chapter_task_sheet": "章节任务单",
    "chapter_transition_contract": "章节交接规则",
    "chapter_word_target": "单章字数要求",
    "ending_variation_policy": "章尾避重规则",
    "first_screen_task": "第一屏任务",
    "genre_contract": "题材契约卡",
    "last_visible_beat": "上一章最后画面",
    "minimal_memory_pack": "最小记忆包",
    "must_use_concrete_anchor": "必须承接的具体锚点",
    "opening_variation_policy": "章首避重规则",
    "recent_style_signatures": "近期章首章尾避重记录",
    "required_next_beat": "下一拍任务",
    "previous_tail_excerpt": "上一章末段原文",
    "shift_reason": "转场原因",
    "style_guard": "避重规则",
    "unresolved_pressure": "未解决压力",
}
_INTERNAL_PROTOCOL_TOKEN_RE = re.compile(r"(?<![a-z0-9_])(?P<token>[a-z][a-z0-9_]*_[a-z0-9_]+)(?![a-z0-9_])")


def localize_visible_protocol_terms(value: Any) -> Any:
    if isinstance(value, str):
        return _INTERNAL_PROTOCOL_TOKEN_RE.sub(
            lambda match: _INTERNAL_PROTOCOL_LABELS.get(match.group("token"), "内部规则"),
            value,
        )
    if isinstance(value, list):
        return [localize_visible_protocol_terms(item) for item in value]
    if isinstance(value, dict):
        return {key: localize_visible_protocol_terms(item) for key, item in value.items()}
    return value


def _remove_visible_protocol_labels(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    label_value = ""
    while text:
        match = _VISIBLE_PROTOCOL_LABEL_RE.match(text)
        if match:
            label_value = match.group("value").strip()
            text = text[match.end() :].strip()
            continue
        strength = _VISIBLE_STRENGTH_LABEL_RE.match(text)
        if strength:
            text = text[strength.end() :].strip()
            continue
        break
    if not label_value:
        return text
    text = text.lstrip("：:，,；;。 ")
    return f"{label_value}：{text}" if text else label_value


def _normalize_plan_characters(plan: dict[str, Any]) -> None:
    protagonist = plan.get("protagonist")
    protagonist_key = _character_identity_key(protagonist) if isinstance(protagonist, dict) else ""
    seen = {protagonist_key} if protagonist_key else set()
    supporting: list[dict[str, Any]] = []
    villains: list[dict[str, Any]] = []
    for source_key, target in [("supporting_characters", supporting), ("villains", villains)]:
        for item in plan.get(source_key, []):
            if not isinstance(item, dict):
                continue
            cleaned = dict(item)
            cleaned["name"] = normalize_character_name(cleaned.get("name"))
            key = _character_identity_key(cleaned)
            if not key or key in seen:
                continue
            seen.add(key)
            if _role_contains(cleaned, "反派"):
                villains.append(cleaned)
            elif _role_contains(cleaned, "主角") and protagonist_key:
                continue
            else:
                target.append(cleaned)
    if isinstance(protagonist, dict):
        protagonist["name"] = normalize_character_name(protagonist.get("name"))
    plan["supporting_characters"] = supporting
    plan["villains"] = villains


def _character_identity_key(character: dict[str, Any]) -> str:
    return character_identity_key(character.get("name"))


def _role_contains(character: dict[str, Any], keyword: str) -> bool:
    role = str(character.get("role") or "")
    name = str(character.get("name") or "")
    return keyword in role or keyword in name


PLANNER_WORK_PLAN_VALIDATOR = validate_work_plan
PLANNER_OUTLINE_VALIDATOR = validate_outline
PLANNER_CHAPTER_OUTLINES_VALIDATOR = validate_chapter_outlines
REVIEW_VALIDATOR = validate_review
MEMORY_CARD_VALIDATOR = validate_memory_card
