from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Callable

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
    memory.setdefault("ending_hook", "")
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
            cleaned["name"] = _clean_character_name(cleaned.get("name"))
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
        protagonist["name"] = _clean_character_name(protagonist.get("name"))
    plan["supporting_characters"] = supporting
    plan["villains"] = villains


def _clean_character_name(value: Any) -> str:
    name = str(value or "").strip()
    name = re.sub(r"[（(].*?[）)]", "", name)
    name = re.sub(r"^(主角|配角|反派)[:：\s]*", "", name)
    return re.sub(r"\s+", "", name)


def _character_identity_key(character: dict[str, Any]) -> str:
    return _clean_character_name(character.get("name")).lower()


def _role_contains(character: dict[str, Any], keyword: str) -> bool:
    role = str(character.get("role") or "")
    name = str(character.get("name") or "")
    return keyword in role or keyword in name


PLANNER_WORK_PLAN_VALIDATOR = validate_work_plan
PLANNER_OUTLINE_VALIDATOR = validate_outline
PLANNER_CHAPTER_OUTLINES_VALIDATOR = validate_chapter_outlines
REVIEW_VALIDATOR = validate_review
MEMORY_CARD_VALIDATOR = validate_memory_card
