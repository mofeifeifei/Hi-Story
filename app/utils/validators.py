from __future__ import annotations

from typing import Any


def _is_text(value: Any, min_len: int = 1) -> bool:
    return isinstance(value, str) and len(value.strip()) >= min_len


def _is_list(value: Any, min_len: int = 0) -> bool:
    return isinstance(value, list) and len(value) >= min_len


def _positive_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def validate_work_plan(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["作品方案必须是 JSON 对象"]
    issues: list[str] = []
    if not isinstance(data.get("book_bible"), dict):
        issues.append("缺少 book_bible")
    if not isinstance(data.get("book_contract"), dict):
        issues.append("missing book_contract")
    if not _is_list(data.get("title_candidates"), 1):
        issues.append("缺少 title_candidates")
    if not _is_text(data.get("summary"), 20):
        issues.append("summary 过短")
    if not _is_list(data.get("core_selling_points"), 1):
        issues.append("缺少 core_selling_points")
    protagonist = data.get("protagonist")
    if not isinstance(protagonist, dict) or not _is_text(protagonist.get("name")):
        issues.append("缺少主角姓名")
    if not _is_list(data.get("world_rules"), 1):
        issues.append("缺少 world_rules")
    return issues


def validate_outline(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["大纲必须是 JSON 对象"]
    issues: list[str] = []
    if not _is_text(data.get("full_outline"), 40):
        issues.append("full_outline 过短")
    volumes = data.get("volume_outline")
    if not _is_list(volumes, 1):
        issues.append("缺少 volume_outline")
        return issues
    for index, volume in enumerate(volumes, 1):
        if not isinstance(volume, dict):
            issues.append(f"第 {index} 卷不是对象")
            continue
        for key in [
            "volume_number",
            "title",
            "goal",
            "main_conflict",
            "ending",
            "target_chapters",
            "min_chapters",
            "soft_max_chapters",
            "hard_max_chapters",
            "entry_condition",
            "exit_condition",
        ]:
            if volume.get(key) in (None, ""):
                issues.append(f"第 {index} 卷缺少 {key}")
        if not _is_list(volume.get("turning_points"), 4):
            issues.append(f"第 {index} 卷 turning_points 少于 4 条")
        if not _is_list(volume.get("required_milestones"), 3):
            issues.append(f"第 {index} 卷 required_milestones 少于 3 条")
        target = _positive_int(volume.get("target_chapters"))
        minimum = _positive_int(volume.get("min_chapters"))
        soft_max = _positive_int(volume.get("soft_max_chapters"))
        hard_max = _positive_int(volume.get("hard_max_chapters"))
        if not all([target, minimum, soft_max, hard_max]):
            issues.append(f"第 {index} 卷章节边界必须是正整数")
        elif not minimum <= target <= soft_max <= hard_max:
            issues.append(f"第 {index} 卷章节边界必须满足 min_chapters <= target_chapters <= soft_max_chapters <= hard_max_chapters")
    return issues


def validate_chapter_outlines(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["章节细纲必须是 JSON 对象"]
    chapters = data.get("chapters")
    if not _is_list(chapters, 1):
        return ["缺少 chapters"]
    issues: list[str] = []
    for index, chapter in enumerate(chapters, 1):
        if not isinstance(chapter, dict):
            issues.append(f"第 {index} 个章节不是对象")
            continue
        if chapter.get("chapter_number") in (None, ""):
            issues.append(f"第 {index} 章缺少 chapter_number")
        if chapter.get("volume_number") in (None, ""):
            issues.append(f"第 {index} 章缺少 volume_number")
        if not _is_text(chapter.get("title")):
            issues.append(f"第 {index} 章缺少 title")
        if not _is_text(chapter.get("outline"), 30):
            issues.append(f"第 {index} 章 outline 过短")
        for key in [
            "story_time",
            "opening_hook",
            "continuity_debt",
            "debt_type",
            "opening_mode",
            "opening_trigger",
            "reader_question_in",
            "reader_answer_out",
            "new_question_out",
            "next_continuity_debt",
            "reader_expectation",
            "conflict",
            "new_information",
            "chapter_payoff",
            "handoff",
        ]:
            if not _is_text(chapter.get(key)):
                issues.append(f"第 {index} 章缺少 {key}")
        scene_cards = chapter.get("scene_cards")
        if not isinstance(scene_cards, list):
            issues.append(f"第 {index} 章 scene_cards 必须是数组")
        elif len(scene_cards) < 3:
            issues.append(f"第 {index} 章 scene_cards 少于 3 个")
        for key in ["ending_hook"]:
            if not _is_text(chapter.get(key)):
                issues.append(f"第 {index} 章缺少 {key}")
    return issues


def validate_review(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["审稿结果必须是 JSON 对象"]
    issues: list[str] = []
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
        try:
            score = int(data.get(key))
        except (TypeError, ValueError):
            issues.append(f"{key} 不是 0-100 分数")
            continue
        if score < 0 or score > 100:
            issues.append(f"{key} 超出 0-100")
    for key in ["repeat_risk", "problems", "suggestions", "template_hits", "risk_flags"]:
        if not isinstance(data.get(key), list):
            issues.append(f"{key} 必须是数组")
    return issues


def validate_memory_card(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["记忆卡必须是 JSON 对象"]
    issues: list[str] = []
    if not _is_text(data.get("summary"), 40):
        issues.append("summary 过短")
    for key in [
        "character_changes",
        "new_foreshadows",
        "resolved_foreshadows",
        "timeline_events",
        "ability_changes",
        "relationship_changes",
        "character_state_updates",
        "historical_updates",
    ]:
        if not isinstance(data.get(key), list):
            issues.append(f"{key} 必须是数组")
    handoff = data.get("handoff")
    if not isinstance(handoff, dict):
        issues.append("缺少 handoff")
        return issues
    for key in ["current_scene", "current_time", "current_characters", "current_conflict", "unresolved_questions", "next_opening_must_continue", "forbidden_jump"]:
        if key not in handoff:
            issues.append(f"handoff 缺少 {key}")
    if not isinstance(handoff.get("current_characters"), list):
        issues.append("handoff.current_characters 必须是数组")
    if not isinstance(handoff.get("unresolved_questions"), list):
        issues.append("handoff.unresolved_questions 必须是数组")
    if not _is_text(handoff.get("next_opening_must_continue")):
        issues.append("handoff.next_opening_must_continue 不能为空")
    if not _is_text(handoff.get("forbidden_jump")):
        issues.append("handoff.forbidden_jump 不能为空")
    for key in ["last_external_action", "open_conflict", "next_first_paragraph_task", "forbidden_opening", "next_continuity_debt", "forbidden_next_opening"]:
        if not _is_text(handoff.get(key)):
            issues.append(f"handoff.{key} 不能为空")
    if not isinstance(handoff.get("suggested_opening_modes"), list):
        issues.append("handoff.suggested_opening_modes 必须是数组")
    return issues
