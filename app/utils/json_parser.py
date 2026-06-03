from __future__ import annotations

import json
import re
from typing import Any


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def parse_json_object(text: str, default: Any | None = None) -> Any:
    cleaned = strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start = min(
        [idx for idx in [cleaned.find("{"), cleaned.find("[")] if idx != -1],
        default=-1,
    )
    if start == -1:
        return default

    for end in range(len(cleaned), start, -1):
        candidate = cleaned[start:end].strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return default


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]

