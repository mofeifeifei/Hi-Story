from __future__ import annotations

import re
from typing import Any

from app.utils.history import HISTORICAL_PROFILE_FIELDS, format_historical_profile
from app.utils.json_parser import as_list, parse_json_object
from app.utils.outline_utils import CHAPTER_OUTLINE_FIELDS, normalize_chapter_outline, scene_cards_to_text


def _text(value: Any, default: str = "未填写") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() or default
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        items = [_text(item, "") for item in value]
        return "、".join(item for item in items if item) or default
    if isinstance(value, dict):
        parts = [f"{key}: {_text(val, '')}" for key, val in value.items() if _text(val, "")]
        return "；".join(parts) or default
    return str(value).strip() or default


def _maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped.startswith(("{", "[")):
        return value
    return parse_json_object(stripped, default=value)


def _trim_join_punctuation(value: str) -> str:
    return re.sub(r"[。；;，,、]+$", "", value.strip())


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _section(lines: list[str], title: str) -> None:
    if lines:
        lines.append("")
    lines.append(f"【{title}】")


def _paragraph_text(value: Any) -> str:
    text = _text(value)
    if text == "未填写":
        return text
    if "\n" in text:
        return "\n\n".join(part.strip() for part in text.splitlines() if part.strip())
    text = re.sub(r"(第[一二三四五六七八九十]+阶段)", r"\n\n\1", text)
    text = re.sub(r"(第一卷|第二卷|第三卷|第四卷|第五卷|第六卷|第七卷|第八卷|第九卷|第十卷)", r"\n\n\1", text)
    sentences = re.split(r"(?<=[。！？])", text)
    paragraphs: list[str] = []
    buffer = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(buffer) + len(sentence) > 180 and buffer:
            paragraphs.append(buffer)
            buffer = sentence
        else:
            buffer = buffer + sentence
    if buffer:
        paragraphs.append(buffer)
    return "\n\n".join(part.strip() for part in paragraphs if part.strip())


def _add_list(lines: list[str], values: Any, *, empty: str = "暂无") -> None:
    items = [item for item in as_list(_maybe_json(values)) if _text(item, "")]
    if not items:
        lines.append(empty)
        return
    for index, item in enumerate(items, 1):
        if isinstance(item, dict):
            lines.append(f"{index}. {_text(item)}")
        else:
            lines.append(f"{index}. {_text(item)}")


REVIEW_SEVERITY_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
    "critical": "严重",
}

REVIEW_TYPE_LABELS = {
    "continuity": "承接连贯",
    "transition": "章节交接",
    "character": "人设",
    "world_rule": "世界观规则",
    "history": "历史准确性",
    "foreshadow": "伏笔",
    "timeline": "时间线",
    "scene_card": "场景卡",
    "user_note": "用户批注",
    "expectation": "读者期待",
    "payoff": "回报兑现",
    "emotion": "情绪",
    "rhythm": "节奏",
    "hook": "结尾牵引",
    "length": "字数控制",
    "ending_style": "章末风格",
    "opening": "开篇",
    "mobile_readability": "移动端阅读",
    "first_three_chapters": "黄金三章",
    "repeat": "重复",
    "template": "模板化",
    "risk": "风险",
    "isolated_chapter": "孤岛章",
    "handoff": "接力棒",
    "ending": "结尾",
}


def _label_from_map(value: Any, labels: dict[str, str], default: str = "未填写") -> str:
    text = _text(value, default)
    if text == default:
        return text
    parts = re.split(r"\s*[/,，、]\s*", text)
    mapped = [labels.get(part.strip().lower(), part.strip()) for part in parts if part.strip()]
    return " / ".join(mapped) if mapped else labels.get(text.lower(), text)


MEMORY_FIELD_LABELS = {
    "summary": "本章摘要",
    "character_changes": "人物变化",
    "character_state_updates": "人物状态更新",
    "new_foreshadows": "新增伏笔",
    "resolved_foreshadows": "回收伏笔",
    "timeline_events": "时间线事件",
    "ability_changes": "能力变化",
    "relationship_changes": "关系变化",
    "historical_updates": "历史设定更新",
    "ending_hook": "结尾钩子",
    "handoff": "下一章接力棒",
    "name": "人物",
    "character": "人物",
    "change": "变化",
    "content": "内容",
    "description": "描述",
    "current_goal": "当前目标",
    "current_fear": "当前恐惧",
    "current_state": "当前状态",
    "current_scene": "当前场景",
    "current_time": "当前时间",
    "current_characters": "当前人物",
    "current_conflict": "当前冲突",
    "unresolved_questions": "未解决问题",
    "next_opening_must_continue": "下一章必须承接",
    "forbidden_jump": "禁止跳过",
    "last_external_action": "末尾外部动作",
    "last_spoken_line": "末尾关键对白",
    "active_object": "承接物件/证据",
    "open_conflict": "未闭合冲突",
    "next_first_paragraph_task": "下一章第一段任务",
    "forbidden_opening": "禁用开头",
    "ending_style": "结尾类型",
    "relationship_stage": "关系阶段",
    "secret_exposure": "秘密暴露",
    "arc_stage": "成长阶段",
    "arc_notes": "成长备注",
    "chapter": "章节",
    "chapter_number": "章节",
    "planned_resolve_chapter": "计划回收章节",
    "actual_resolve_chapter": "实际回收章节",
    "story_time": "故事时间",
    "event": "事件",
    "category": "类别",
    "chapter_impact": "本章影响",
    "future_constraint": "后续约束",
    "characters_involved": "涉及人物",
    "ability": "能力",
    "from": "变化前",
    "to": "变化后",
    "before": "变化前",
    "after": "变化后",
    "old_value": "原值",
    "new_value": "新值",
    "reason": "原因",
    "relationship": "关系",
    "status": "状态",
    "state": "状态",
    "type": "类型",
    "source": "来源",
    "target": "对象",
    "impact": "影响",
    "time": "时间",
    "place": "地点",
    "location": "地点",
    "scene": "场景",
    "question": "问题",
    "answer": "答案",
    "note": "备注",
    "notes": "备注",
}


MEMORY_VALUE_LABELS = {
    "open": "未结束",
    "active": "进行中",
    "pending": "待处理",
    "resolved": "已回收",
    "closed": "已关闭",
    "unknown": "未知",
    "none": "无",
}


def _labeled_key(key: Any, labels: dict[str, str]) -> str:
    text = str(key)
    return labels.get(text, labels.get(text.lower(), text))


def _labeled_value_text(value: Any, labels: dict[str, str]) -> str:
    value = _maybe_json(value)
    if isinstance(value, dict):
        return _format_labeled_dict(value, labels)
    if isinstance(value, list):
        parts = [_trim_join_punctuation(_labeled_value_text(item, labels)) for item in value]
        return "、".join(part for part in parts if part and part != "未填写")
    text = _text(value, "")
    if not text:
        return ""
    return MEMORY_VALUE_LABELS.get(text.lower(), text)


def _format_labeled_dict(item: dict[str, Any], labels: dict[str, str]) -> str:
    parts: list[str] = []
    for key, value in item.items():
        text = _labeled_value_text(value, labels)
        if not text:
            continue
        text = _trim_join_punctuation(text)
        parts.append(f"{_labeled_key(key, labels)}：{text}")
    return "；".join(parts) or "未填写"


def _add_memory_list(lines: list[str], values: Any, *, empty: str = "暂无") -> None:
    items = [item for item in as_list(_maybe_json(values)) if _labeled_value_text(item, MEMORY_FIELD_LABELS)]
    if not items:
        lines.append(empty)
        return
    for index, item in enumerate(items, 1):
        if isinstance(item, dict):
            lines.append(f"{index}. {_format_labeled_dict(item, MEMORY_FIELD_LABELS)}")
        else:
            lines.append(f"{index}. {_labeled_value_text(item, MEMORY_FIELD_LABELS)}")


def _format_character(character: dict[str, Any]) -> list[str]:
    fields = [
        ("姓名", "name"),
        ("定位", "role"),
        ("旧名/别名", "aliases"),
        ("性格/行为", "personality"),
        ("目标", "goal"),
        ("秘密", "secret"),
        ("说话方式", "speaking_style"),
        ("关系", "relationship"),
        ("锁定规则", "locked_rules"),
        ("当前目标", "current_goal"),
        ("当前恐惧", "current_fear"),
        ("当前状态", "current_state"),
        ("关系阶段", "relationship_stage"),
        ("秘密暴露", "secret_exposure"),
        ("成长阶段", "arc_stage"),
        ("成长备注", "arc_notes"),
        ("变更章节", "last_changed_chapter"),
    ]
    return [f"{label}：{_text(character.get(key))}" for label, key in fields]


def _format_rule(rule: dict[str, Any]) -> str:
    return (
        f"{_text(rule.get('rule_name'))}\n"
        f"规则：{_text(rule.get('rule_content'))}\n"
        f"限制：{_text(rule.get('limitations'))}\n"
        f"禁止改动：{_text(rule.get('forbidden_changes'))}"
    )


def _format_book_bible(bible: dict[str, Any]) -> list[str]:
    fields = [
        ("核心阅读承诺", "core_reading_promise"),
        ("主类型", "primary_genre"),
        ("副类型", "secondary_genres"),
        ("情绪底色", "emotional_tone"),
        ("叙事驱动力", "narrative_driver"),
        ("主角终局目标", "protagonist_end_goal"),
        ("长篇发动机", "long_form_engine"),
        ("必须保留", "must_keep_rules"),
        ("禁止跑偏", "forbidden_drift"),
        ("结局方向", "ending_direction"),
    ]
    return [f"{label}：{_text(bible.get(key))}" for label, key in fields]


def _has_historical_profile(profile: Any) -> bool:
    return isinstance(profile, dict) and any(str(profile.get(key) or "").strip() for key in HISTORICAL_PROFILE_FIELDS)


def _format_volume(item: dict[str, Any], index: int) -> list[str]:
    number = item.get("volume_number") or item.get("number") or index
    title = item.get("title") or item.get("volume") or f"第{number}卷"
    lines = [f"{index}. 第{number}卷：{_text(title)}"]
    field_labels = [
        ("卷目标", "goal"),
        ("主要冲突", "main_conflict"),
        ("关键转折", "turning_points"),
        ("结尾状态", "ending"),
        ("分卷内容", "outline"),
    ]
    for label, key in field_labels:
        value = item.get(key)
        if value:
            lines.append(f"   {label}：{_text(value)}")
    return lines


def format_project_readable(data: dict[str, Any] | None) -> str:
    if not data:
        return "暂无设定内容。"
    if "work" in data:
        return format_work_bundle_readable(data)
    return format_plan_readable(data)


def format_plan_readable(plan: dict[str, Any]) -> str:
    lines: list[str] = []
    _section(lines, "书名候选")
    _add_list(lines, plan.get("title_candidates"))

    _section(lines, "作品简介")
    lines.append(_text(plan.get("summary")))

    _section(lines, "核心卖点")
    _add_list(lines, plan.get("core_selling_points"))

    _section(lines, "目标读者")
    lines.append(_text(plan.get("target_readers")))

    protagonist = plan.get("protagonist")
    if isinstance(protagonist, dict):
        _section(lines, "主角")
        lines.extend(_format_character(protagonist))

    supporting = [item for item in as_list(plan.get("supporting_characters")) if isinstance(item, dict)]
    if supporting:
        _section(lines, "配角")
        for index, character in enumerate(supporting, 1):
            lines.append(f"{index}. {_text(character.get('name'))}（{_text(character.get('role'))}）")
            lines.extend(f"   {line}" for line in _format_character(character)[2:])

    villains = [item for item in as_list(plan.get("villains")) if isinstance(item, dict)]
    if villains:
        _section(lines, "反派")
        for index, character in enumerate(villains, 1):
            lines.append(f"{index}. {_text(character.get('name'))}（{_text(character.get('role'), '反派')}）")
            lines.extend(f"   {line}" for line in _format_character(character)[2:])

    rules = [item for item in as_list(plan.get("world_rules")) if isinstance(item, dict)]
    if rules:
        _section(lines, "世界观与能力规则")
        for index, rule in enumerate(rules, 1):
            lines.append(f"{index}. {_format_rule(rule)}")

    historical_profile = plan.get("historical_profile")
    if _has_historical_profile(historical_profile):
        _section(lines, "历史设定卡")
        lines.append(format_historical_profile(historical_profile))

    _section(lines, "主线目标")
    lines.append(_text(plan.get("main_goal")))

    _section(lines, "第一卷方向")
    lines.append(_text(plan.get("first_volume_direction")))

    warnings = plan.get("warnings") or []
    if warnings:
        _section(lines, "需要注意")
        _add_list(lines, warnings)

    bible = plan.get("book_bible")
    if isinstance(bible, dict) and bible:
        _section(lines, "作品圣经")
        lines.extend(_format_book_bible(bible))
    return "\n".join(lines).strip()


def format_work_bundle_readable(bundle: dict[str, Any]) -> str:
    work = bundle.get("work") or {}
    lines: list[str] = []
    _section(lines, "当前文章")
    lines.append(f"名称：{_text(work.get('title'))}")
    lines.append(f"创意：{_text(work.get('idea'))}")
    lines.append(f"题材：{_text(work.get('genre'))}")
    lines.append(f"平台：{_text(work.get('platform'))}")
    lines.append(f"目标字数：{_text(work.get('target_words'))}")
    lines.append(f"简介：{_text(work.get('summary'))}")

    selling_points = _maybe_json(work.get("core_selling_points") or [])
    if selling_points:
        _section(lines, "核心卖点")
        _add_list(lines, selling_points)

    bible = _maybe_json(work.get("book_bible_json") or {})
    if isinstance(bible, dict) and bible:
        _section(lines, "作品圣经")
        lines.extend(_format_book_bible(bible))

    characters = [item for item in as_list(bundle.get("characters")) if isinstance(item, dict)]
    _section(lines, "人物资料")
    if characters:
        for index, character in enumerate(characters, 1):
            lines.append(f"{index}. {_text(character.get('name'))}（{_text(character.get('role'))}）")
            lines.extend(f"   {line}" for line in _format_character(character)[2:])
    else:
        lines.append("暂无人物资料。")

    rules = [item for item in as_list(bundle.get("world_rules")) if isinstance(item, dict)]
    _section(lines, "世界观规则")
    if rules:
        for index, rule in enumerate(rules, 1):
            lines.append(f"{index}. {_format_rule(rule)}")
    else:
        lines.append("暂无世界观规则。")

    historical_profile = bundle.get("historical_profile")
    if _has_historical_profile(historical_profile):
        _section(lines, "历史设定卡")
        lines.append(format_historical_profile(historical_profile))

    historical_facts = [item for item in as_list(bundle.get("historical_facts")) if isinstance(item, dict)]
    if historical_facts:
        _section(lines, "已落地历史事实")
        for item in historical_facts[-20:]:
            lines.append(
                f"- 第{_text(item.get('chapter_number'), '?')}章"
                f"【{_text(item.get('category'), '未分类')}】：{_text(item.get('content'))}"
                f"；后续约束：{_text(item.get('future_constraint'))}"
            )

    notes = [item for item in as_list(bundle.get("chapter_notes")) if isinstance(item, dict)]
    _section(lines, "章节批注")
    if notes:
        for item in notes:
            lines.append(
                f"- 第{_text(item.get('chapter_number'), '?')}章[{_text(item.get('note_type'))}]：{_text(item.get('content'))}"
            )
    else:
        lines.append("暂无章节批注。")

    threads = [item for item in as_list(bundle.get("open_plot_threads")) if isinstance(item, dict)]
    _section(lines, "未回收伏笔")
    if threads:
        for item in threads:
            lines.append(
                f"第{_text(item.get('first_chapter'), '?')}章：{_text(item.get('content'))}"
                f"（计划回收：{_text(item.get('planned_resolve_chapter'))}）"
            )
    else:
        lines.append("暂无未回收伏笔。")
    return "\n".join(lines).strip()


def format_outline_readable(data: Any) -> str:
    if not data:
        return "暂无大纲或细纲。"
    if isinstance(data, list):
        return format_chapter_outlines_readable(data)
    if not isinstance(data, dict):
        return _text(data, "暂无大纲或细纲。")

    if "chapters" in data and "full_outline" not in data and "volume_outline" not in data:
        return format_chapter_outlines_readable(data.get("chapters"))

    lines: list[str] = []
    _section(lines, "全书大纲")
    lines.append(_paragraph_text(data.get("full_outline")))

    volume_outline = _maybe_json(data.get("volume_outline") or [])
    _section(lines, "分卷大纲")
    items = as_list(volume_outline)
    if items:
        for index, item in enumerate(items, 1):
            if isinstance(item, dict):
                lines.extend(_format_volume(item, index))
            else:
                lines.append(f"{index}. {_text(item)}")
    else:
        lines.append("暂无分卷大纲。")

    chapters = [item for item in as_list(data.get("chapters")) if isinstance(item, dict)]
    if chapters:
        _section(lines, "章节细纲")
        lines.append(format_chapter_outlines_readable(chapters))
    return "\n".join(lines).strip()


def format_chapter_outlines_readable(chapters: Any) -> str:
    items = [item for item in as_list(chapters) if isinstance(item, dict)]
    if not items:
        return "暂无章节细纲。"
    lines: list[str] = []
    for chapter in items:
        detail = normalize_chapter_outline(chapter)
        number = _int_or_zero(detail.get("chapter_number"))
        title = _text(detail.get("title"), "未命名章节")
        _section(lines, f"第{number:03d}章 {title}" if number else title)
        fields = [
            ("本章细纲", "outline"),
            ("场景卡", "scene_cards"),
            *[(label, key) for key, label in CHAPTER_OUTLINE_FIELDS],
            ("结尾钩子", "ending_hook"),
        ]
        for label, key in fields:
            if detail.get(key):
                if key == "scene_cards":
                    cards = detail.get(key)
                    formatted_cards = scene_cards_to_text(cards)
                    if formatted_cards:
                        lines.append(f"{label}：")
                        lines.append(formatted_cards)
                else:
                    lines.append(f"{label}：{_text(detail.get(key))}")
    return "\n".join(lines).strip()


def format_context_readable(context: dict[str, Any] | None) -> str:
    if not context:
        return "暂无上下文。"
    lines: list[str] = []
    work = context.get("work") or {}
    chapter = context.get("chapter") or {}
    _section(lines, "当前任务")
    lines.append(f"文章：{_text(work.get('title'))}")
    lines.append(f"章节：第{_text(chapter.get('chapter_number'))}章 {_text(chapter.get('title'), '')}")
    lines.append(f"细纲：{_text(chapter.get('outline'))}")
    word_target = context.get("chapter_word_target")
    if isinstance(word_target, dict):
        lines.append(f"单章字数：{_text(word_target.get('label'))}")
        if word_target.get("min") and word_target.get("max"):
            lines.append(f"建议范围：{_text(word_target.get('min'))}-{_text(word_target.get('max'))} 字")
        lines.append(f"字数规则：{_text(word_target.get('note'))}")
    bible = context.get("book_bible")
    if isinstance(bible, dict) and bible:
        _section(lines, "作品圣经")
        lines.extend(_format_book_bible(bible))
    history_specialist = context.get("history_specialist")
    if isinstance(history_specialist, dict) and history_specialist.get("enabled"):
        _section(lines, "历史专项")
        lines.append(_text(history_specialist.get("compact_context")))
    outline_detail = normalize_chapter_outline(chapter)
    scene_cards = outline_detail.get("scene_cards")
    if scene_cards:
        lines.append("场景卡：")
        lines.append(scene_cards_to_text(scene_cards))
    for key, label in CHAPTER_OUTLINE_FIELDS:
        value = outline_detail.get(key, "")
        if value:
            lines.append(f"{label}：{_text(value)}")
    lines.append(f"结尾钩子要求：{_text(chapter.get('ending_hook'))}")

    previous = context.get("previous_chapter")
    _section(lines, "上一章承接")
    if isinstance(previous, dict):
        lines.append(f"上一章：第{_text(previous.get('chapter_number'))}章 {_text(previous.get('title'), '')}")
        lines.append(f"结尾钩子：{_text(previous.get('ending_hook'))}")
        lines.append(f"接力棒：{_text(previous.get('handoff'))}")
        lines.append(f"上一章末尾：{_text(previous.get('tail'))}")
    else:
        lines.append("暂无上一章。")

    transition = context.get("chapter_transition_contract")
    if isinstance(transition, dict) and transition:
        _section(lines, "章节交接口")
        lines.append(f"第一段任务：{_text(transition.get('required_first_paragraph'))}")
        lines.append(f"必须使用锚点：{_text(transition.get('must_use_concrete_anchor'))}")
        lines.append(f"禁用开头：{_text(transition.get('forbidden_opening'))}")

    _section(lines, "最近三章摘要")
    summaries = [item for item in as_list(context.get("recent_three_chapter_summaries")) if isinstance(item, dict)]
    if summaries:
        for item in summaries:
            lines.append(f"第{_text(item.get('chapter_number'))}章：{_text(item.get('summary'))}")
    else:
        lines.append("暂无摘要。")

    notes = [item for item in as_list(context.get("chapter_notes")) if isinstance(item, dict)]
    _section(lines, "当前章节批注")
    if notes:
        for item in notes:
            lines.append(f"- [{_text(item.get('note_type'))}] {_text(item.get('content'))}")
    else:
        lines.append("暂无批注。")

    repeats = as_list(context.get("repeat_risk_warnings"))
    _section(lines, "重复风险")
    if repeats:
        for item in repeats:
            lines.append(f"- {_text(item)}")
    else:
        lines.append("暂无明显重复风险。")

    _section(lines, "相关人物")
    characters = [item for item in as_list(context.get("characters")) if isinstance(item, dict)]
    if characters:
        for item in characters:
            lines.append(
                f"- {_text(item.get('name'))}：{_text(item.get('personality'))}"
                f"；长期目标：{_text(item.get('goal'))}"
                f"；当前状态：{_text(item.get('current_state'))}"
                f"；当前目标：{_text(item.get('current_goal'))}"
            )
    else:
        lines.append("暂无人物资料。")

    _section(lines, "世界观规则")
    rules = [item for item in as_list(context.get("world_rules")) if isinstance(item, dict)]
    if rules:
        for item in rules:
            lines.append(f"- {_text(item.get('rule_name'))}：{_text(item.get('limitations'))}")
    else:
        lines.append("暂无世界观规则。")

    _section(lines, "未回收伏笔")
    threads = [item for item in as_list(context.get("open_plot_threads")) if isinstance(item, dict)]
    if threads:
        for item in threads:
            lines.append(f"- 第{_text(item.get('first_chapter'))}章：{_text(item.get('content'))}")
    else:
        lines.append("暂无未回收伏笔。")
    return "\n".join(lines).strip()


def format_review_readable(review: dict[str, Any] | None) -> str:
    if not review:
        return "暂无审稿结果。"
    lines: list[str] = []
    _section(lines, "审稿评分")
    score_labels = [
        ("承接连贯", "continuity_score"),
        ("人设稳定", "character_score"),
        ("情绪有效", "emotion_score"),
        ("节奏控制", "rhythm_score"),
        ("伏笔管理", "foreshadow_score"),
        ("回报兑现", "payoff_score"),
        ("结尾牵引", "hook_score"),
        ("移动端可读", "readability_score"),
    ]
    if "length_score" in review:
        score_labels.append(("字数控制", "length_score"))
    if _int_or_zero(review.get("historical_score")):
        score_labels.append(("历史准确", "historical_score"))
    for label, key in score_labels:
        lines.append(f"{label}：{_text(review.get(key), '0')}/100")

    _section(lines, "主要问题")
    problems = as_list(review.get("problems"))
    if problems:
        for index, item in enumerate(problems, 1):
            if isinstance(item, dict):
                lines.append(
                    f"{index}. [{_label_from_map(item.get('severity'), REVIEW_SEVERITY_LABELS, '未分级')}] "
                    f"{_label_from_map(item.get('type'), REVIEW_TYPE_LABELS)}：{_text(item.get('evidence'))}"
                )
                lines.append(f"   影响：{_text(item.get('why_it_matters'))}")
            else:
                lines.append(f"{index}. {_text(item)}")
    else:
        lines.append("暂无明确问题。")

    _section(lines, "修改建议")
    suggestions = as_list(review.get("suggestions"))
    if suggestions:
        for index, item in enumerate(suggestions, 1):
            if isinstance(item, dict):
                lines.append(f"{index}. 目标：{_text(item.get('target'))}")
                lines.append(f"   做法：{_text(item.get('action'))}")
                lines.append(f"   保留：{_text(item.get('keep'))}")
                lines.append(f"   避免：{_text(item.get('avoid'))}")
            else:
                lines.append(f"{index}. {_text(item)}")
    else:
        lines.append("暂无修改建议。")
    if review.get("length_problem"):
        _section(lines, "字数问题")
        lines.append(_text(review.get("length_problem")))

    _section(lines, "模板句与风险")
    lines.append(f"模板句：{_text(review.get('template_hits'), '未发现')}")
    lines.append(f"风险提示：{_text(review.get('risk_flags'), '未发现')}")
    _section(lines, "重复度")
    repeats = as_list(review.get("repeat_risk"))
    if repeats:
        _add_list(lines, repeats, empty="暂无重复风险")
    else:
        lines.append("暂无重复风险")
    return "\n".join(lines).strip()


def format_memory_readable(memory: dict[str, Any] | None) -> str:
    if not memory:
        return "暂无记忆草稿。"
    memory = _maybe_json(memory)
    if not isinstance(memory, dict):
        return _text(memory, "暂无记忆草稿。")
    lines: list[str] = []
    _section(lines, "本章摘要")
    lines.append(_text(memory.get("summary")))

    sections = [
        ("人物变化", "character_changes"),
        ("人物状态更新", "character_state_updates"),
        ("新增伏笔", "new_foreshadows"),
        ("回收伏笔", "resolved_foreshadows"),
        ("时间线事件", "timeline_events"),
        ("能力变化", "ability_changes"),
        ("关系变化", "relationship_changes"),
        ("历史设定更新", "historical_updates"),
    ]
    for title, key in sections:
        _section(lines, title)
        _add_memory_list(lines, memory.get(key))

    _section(lines, "结尾钩子")
    lines.append(_text(memory.get("ending_hook")))

    handoff = _maybe_json(memory.get("handoff"))
    _section(lines, "下一章接力棒")
    if isinstance(handoff, dict):
        labels = [
            ("当前场景", "current_scene"),
            ("当前时间", "current_time"),
            ("当前人物", "current_characters"),
            ("当前冲突", "current_conflict"),
            ("未解决问题", "unresolved_questions"),
            ("末尾外部动作", "last_external_action"),
            ("末尾关键对白", "last_spoken_line"),
            ("承接物件/证据", "active_object"),
            ("未闭合冲突", "open_conflict"),
            ("下一章必须承接", "next_opening_must_continue"),
            ("下一章第一段任务", "next_first_paragraph_task"),
            ("禁止跳过", "forbidden_jump"),
            ("禁用开头", "forbidden_opening"),
            ("结尾类型", "ending_style"),
        ]
        for label, key in labels:
            value = handoff.get(key)
            if isinstance(value, (list, dict)):
                text = _labeled_value_text(value, MEMORY_FIELD_LABELS) or "未填写"
            else:
                text = _text(value)
            lines.append(f"{label}：{text}")
    else:
        lines.append(_text(handoff))
    return "\n".join(lines).strip()
