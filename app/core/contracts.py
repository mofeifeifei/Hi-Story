from __future__ import annotations

from copy import deepcopy
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
    result = _object_or_empty(data)
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
        item.setdefault("story_time", "")
        item.setdefault("opening_hook", "")
        item.setdefault("continuity_debt", "")
        item.setdefault("debt_type", "")
        item.setdefault("opening_mode", "")
        item.setdefault("opening_subject", "")
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
        item.setdefault("handoff", "")
        item.setdefault("forbidden", "")
        normalized_chapters.append(item)
    result["chapters"] = normalized_chapters
    return result


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
    review.setdefault("problems", [])
    review.setdefault("suggestions", [])
    review.setdefault("template_hits", template_hits or [])
    review.setdefault("risk_flags", [])
    return review


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
