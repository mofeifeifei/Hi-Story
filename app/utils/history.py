from __future__ import annotations

from typing import Any

from app.utils.config import load_prompt


HISTORICAL_KEYWORDS = [
    "历史",
    "朝堂",
    "权谋",
    "古代",
    "古言",
    "宫廷",
    "科举",
    "王朝",
    "争霸",
    "年代",
    "唐朝",
    "宋朝",
    "元朝",
    "明朝",
    "清朝",
    "秦朝",
    "汉朝",
    "三国",
    "魏晋",
    "南北朝",
    "隋唐",
]

HISTORICAL_PROFILE_FIELDS = [
    "dynasty",
    "period",
    "year_range",
    "political_context",
    "official_system",
    "military_system",
    "social_order",
    "daily_life",
    "language_style",
    "taboo_words",
    "allowed_fiction",
    "locked_facts",
    "source_notes",
]


def is_historical_inputs(inputs: dict[str, Any]) -> bool:
    return _contains_historical_keyword(_collect_text(inputs))


def is_historical_bundle(bundle: dict[str, Any]) -> bool:
    profile = bundle.get("historical_profile")
    if isinstance(profile, dict) and any(str(profile.get(key) or "").strip() for key in HISTORICAL_PROFILE_FIELDS):
        return True
    return _contains_historical_keyword(_collect_text(bundle))


def historical_context_for_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    if not is_historical_bundle(bundle):
        return {"enabled": False}
    profile = compact_historical_profile(bundle.get("historical_profile") or {})
    facts = _compact_historical_facts(bundle.get("historical_facts") or [])
    return {
        "enabled": True,
        "trigger_rule": "题材、风格、作品圣经或历史设定卡命中历史类关键词。",
        "profile": profile,
        "facts": facts,
        "compact_context": _join_history_context(profile, facts),
    }


def compact_historical_profile(profile: Any) -> dict[str, str]:
    if not isinstance(profile, dict):
        return {key: "" for key in HISTORICAL_PROFILE_FIELDS}
    return {
        key: str(profile.get(key) or "").strip()
        for key in HISTORICAL_PROFILE_FIELDS
    }


def default_historical_profile(inputs: dict[str, Any], plan: dict[str, Any] | None = None) -> dict[str, str]:
    plan = plan or {}
    text = _collect_text({"inputs": inputs, "plan": plan})
    dynasty = _first_matching_keyword(text, ["唐朝", "宋朝", "元朝", "明朝", "清朝", "秦朝", "汉朝", "三国", "魏晋", "南北朝", "隋唐"])
    return {
        "dynasty": dynasty,
        "period": "",
        "year_range": "",
        "political_context": "",
        "official_system": "",
        "military_system": "",
        "social_order": "",
        "daily_life": "",
        "language_style": "",
        "taboo_words": "手机、微信、电脑、互联网、摄像头、身份证、银行卡、二维码、打印机、塑料、公司、老板、总裁、电梯、汽车、公交、外卖",
        "allowed_fiction": "未明确锁定的角色和支线可以虚构；真实历史人物、制度和重大事件如需改动，必须在锁定设定或用户批注中说明。",
        "locked_facts": "",
        "source_notes": "由题材关键词自动创建，请后续补充具体朝代、年号、制度和资料依据。",
    }


def format_historical_profile(profile: dict[str, Any]) -> str:
    labels = [
        ("朝代", "dynasty"),
        ("具体时期", "period"),
        ("年份范围", "year_range"),
        ("政局背景", "political_context"),
        ("官制/爵位/行政", "official_system"),
        ("军制/兵制", "military_system"),
        ("阶层/宗族/礼法", "social_order"),
        ("衣食住行", "daily_life"),
        ("称谓和语言风格", "language_style"),
        ("禁用现代词/后世词", "taboo_words"),
        ("允许虚构范围", "allowed_fiction"),
        ("不可改历史事实", "locked_facts"),
        ("资料备注", "source_notes"),
    ]
    lines = []
    for label, key in labels:
        value = str(profile.get(key) or "").strip()
        if value:
            lines.append(f"{label}：{value}")
    return "\n".join(lines) if lines else "历史设定卡尚未补充，请仅按用户已给出的时代背景约束写作。"


def _compact_historical_facts(facts: Any) -> list[dict[str, str]]:
    if not isinstance(facts, list):
        return []
    compacted: list[dict[str, str]] = []
    for item in facts[-30:]:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        compacted.append(
            {
                "chapter_number": str(item.get("chapter_number") or "").strip(),
                "category": str(item.get("category") or "").strip(),
                "content": content,
                "future_constraint": str(item.get("future_constraint") or "").strip(),
            }
        )
    return compacted


def _join_history_context(profile: dict[str, Any], facts: list[dict[str, str]]) -> str:
    parts = [format_historical_profile(profile)]
    if facts:
        lines = ["【已落地历史事实】"]
        for item in facts:
            prefix = f"第{item['chapter_number']}章" if item.get("chapter_number") else "前文"
            category = f" / {item['category']}" if item.get("category") else ""
            constraint = f"；后续约束：{item['future_constraint']}" if item.get("future_constraint") else ""
            lines.append(f"- {prefix}{category}：{item['content']}{constraint}")
        parts.append("\n".join(lines))
    return "\n\n".join(part for part in parts if part)


def history_prompt_section(context: dict[str, Any]) -> str:
    specialist = context.get("history_specialist")
    if not isinstance(specialist, dict) or not specialist.get("enabled"):
        return ""
    return (
        "【历史专项约束】\n"
        f"{load_prompt('history_prompt.md')}\n\n"
        "【当前作品历史设定卡】\n"
        f"{specialist.get('compact_context') or format_historical_profile(specialist.get('profile') or {})}\n"
    )


def _contains_historical_keyword(text: str) -> bool:
    return any(keyword in text for keyword in HISTORICAL_KEYWORDS)


def _first_matching_keyword(text: str, keywords: list[str]) -> str:
    for keyword in keywords:
        if keyword in text:
            return keyword
    return ""


def _collect_text(value: Any) -> str:
    parts: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            parts.append(_collect_text(item))
    elif isinstance(value, list):
        for item in value:
            parts.append(_collect_text(item))
    elif value not in (None, ""):
        parts.append(str(value))
    return "\n".join(part for part in parts if part)
