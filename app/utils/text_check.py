from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import re
from typing import Iterable


DEFAULT_TEMPLATE_BLACKLIST = [
    "重生归来",
    "系统觉醒",
    "全网震惊",
    "她冷笑一声",
    "他冷笑一声",
    "嘴角勾起",
    "三年之期已到",
    "恐怖如斯",
    "所有人都愣住了",
    "你可知我是谁",
    "前所未有的震撼",
    "一切才刚刚开始",
    "事情才刚刚开始",
    "真正的危险还在后面",
    "夜色更深了",
    "没人知道",
    "改变了一切",
    "他终于明白",
    "她终于明白",
    "他不知道的是",
    "她不知道的是",
    "命运的齿轮开始转动",
    "声音不大，却",
    "不容置疑的力量",
    "不易察觉",
    "眼中闪过",
    "眼底闪过",
    "嘴角微扬",
    "嘴角勾起一抹",
    "心中涌起",
    "心头一震",
    "心中暗道",
    "深吸一口气",
    "映入眼帘",
    "不由自主",
    "不禁",
    "仿佛",
    "宛若",
    "犹如",
    "由此可见",
    "综上所述",
    "与此同时",
    "前途无量",
    "未来可期",
    "新的篇章",
]

DEFAULT_TEMPLATE_PATTERNS: list[tuple[str, str]] = [
    ("不是A，而是B式句式", r"不是[^，。！？\n]{1,24}[，,]\s*而是[^，。！？\n]{1,40}"),
    ("不是A不是B而是C式句式", r"不是[^，。！？\n]{1,16}[，,]\s*不是[^，。！？\n]{1,16}[，,]\s*而是"),
    ("万能带着状语", r"[，,]\s*带着[^，。！？\n]{1,24}"),
    ("声音不大却带着式句式", r"声音不大[，,]\s*却[^。！？\n]{1,40}"),
    ("章末预告式空悬念", r"不?知道的是[^。！？\n]{1,40}(风暴|危险|真相|阴谋|开始)"),
    ("章末总结顿悟", r"(终于明白|这才意识到|这一刻[^。！？\n]{0,20}明白)"),
    ("眼神闪过一丝式描写", r"(眼中|眼底|眸中)[^。！？\n]{0,10}闪过[^。！？\n]{0,12}(一丝|一抹|几分)"),
    ("嘴角勾起一抹式描写", r"嘴角[^。！？\n]{0,8}(勾起|扬起)[^。！？\n]{0,12}(一抹|一丝)"),
]

DEFAULT_HISTORICAL_ANACHRONISMS = [
    "手机",
    "微信",
    "短信",
    "电脑",
    "互联网",
    "网络热搜",
    "摄像头",
    "身份证",
    "银行卡",
    "二维码",
    "打印机",
    "塑料袋",
    "塑料",
    "公司",
    "老板",
    "总裁",
    "办公室",
    "电梯",
    "汽车",
    "公交",
    "地铁",
    "外卖",
    "快递",
    "派出所",
    "朋友圈",
    "粉丝",
    "直播",
    "网红",
    "打卡",
    "加班",
]


def detect_template_phrases(
    text: str,
    blacklist: Iterable[str] = DEFAULT_TEMPLATE_BLACKLIST,
) -> list[dict[str, int | str]]:
    counter: Counter[str] = Counter()
    for phrase in blacklist:
        count = text.count(phrase)
        if count:
            counter[phrase] = count
    for label, pattern in DEFAULT_TEMPLATE_PATTERNS:
        count = len(re.findall(pattern, text))
        if count:
            counter[label] += count
    return [{"phrase": phrase, "count": count} for phrase, count in counter.items()]


def detect_historical_anachronisms(
    text: str,
    blacklist: Iterable[str] = DEFAULT_HISTORICAL_ANACHRONISMS,
) -> list[dict[str, int | str]]:
    counter: Counter[str] = Counter()
    for phrase in blacklist:
        count = text.count(phrase)
        if count:
            counter[f"历史穿帮：{phrase}"] = count
    return [{"phrase": phrase, "count": count} for phrase, count in counter.items()]


def blacklist_for_prompt() -> str:
    phrase_lines = [f"- {phrase}" for phrase in DEFAULT_TEMPLATE_BLACKLIST]
    pattern_lines = [f"- {label}" for label, _ in DEFAULT_TEMPLATE_PATTERNS]
    return "\n".join([*phrase_lines, *pattern_lines])


def text_similarity(left: str, right: str) -> float:
    left_sig = _signature(left)
    right_sig = _signature(right)
    if not left_sig or not right_sig:
        return 0.0
    return SequenceMatcher(None, left_sig, right_sig).ratio()


def repeated_text_warnings(
    text: str,
    recent_chapters: Iterable[dict],
    *,
    threshold: float = 0.68,
) -> list[str]:
    warnings: list[str] = []
    for chapter in recent_chapters:
        previous_text = str(chapter.get("final_text") or chapter.get("draft") or "")
        ratio = text_similarity(text, previous_text)
        if ratio >= threshold:
            number = chapter.get("chapter_number") or "前文"
            warnings.append(f"与第{number}章正文相似度过高（{ratio:.0%}）")
    return warnings


def _signature(text: str) -> str:
    normalized = re.sub(r"\s+", "", text)
    normalized = re.sub(r"第\s*\d+\s*章", "第N章", normalized)
    normalized = re.sub(r"[A-Z]-\d+", "X-N", normalized)
    normalized = re.sub(r"\d+", "N", normalized)
    return normalized
