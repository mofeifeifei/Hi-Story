from __future__ import annotations

from typing import Any

from app.utils.json_parser import as_list, parse_json_object


def filter_chapter_bundle(bundle: dict[str, Any], outline_detail: dict[str, Any]) -> dict[str, Any]:
    filtered = dict(bundle)
    filtered["characters"] = _relevant_characters(bundle.get("characters", []), outline_detail)
    filtered["open_plot_threads"] = _relevant_plot_threads(bundle.get("open_plot_threads", []), outline_detail)
    filtered["world_rules"] = _relevant_world_rules(bundle.get("world_rules", []), outline_detail)
    filtered["latest_timeline"] = _latest_items(bundle.get("latest_timeline", []), 10)
    filtered["historical_facts"] = _latest_items(bundle.get("historical_facts", []), 20)
    filtered["minimal_memory_pack"] = _minimal_memory_pack(filtered, outline_detail)
    return filtered


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
        "chapter_focus": {
            "chapter_goal": str(outline_detail.get("chapter_goal") or ""),
            "reader_expectation": str(outline_detail.get("reader_expectation") or ""),
            "target_emotion": str(
                outline_detail.get("emotional_turn")
                or outline_detail.get("emotional_rhythm")
                or ""
            ),
            "chapter_payoff": str(outline_detail.get("chapter_payoff") or ""),
            "opening_hook": str(outline_detail.get("opening_hook") or ""),
            "ending_hook": str(outline_detail.get("ending_hook") or ""),
            "handoff": str(outline_detail.get("handoff") or ""),
        },
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
