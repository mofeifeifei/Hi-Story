from __future__ import annotations

import re
from typing import Any


def chapter_word_target_from_style(style: Any) -> dict[str, Any]:
    label = _chapter_words_label(style)
    if not label:
        return {
            "label": "",
            "target": None,
            "min": None,
            "max": None,
            "strict": False,
            "note": "用户未设置单章字数。优先保证章节完整，不能写成短摘要。",
        }
    if "自然" in label or "剧情" in label:
        return {
            "label": label,
            "target": None,
            "min": None,
            "max": None,
            "strict": False,
            "note": "按剧情自然分配，不强行凑字数；但必须是完整章节，不能写成短摘要、梗概或片段。",
        }
    match = re.search(r"(\d{3,6})", label)
    if not match:
        return {
            "label": label,
            "target": None,
            "min": None,
            "max": None,
            "strict": False,
            "note": "无法解析具体目标字数。尽量接近用户填写的单章字数要求，不能写成短摘要。",
        }
    target = int(match.group(1))
    margin = max(100, int(target * 0.1))
    return {
        "label": label,
        "target": target,
        "min": max(1, target - margin),
        "max": target + margin,
        "strict": True,
        "note": "正文应尽量落在建议范围内；不得为了凑字数重复解释、重复心理活动或重复环境描写。",
    }


def _chapter_words_label(style: Any) -> str:
    text = str(style or "")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"单章字数[：:]\s*(.+)", stripped)
        if match:
            return match.group(1).strip()
    return ""
