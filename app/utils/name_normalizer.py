from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


ROLE_LABEL_PATTERN = r"主角|配角|反派|男主|女主|男配|女配|主人公|人物|角色|待补充|protagonist|supporting|villain"


def normalize_character_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name:
        return ""
    name = re.sub(r"[（(【\[].*?[）)】\]]", "", name)
    name = re.sub(rf"^\s*(?:{ROLE_LABEL_PATTERN})\s*[:：\-—·、\s]+", "", name, flags=re.IGNORECASE)
    name = re.sub(rf"[:：\-—·、\s]+(?:{ROLE_LABEL_PATTERN})\s*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", "", name)
    return name.strip("：:，,。；;、-—·")


def character_identity_key(value: Any) -> str:
    return normalize_character_name(value).casefold()


def aliases_to_official_map(characters: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for character in characters:
        if not isinstance(character, dict):
            continue
        raw_official = str(character.get("name") or "").strip()
        official = normalize_character_name(raw_official)
        if not official:
            continue
        if raw_official and raw_official != official:
            mapping[raw_official] = official
        for alias in _alias_values(character.get("aliases")):
            alias = str(alias or "").strip()
            if alias and alias != official:
                mapping[alias] = official
            normalized_alias = normalize_character_name(alias)
            if normalized_alias and normalized_alias != official:
                mapping[normalized_alias] = official
    return mapping


def normalize_names(value: Any, mapping: dict[str, str], *, strip_aliases: bool = False) -> Any:
    mapping = {
        old: new
        for old, new in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True)
        if old and new and old != new
    }
    if not mapping:
        result = deepcopy(value)
        return _strip_aliases(result) if strip_aliases else result
    result = _replace(deepcopy(value), mapping)
    return _strip_aliases(result) if strip_aliases else result


def normalize_bundle_names(bundle: dict[str, Any], *, strip_aliases: bool = True) -> dict[str, Any]:
    characters = bundle.get("characters", []) if isinstance(bundle, dict) else []
    mapping = aliases_to_official_map(characters if isinstance(characters, list) else [])
    normalized = normalize_names(bundle, mapping, strip_aliases=strip_aliases)
    if isinstance(normalized, dict):
        normalized.setdefault("name_normalization_policy", {})
        normalized["name_normalization_policy"] = {
            "official_name_rule": "characters.name 是唯一正式姓名；aliases 仅用于程序兼容旧名，不得在新内容中使用。",
            "hidden_alias_count": len(mapping),
        }
    return normalized


def _replace(value: Any, mapping: dict[str, str]) -> Any:
    if isinstance(value, str):
        result = value
        for old, new in mapping.items():
            result = result.replace(old, new)
        return result
    if isinstance(value, list):
        return [_replace(item, mapping) for item in value]
    if isinstance(value, dict):
        return {key: _replace(item, mapping) for key, item in value.items()}
    return value


def _strip_aliases(value: Any) -> Any:
    if isinstance(value, list):
        return [_strip_aliases(item) for item in value]
    if isinstance(value, dict):
        return {key: _strip_aliases(item) for key, item in value.items() if key != "aliases"}
    return value


def _alias_values(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return [line.strip() for line in stripped.splitlines() if line.strip()]
        return _alias_values(parsed)
    return [str(value)]
