from __future__ import annotations

from typing import Any

from app.utils.json_parser import as_list, parse_json_object


def filter_chapter_bundle(bundle: dict[str, Any], outline_detail: dict[str, Any]) -> dict[str, Any]:
    filtered = dict(bundle)
    filtered["genre_contract"] = compact_genre_contract(bundle.get("book_contract", {}))
    filtered.pop("book_contract", None)
    filtered["characters"] = _relevant_characters(bundle.get("characters", []), outline_detail)
    filtered["open_plot_threads"] = _relevant_plot_threads(bundle.get("open_plot_threads", []), outline_detail)
    filtered["world_rules"] = _relevant_world_rules(bundle.get("world_rules", []), outline_detail)
    filtered["latest_timeline"] = _latest_items(bundle.get("latest_timeline", []), 10)
    filtered["historical_facts"] = _latest_items(bundle.get("historical_facts", []), 20)
    filtered["minimal_memory_pack"] = _minimal_memory_pack(filtered, outline_detail)
    return filtered


def context_for_reviewer(context: dict[str, Any]) -> dict[str, Any]:
    return _agent_context(context, task="reviewer")


def context_for_writer(context: dict[str, Any]) -> dict[str, Any]:
    return _agent_context(context, task="writer")


def context_for_reviser(context: dict[str, Any]) -> dict[str, Any]:
    return _agent_context(context, task="reviser")


def context_for_memory(context: dict[str, Any]) -> dict[str, Any]:
    return _agent_context(context, task="memory")


def compact_genre_contract(contract: Any) -> dict[str, str]:
    if not isinstance(contract, dict):
        return {}
    fields = [
        "genre_core",
        "reader_promise",
        "conflict_engine",
        "chapter_payoff",
        "opening_preference",
        "avoid",
    ]
    result = {
        field: str(contract.get(field) or "").strip()
        for field in fields
        if str(contract.get(field) or "").strip()
    }
    if not result:
        return {}
    return {
        "genre_core": result.get("genre_core", ""),
        "reader_promise": result.get("reader_promise", ""),
        "conflict_engine": result.get("conflict_engine", ""),
        "chapter_payoff": result.get("chapter_payoff", ""),
        "opening_preference": result.get("opening_preference", ""),
        "avoid": result.get("avoid", ""),
        "usage_rule": "每章只按这些短字段保持题材味道，不展开成长篇专项提示词。",
    }


def _outline_text(outline_detail: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in outline_detail.values():
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif isinstance(value, dict):
            parts.extend(str(item) for item in value.values())
    return "\n".join(parts)


def _relevant_characters(characters: list[dict[str, Any]], outline_detail: dict[str, Any]) -> list[dict[str, Any]]:
    if len(characters) <= 6:
        return characters
    text = _outline_text(outline_detail)
    relevant = [character for character in characters if _character_matches_text(character, text)]
    protagonist = [
        character
        for character in characters
        if _is_protagonist(character) and character not in relevant
    ]
    result = [*protagonist[:1], *relevant]
    if not result:
        result = [*protagonist[:1], *characters[:6]]
    return result[:8]


def _character_matches_text(character: dict[str, Any], text: str) -> bool:
    for value in _character_names(character):
        if value and value in text:
            return True
    return False


def _character_names(character: dict[str, Any]) -> list[str]:
    values = [str(character.get("name") or "").strip()]
    aliases = character.get("aliases")
    parsed_aliases = parse_json_object(str(aliases or ""), default=aliases)
    for alias in as_list(parsed_aliases):
        text = str(alias or "").strip()
        if text:
            values.append(text)
    return list(dict.fromkeys(value for value in values if value))


def _is_protagonist(character: dict[str, Any]) -> bool:
    role = str(character.get("role") or "").lower()
    name = str(character.get("name") or "").lower()
    return any(token in role or token in name for token in ["主角", "男主", "女主", "protagonist"])


def _relevant_plot_threads(threads: list[dict[str, Any]], outline_detail: dict[str, Any]) -> list[dict[str, Any]]:
    if len(threads) <= 8:
        return threads
    text = _outline_text(outline_detail)
    matched = [
        thread
        for thread in threads
        if thread.get("content") and _has_keyword_overlap(str(thread["content"]), text)
    ]
    result = matched or threads[:8]
    return result[:10]


def _relevant_world_rules(rules: list[dict[str, Any]], outline_detail: dict[str, Any]) -> list[dict[str, Any]]:
    if len(rules) <= 8:
        return rules
    text = _outline_text(outline_detail)
    matched = [
        rule
        for rule in rules
        if _world_rule_matches_text(rule, text)
    ]
    return (matched or rules[:8])[:10]


def _world_rule_matches_text(rule: dict[str, Any], text: str) -> bool:
    rule_name = str(rule.get("rule_name") or "").strip()
    if rule_name and rule_name in text:
        return True
    rule_text = " ".join(
        str(rule.get(key) or "")
        for key in ["rule_content", "limitations", "forbidden_changes"]
    )
    return _has_keyword_overlap(rule_text, text)


def _minimal_memory_pack(bundle: dict[str, Any], outline_detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "selection_rule": "只保留如果不知道这个，本章就会写错的信息。",
        "character_states": [_character_memory_item(item) for item in bundle.get("characters", [])],
        "related_foreshadows": [_thread_memory_item(item) for item in bundle.get("open_plot_threads", [])],
        "world_constraints": [_rule_memory_item(item) for item in bundle.get("world_rules", [])],
        "historical_constraints": [_historical_fact_memory_item(item) for item in bundle.get("historical_facts", [])],
    }


def _character_memory_item(character: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": character.get("name", ""),
        "role": character.get("role", ""),
        "current_goal": character.get("current_goal", ""),
        "current_fear": character.get("current_fear", ""),
        "current_state": character.get("current_state", ""),
        "relationship_stage": character.get("relationship_stage", ""),
        "speaking_style": character.get("speaking_style", ""),
        "locked_rules": character.get("locked_rules", ""),
    }


def _thread_memory_item(thread: dict[str, Any]) -> dict[str, Any]:
    return {
        "first_chapter": thread.get("first_chapter"),
        "content": thread.get("content", ""),
        "status": thread.get("status", ""),
        "planned_resolve_chapter": thread.get("planned_resolve_chapter"),
    }


def _rule_memory_item(rule: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_name": rule.get("rule_name", ""),
        "rule_content": rule.get("rule_content", ""),
        "limitations": rule.get("limitations", ""),
        "forbidden_changes": rule.get("forbidden_changes", ""),
    }


def _historical_fact_memory_item(fact: dict[str, Any]) -> dict[str, Any]:
    return {
        "chapter_number": fact.get("chapter_number"),
        "category": fact.get("category", ""),
        "content": fact.get("content", ""),
        "future_constraint": fact.get("future_constraint", ""),
    }


def _has_keyword_overlap(left: str, right: str) -> bool:
    tokens = [token for token in left.replace("，", " ").replace("。", " ").split() if len(token) >= 2]
    return any(token in right for token in tokens[:8])


def _latest_items(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(items) <= limit:
        return items
    return items[-limit:]


def _agent_context(context: dict[str, Any], *, task: str) -> dict[str, Any]:
    chapter = context.get("chapter") if isinstance(context.get("chapter"), dict) else {}
    memory_pack = context.get("minimal_memory_pack")
    if not isinstance(memory_pack, dict):
        memory_pack = {}
    task_sheet = _compact_task_sheet(chapter.get("outline_detail"))
    result: dict[str, Any] = {
        "work": _pick(context.get("work"), _work_keys(task)),
        "chapter": _pick(
            chapter,
            [
                "id",
                "chapter_number",
                "title",
            ],
        ),
        "story_plan": task_sheet,
        "book_bible": _compact_book_bible(context.get("book_bible")),
        "genre_contract": compact_genre_contract(
            context.get("genre_contract") or context.get("book_contract", {})
        ),
        "chapter_word_target": context.get("chapter_word_target", {}),
        "minimal_memory_pack": memory_pack,
        "scene_handoff": _compact_scene_handoff(context),
        "chapter_notes": _compact_notes(context.get("chapter_notes")),
        "history_specialist": _history_marker(context.get("history_specialist")),
        "style_guard": _compact_style_guard(context),
        "recent_title_ledger": context.get("recent_title_ledger", []),
    }
    if task == "reviewer":
        result["minimal_memory_pack"] = {
            "selection_rule": "只保留如果不知道这个，本章就会写错的信息。",
            "historical_constraints": memory_pack.get("historical_constraints", []),
        }
        result.update(
            {
                "previous_chapter": _previous_chapter(context.get("previous_chapter")),
                "characters": _compact_items(context.get("characters"), _character_keys(), 8),
                "world_rules": _compact_items(context.get("world_rules"), _world_rule_keys(), 8),
                "open_plot_threads": _compact_items(context.get("open_plot_threads"), _thread_keys(), 10),
                "recent_three_chapter_summaries": _compact_recent_summaries(
                    context.get("recent_three_chapter_summaries")
                ),
                "opening_variation_policy": context.get("opening_variation_policy", {}),
                "ending_variation_policy": context.get("ending_variation_policy", {}),
                "repeat_risk_warnings": context.get("repeat_risk_warnings", []),
                "local_quality_report": context.get("local_quality_report", {}),
                "recent_style_signatures": _recent_style_signatures(context),
            }
        )
    return _drop_empty(result)


def _work_keys(task: str) -> list[str]:
    keys = [
        "title",
        "genre",
        "platform",
        "target_words",
        "style",
        "reader_profile",
        "locked_facts",
    ]
    if task == "memory":
        return ["title", "genre", "summary"]
    return keys


def _compact_book_bible(value: Any) -> dict[str, Any]:
    return _pick(
        value,
        [
            "core_reading_promise",
            "primary_genre",
            "secondary_genres",
            "emotional_tone",
            "narrative_driver",
            "protagonist_end_goal",
            "long_form_engine",
            "must_keep_rules",
            "forbidden_drift",
        ],
    )


def _compact_task_sheet(value: Any) -> dict[str, Any]:
    detail = value if isinstance(value, dict) else {}
    task = _pick(
        detail,
        [
            "outline",
            "sequence_id",
            "sequence_goal",
            "sequence_position",
            "chapter_goal",
            "conflict",
            "main_scene",
            "chapter_payoff",
            "first_screen_conflict",
            "reader_question_in",
            "reader_answer_out",
            "new_question_out",
            "emotional_turn",
            "cut_reason",
            "forbidden",
        ],
    )
    task["scene_cards"] = _compact_scene_cards(detail.get("scene_cards"))
    return _drop_empty(task)


def _compact_scene_cards(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    keys = ["scene_goal", "obstacle", "information_gain", "emotional_shift", "scene_exit"]
    return [_pick(item, keys) for item in value if isinstance(item, dict) and _pick(item, keys)][:6]


def _compact_bridge_pack(value: Any) -> dict[str, Any]:
    return _pick(
        value,
        [
            "source_chapter",
            "source_title",
            "previous_tail_excerpt",
            "last_visible_beat",
            "unresolved_pressure",
            "required_next_beat",
            "allowed_shift",
            "shift_reason",
            "bridge_rule",
        ],
    )


def _compact_scene_handoff(context: dict[str, Any]) -> dict[str, Any]:
    bridge = context.get("chapter_bridge_pack")
    if not isinstance(bridge, dict):
        bridge = {}
    execution = context.get("chapter_execution_card")
    if not isinstance(execution, dict):
        execution = {}
    detail = context.get("chapter")
    detail = detail.get("outline_detail") if isinstance(detail, dict) else {}
    if not isinstance(detail, dict):
        detail = {}
    allowed_shift = bool(bridge.get("allowed_shift") or detail.get("allowed_shift"))
    mode = str(detail.get("continuity_mode") or ("shift" if allowed_shift else "direct")).strip()
    return _drop_empty(
        {
            "source_chapter": bridge.get("source_chapter"),
            "scene_id": detail.get("scene_id") or detail.get("sequence_id"),
            "mode": mode,
            "previous_text": bridge.get("previous_tail_excerpt"),
            "last_event": bridge.get("last_visible_beat") or execution.get("last_visible_beat"),
            "unfinished_action": bridge.get("unresolved_pressure"),
            "first_event": bridge.get("required_next_beat") or execution.get("first_screen_task"),
            "active_people": detail.get("characters_present"),
            "location": detail.get("main_scene"),
            "shift_reason": bridge.get("shift_reason") or detail.get("shift_reason"),
        }
    )


def _compact_notes(value: Any) -> list[dict[str, Any]]:
    return _compact_items(value, ["note_type", "content", "created_at"], 6)


def _compact_style_guard(context: dict[str, Any]) -> dict[str, Any]:
    opening = context.get("opening_variation_policy")
    ending = context.get("ending_variation_policy")
    return _drop_empty(
        {
            "opening": _pick(
                opening,
                [
                    "instruction",
                    "repeated_opening_mode",
                    "repeated_surface_anchors",
                    "repeated_opening_engine",
                    "repeated_syntax_shapes",
                ],
            ),
            "ending": _pick(
                ending,
                [
                    "instruction",
                    "repeated_anchor_type",
                    "repeated_concrete_anchors",
                    "repeated_dash_ending",
                    "repeated_contrast_ending",
                ],
            ),
        }
    )


def _history_marker(value: Any) -> dict[str, bool]:
    return {"enabled": bool(isinstance(value, dict) and value.get("enabled"))}


def _recent_style_signatures(context: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    opening_keys = [
        "chapter_number",
        "title",
        "pattern",
        "rhetorical_flags",
        "opening_mode",
        "opening_engine",
        "primary_surface_anchor",
        "subject_type",
        "syntax_shape",
    ]
    ending_keys = [
        "chapter_number",
        "title",
        "anchor_type",
        "concrete_anchors",
        "rhetorical_flags",
        "dash_count",
        "contrast_count",
        "abstract_forecast",
    ]
    return {
        "openings": _compact_items(context.get("recent_chapter_openings"), opening_keys, 5),
        "endings": _compact_items(context.get("recent_chapter_endings"), ending_keys, 5),
    }


def _character_keys() -> list[str]:
    return [
        "name",
        "role",
        "personality",
        "goal",
        "current_goal",
        "current_fear",
        "current_state",
        "relationship",
        "relationship_stage",
        "speaking_style",
        "locked_rules",
    ]


def _character_memory_keys() -> list[str]:
    return [
        "name",
        "role",
        "current_goal",
        "current_fear",
        "current_state",
        "relationship_stage",
        "locked_rules",
    ]


def _world_rule_keys() -> list[str]:
    return ["rule_name", "rule_content", "limitations", "forbidden_changes"]


def _thread_keys() -> list[str]:
    return ["first_chapter", "content", "status", "planned_resolve_chapter", "actual_resolve_chapter"]


def _previous_chapter(value: Any) -> dict[str, Any]:
    return _pick(
        value,
        [
            "chapter_number",
            "title",
            "summary",
        ],
    )


def _compact_recent_summaries(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value[-2:]:
        if not isinstance(item, dict):
            continue
        result.append(
            _drop_empty(
                {
                    "chapter_number": item.get("chapter_number"),
                    "title": item.get("title"),
                    "summary": str(item.get("summary") or "")[:600],
                    "ending_hook": str(item.get("ending_hook") or "")[:240],
                    "handoff": str(item.get("handoff") or "")[:240],
                }
            )
        )
    return result


def _history_specialist_for_task(value: Any, task: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not value.get("enabled"):
        return {"enabled": False}
    fact_limit = {"reviewer": 12, "reviser": 8, "memory": 5}.get(task, 12)
    return _drop_empty(
        {
            "enabled": True,
            "trigger_rule": value.get("trigger_rule", ""),
            "profile": _selected_history_profile(value.get("profile")),
            "facts": _latest_items(value.get("facts") or [], fact_limit),
        }
    )


def _selected_history_profile(value: Any) -> dict[str, Any]:
    return _pick(
        value,
        [
            "dynasty",
            "period",
            "year_range",
            "current_ruler",
            "official_system",
            "central_official_system",
            "local_administration",
            "noble_titles",
            "exam_system",
            "military_system",
            "military_ranks",
            "weapons",
            "social_order",
            "daily_life",
            "currency",
            "measurements",
            "geo_notes",
            "travel_speed",
            "communication_speed",
            "language_style",
            "address_terms",
            "taboo_words",
            "allowed_fiction",
            "fiction_boundary",
            "locked_facts",
        ],
    )


def _compact_items(value: Any, keys: list[str], limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = [_pick(item, keys) for item in value if isinstance(item, dict)]
    return [item for item in result if item][:limit]


def _pick(value: Any, keys: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return _drop_empty({key: value.get(key) for key in keys if key in value})


def _drop_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item not in (None, "", [], {})
    }
