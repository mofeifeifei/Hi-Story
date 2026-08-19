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


def validate_planning_core(core: Any, *, label: str = "章节") -> list[str]:
    if not isinstance(core, dict):
        return [f"{label}缺少 planning_core"]
    issues: list[str] = []
    chapter = core.get("chapter") if isinstance(core.get("chapter"), dict) else {}
    bridge = core.get("bridge") if isinstance(core.get("bridge"), dict) else {}
    result = core.get("result") if isinstance(core.get("result"), dict) else {}
    questions = core.get("questions") if isinstance(core.get("questions"), dict) else {}
    handoff = core.get("handoff") if isinstance(core.get("handoff"), dict) else {}

    for key in ["chapter_number", "volume_number", "title", "sequence_id", "sequence_goal"]:
        if chapter.get(key) in (None, ""):
            issues.append(f"{label}核心契约缺少 chapter.{key}")
    for key in ["opening_action", "opening_conflict", "continuity_debt"]:
        if not _is_text(bridge.get(key)):
            issues.append(f"{label}核心契约缺少 bridge.{key}")
    try:
        chapter_number = int(chapter.get("chapter_number") or 1)
    except (TypeError, ValueError):
        chapter_number = 1
    if chapter_number > 1 and not _is_text(bridge.get("previous_anchor")):
        issues.append(f"{label}核心契约缺少 bridge.previous_anchor")

    scenes = core.get("scenes")
    if not _is_list(scenes, 3):
        issues.append(f"{label}核心契约 scenes 少于 3 个")
    else:
        for index, scene in enumerate(scenes, 1):
            if not isinstance(scene, dict):
                issues.append(f"{label}核心契约第 {index} 个场景不是对象")
                continue
            for key in ["location", "goal", "obstacle", "turn", "exit"]:
                if not _is_text(scene.get(key)):
                    issues.append(f"{label}核心契约第 {index} 个场景缺少 {key}")

    for key in ["in", "answer", "out"]:
        if not _is_text(questions.get(key)):
            issues.append(f"{label}核心契约缺少 questions.{key}")
    for key in ["new_information", "chapter_payoff", "character_change"]:
        if not _is_text(result.get(key)):
            issues.append(f"{label}核心契约缺少 result.{key}")
    for key in ["ending_event", "next_opening_action", "next_continuity_debt"]:
        if not _is_text(handoff.get(key)):
            issues.append(f"{label}核心契约缺少 handoff.{key}")
    return issues


def validate_chapter_outlines(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["章节细纲必须是 JSON 对象"]
    chapters = data.get("chapters")
    if not _is_list(chapters, 1):
        return ["缺少 chapters"]
    issues: list[str] = []
    decision = data.get("volume_decision")
    if decision is not None and not isinstance(decision, dict):
        issues.append("volume_decision 必须是对象")
    for index, chapter in enumerate(chapters, 1):
        if not isinstance(chapter, dict):
            issues.append(f"返回第 {index} 项不是章节对象")
            continue
        label = _chapter_issue_label(index, chapter)
        if "planning_core" in chapter:
            issues.extend(validate_planning_core(chapter.get("planning_core"), label=label))
        if chapter.get("chapter_number") in (None, ""):
            issues.append(f"{label}缺少 chapter_number")
        if chapter.get("volume_number") in (None, ""):
            issues.append(f"{label}缺少 volume_number")
        if not _is_text(chapter.get("title")):
            issues.append(f"{label}缺少 title")
        if not _is_text(chapter.get("outline"), 30):
            issues.append(f"{label}outline 过短")
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
                issues.append(f"{label}缺少 {key}")
        scene_cards = chapter.get("scene_cards")
        if not isinstance(scene_cards, list):
            issues.append(f"{label}scene_cards 必须是数组")
        elif len(scene_cards) < 3:
            issues.append(f"{label}scene_cards 少于 3 个")
        for key in ["ending_hook"]:
            if not _is_text(chapter.get(key)):
                issues.append(f"{label}缺少 {key}")
    return issues


def _chapter_issue_label(index: int, chapter: dict[str, Any]) -> str:
    chapter_number = chapter.get("chapter_number")
    if chapter_number not in (None, ""):
        return f"返回第 {index} 项（目标第 {chapter_number} 章）"
    return f"返回第 {index} 项"


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
    for key in ["repeat_risk", "scene_coverage", "problems", "suggestions", "template_hits", "risk_flags"]:
        if not isinstance(data.get(key), list):
            issues.append(f"{key} 必须是数组")
    for index, item in enumerate(data.get("scene_coverage") or [], 1):
        if not isinstance(item, dict):
            issues.append(f"scene_coverage 第 {index} 项必须是对象")
            continue
        if str(item.get("status") or "").strip().lower() not in {"complete", "partial", "missing"}:
            issues.append(f"scene_coverage 第 {index} 项 status 无效")
        if not str(item.get("evidence") or item.get("missing") or "").strip():
            issues.append(f"scene_coverage 第 {index} 项缺少 evidence 或 missing")
    for index, item in enumerate(data.get("problems") or [], 1):
        if not isinstance(item, dict):
            issues.append(f"problems 第 {index} 项必须是对象")
            continue
        for key in ["type", "severity", "evidence", "why_it_matters"]:
            if not str(item.get(key) or "").strip():
                issues.append(f"problems 第 {index} 项缺少 {key}")
    for index, item in enumerate(data.get("suggestions") or [], 1):
        if not isinstance(item, dict):
            issues.append(f"suggestions 第 {index} 项必须是对象")
            continue
        for key in ["target", "action"]:
            if not str(item.get(key) or "").strip():
                issues.append(f"suggestions 第 {index} 项缺少 {key}")
    _validate_title_decision(data.get("title_decision"), issues, "title_decision")
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
    result_card = data.get("chapter_result_card")
    if not isinstance(result_card, dict):
        issues.append("缺少 chapter_result_card")
    else:
        _validate_title_decision(
            result_card.get("title_decision"),
            issues,
            "chapter_result_card.title_decision",
        )
    return issues


def _validate_title_decision(value: Any, issues: list[str], label: str) -> None:
    # Title selection is advisory. A model that omits it must not block an
    # otherwise usable review or memory card; populated decisions remain strict.
    if value is None or value == "":
        return
    if isinstance(value, dict) and not any(
        str(value.get(key) or "").strip() for key in ["chapter_summary", "recommended_title", "reason"]
    ) and not value.get("candidates"):
        return
    if not isinstance(value, dict):
        issues.append(f"{label} 必须是对象")
        return
    if not _is_text(value.get("chapter_summary"), 12):
        issues.append(f"{label}.chapter_summary 过短")
    recommended = str(value.get("recommended_title") or "").strip()
    if not recommended:
        issues.append(f"{label}.recommended_title 不能为空")
    if not _is_text(value.get("reason"), 8):
        issues.append(f"{label}.reason 过短")
    candidates = value.get("candidates")
    if not _is_list(candidates, 4):
        issues.append(f"{label}.candidates 少于 4 个")
    elif recommended and recommended not in candidates:
        issues.append(f"{label}.recommended_title 必须来自 candidates")
