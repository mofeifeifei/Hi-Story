from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import re
from typing import Any, Iterable


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

EMPTY_ENDING_PHRASES = [
    "一切才刚刚开始",
    "事情才刚刚开始",
    "真正的危险还在后面",
    "夜色更深了",
    "没人知道",
    "改变了一切",
    "他终于明白",
    "她终于明白",
    "命运的齿轮开始转动",
]

ABSTRACT_ENDING_WORDS = [
    "命运",
    "风暴",
    "黑暗",
    "夜色",
    "倒计时",
    "那条线",
    "深渊",
    "暗流",
    "迷雾",
    "真相还在后面",
    "危险还在后面",
    "一切才刚开始",
    "事情才刚开始",
]

CONCRETE_ENDING_WORDS = [
    "门",
    "窗",
    "手",
    "刀",
    "剑",
    "血",
    "伤",
    "信",
    "纸",
    "名单",
    "账册",
    "证据",
    "令",
    "印",
    "钥匙",
    "脚步",
    "敲门",
    "马蹄",
    "火",
    "灯",
    "尸",
    "药",
    "箭",
    "绳",
    "匣",
    "牌",
]

CONCRETE_ENDING_ACTION_RE = re.compile(
    r"(递|推|按|扣|拔|落|砸|撕|扔|握|攥|掀|打开|关上|敲|撞|跪|站|退|冲|追|抓|拖|刺|砍|咬|吐|流|亮出|交出|藏起|封住|拦住|逼近|停住|响起)"
)

OPENING_ENDING_REPAIR_MARKERS = [
    "章首",
    "开篇",
    "第一屏",
    "接力棒",
    "具体锚点",
    "空泛收束",
    "抽象氛围",
    "外部锚点",
    "章末",
    "结尾",
    "承接债",
    "开头方式",
    "开头触发",
]

FORBIDDEN_OPENING_KEYWORDS = [
    "晨光",
    "晨雾",
    "清晨",
    "卯时",
    "辰时",
    "天未亮",
    "天色未明",
    "驿站",
    "驿馆",
    "门前",
    "马棚",
    "上马",
    "出发",
    "整备",
    "醒来",
    "看了看",
    "检查",
    "整理",
    "推门",
    "赶路",
]

ANCHOR_KEYWORDS = [
    "证据",
    "线索",
    "封蜡",
    "折痕",
    "划痕",
    "名单",
    "账册",
    "文书",
    "书信",
    "令牌",
    "钥匙",
    "脚印",
    "血",
    "伤口",
    "命令",
    "威胁",
    "敲门",
    "门外",
    "追兵",
    "尸体",
    "兵器",
    "刀",
    "箭",
    "马鞍袋",
    "皮囊",
    "选择",
    "关系",
    "问题",
    "疑问",
    "回答",
    "缺席",
    "异常",
]

OPENING_MODE_VALUES = [
    "物件",
    "对白",
    "异常",
    "后果",
    "反应",
    "命令",
    "缺席",
    "冲突",
    "时间压力",
    "环境异常",
    "人物动作",
    "其他",
]

OPENING_MODE_COMPATIBLE = {
    "物件": {"异常"},
    "异常": {"物件", "环境异常"},
    "冲突": {"命令", "反应"},
    "命令": {"冲突"},
    "反应": {"冲突", "后果"},
    "后果": {"反应", "异常"},
    "时间压力": {"环境异常"},
    "环境异常": {"时间压力", "异常"},
}

_HEADING_LINE_RE = re.compile(
    r"^\s*(?:[#＃]+\s*)?(?:第\s*[\d一二三四五六七八九十百千万〇零两]+\s*[章节回集卷幕]|章节名\s*[：:]|标题\s*[：:])"
)

OPENING_TIME_RE = re.compile(
    r"^\s*(?:"
    r"(?:卯|辰|巳|午|未|申|酉|戌|亥|子|丑|寅)时"
    r"|[一二三四五六七八九十半三两]+更"
    r"|[\u4e00-\u9fff]{2,8}(?:元|[一二三四五六七八九十百千万〇零两]+)年(?:春|夏|秋|冬)?"
    r"|距[^，。！？\n]{2,24}(?:仅余|只剩|还剩|不过)"
    r"|翌日|次日|清晨|晨间|天色|天刚亮|黄昏|入夜|深夜|夜里|黎明|拂晓"
    r"|天(?:尚未|还未|还没|未)?全?亮|天色(?:未明|微明|将明)|晨光|晨色"
    r"|日头|月上|鸡鸣|晨钟|暮鼓|街鼓|钟声|鼓声|漏声"
    r")"
)
OPENING_PLACE_RE = re.compile(
    r"^\s*[\u4e00-\u9fff]{1,12}(?:"
    r"门外|门前|门内|城外|城中|城内|街上|巷口|府中|府外|府衙|县衙|官署|"
    r"书房|院中|殿内|殿外|宫中|营中|船上|渡口|码头|堂前|廊下|案前"
    r")"
)
OPENING_PLACE_NEAR_RE = re.compile(
    r"[\u4e00-\u9fff]{1,12}(?:"
    r"门外|门前|门内|城外|城中|城内|街上|巷口|坊巷|巷里|一带|府中|府外|府衙|县衙|官署|"
    r"书房|院中|殿内|殿外|宫中|营中|船上|渡口|码头|堂前|廊下|案前"
    r")"
)
OPENING_ENV_RE = re.compile(
    r"^\s*(?:"
    r"晨雾|薄雾|雾气|雨声|风声|雪|霜|雾|日光|阳光|月色|夜色|灯火|烛火|天光|"
    r"暮色|寒意|热气|尘土|檐雨|雨丝|风从"
    r")"
)
OPENING_ENV_NEAR_RE = re.compile(
    r"(?:晨雾|薄雾|雾气|雨声|风声|雪|霜|日光|阳光|月色|夜色|灯火|烛火|天光|暮色|寒意|檐雨|雨丝)"
)
OPENING_ATMOSPHERE_WORDS = [
    "晨雾",
    "薄雾",
    "雾气",
    "雨声",
    "风声",
    "日光",
    "夜色",
    "天尚未全亮",
    "天色未明",
    "天未亮",
    "晨光",
    "晨色",
    "街鼓",
    "钟声",
    "鼓声",
    "漏声",
    "卯时",
    "辰时",
    "巳时",
    "午时",
    "未时",
    "申时",
    "酉时",
    "戌时",
    "亥时",
]

FIRST_SCREEN_HOOK_RE = re.compile(
    r"(?:"
    r"不对|不见|消失|失踪|异常|反常|可疑|破绽|矛盾|漏洞|假|伪|错|换|动过|多出|少了|"
    r"证据|反证|线索|账册|名单|告示|文书|密报|封蜡|印泥|朱砂|血|伤|尸|毒|火|刀|弩|兵器|"
    r"威胁|追兵|搜查|戒严|围住|堵住|抓人|押走|通缉|命令|军令|诏令|期限|仅余|只剩|来不及|"
    r"为什么|为何|怎么|谁|哪来|竟然|偏偏|必须|否则|不能|不准|拒绝|选择|代价|背叛|质问"
    r")"
)

LOW_VALUE_OPENING_RE = re.compile(
    r"^\s*[\u4e00-\u9fff]{1,8}"
    r"(?:把[^。！？\n]{0,28})?"
    r"(?:又|再|反复|重新|仔细)?"
    r"(?:看了看|看见|看着|检查|翻看|摸了摸|拿起|放下|走出|走进|翻身上马|上马|下马|沉默|没有说话|点了点头)"
)


def first_paragraph(text: str, *, max_chars: int = 220) -> str:
    for part in re.split(r"\n\s*\n|\r\n\s*\r\n", str(text or "").strip()):
        compact = part.strip()
        if compact:
            return compact[:max_chars]
    return ""


def opening_pattern_flags(opening: str) -> list[str]:
    first = first_paragraph(opening, max_chars=160)
    first_sentence = re.split(r"[。！？!?]\s*", first, maxsplit=1)[0].strip()
    flags: list[str] = []
    if OPENING_TIME_RE.search(first_sentence):
        flags.append("时间/时辰")
    if OPENING_PLACE_RE.search(first_sentence) or OPENING_PLACE_NEAR_RE.search(first_sentence[:90]):
        flags.append("地点陈列")
    if OPENING_ENV_RE.search(first_sentence) or OPENING_ENV_NEAR_RE.search(first_sentence[:90]):
        flags.append("天气/环境")
    if any(word in first_sentence[:80] for word in OPENING_ATMOSPHERE_WORDS):
        flags.append("古装氛围词")
    return _dedupe(flags)


def opening_pattern_label(opening: str) -> str:
    flags = opening_pattern_flags(opening)
    return " + ".join(flags) if flags else "动作/对白/冲突"


def detect_opening_mode(opening: str) -> str:
    first = first_paragraph(opening, max_chars=220)
    first_sentence = re.split(r"[。！？!?]\s*", first, maxsplit=1)[0].strip()
    if not first_sentence:
        return "其他"
    if first_sentence.startswith(("“", "\"")) or re.search(r"(问道|说道|答道|喝道|低声道|沉声道|冷声道|道[：:])", first_sentence[:80]):
        return "对白"
    if any(word in first[:140] for word in ["没有来", "不见", "空无一人", "只留下", "缺席", "少了一个人"]):
        return "缺席"
    if any(word in first[:140] for word in ["命令", "军令", "诏令", "文书", "批条", "令牌", "札子", "急报"]):
        return "命令"
    if any(word in first[:140] for word in ["堵", "拦", "围", "争执", "质问", "逼问", "拔刀", "按刀"]):
        return "冲突"
    if any(word in first[:140] for word in ["脸色", "僵", "怔", "退了一步", "手先", "呼吸", "发抖"]):
        return "反应"
    if any(word in first[:140] for word in ["不对", "异常", "反常", "多出", "少了", "动过", "裂", "血", "封蜡", "划痕", "粉末"]):
        return "异常"
    if any(word in first[:140] for word in ["马鞍袋", "账册", "名单", "信", "纸", "刀", "钥匙", "印", "封蜡", "皮囊", "木匣"]):
        return "物件"
    if OPENING_TIME_RE.search(first_sentence) and _has_first_screen_hook(first):
        return "时间压力"
    if (OPENING_ENV_RE.search(first_sentence) or OPENING_ENV_NEAR_RE.search(first[:100])) and _has_first_screen_hook(first):
        return "环境异常"
    if LOW_VALUE_OPENING_RE.search(first_sentence) or re.match(r"^\s*[\u4e00-\u9fff]{1,6}(?:把|从|向|在|没有|低头|抬头|伸手|翻身|走|站|坐)", first_sentence):
        return "人物动作"
    return "其他"


def _has_first_screen_hook(text: str) -> bool:
    first = first_paragraph(text, max_chars=320)
    if not first:
        return False
    if FIRST_SCREEN_HOOK_RE.search(first):
        return True
    if "？" in first or "?" in first or "！" in first or "!" in first:
        return True
    if "“" in first[:120] or '"' in first[:120]:
        return FIRST_SCREEN_HOOK_RE.search(first) is not None
    return False


def _first_screen_hook_warning(text: str) -> str:
    first = first_paragraph(text, max_chars=320)
    if not first:
        return ""
    if _has_first_screen_hook(first):
        return ""
    first_sentence = re.split(r"[。！？!?]\s*", first, maxsplit=1)[0].strip()
    if LOW_VALUE_OPENING_RE.search(first_sentence):
        return "章首有动作，但第一屏缺少问题、压力、异常、威胁、选择或反证，容易显得平。"
    flags = opening_pattern_flags(first)
    if flags:
        return "章首有时间、地点或环境信息，但第一屏缺少叙事钩子；时间和环境需要带出倒计时、异常、威胁、反证或代价。"
    return ""


def chapter_opening_warning(text: str, context: dict[str, Any]) -> str:
    current_flags = opening_pattern_flags(text)
    copied_outline = _copied_outline_opening_warning(text, context)
    if copied_outline:
        return copied_outline
    hook_warning = _first_screen_hook_warning(text)
    if hook_warning:
        return hook_warning
    if not current_flags:
        return ""
    recent = context.get("recent_chapter_openings")
    if not isinstance(recent, list):
        recent = []
    recent_flag_sets = []
    for item in recent[-3:]:
        if isinstance(item, dict):
            flags = item.get("pattern_flags") or opening_pattern_flags(str(item.get("opening") or ""))
            if flags:
                recent_flag_sets.append(set(str(flag) for flag in flags))
    repeated = sorted(set(current_flags).intersection(*recent_flag_sets)) if len(recent_flag_sets) >= 2 else []
    if repeated:
        return "章首连续使用" + "、".join(repeated) + "开头，AI味明显；请换成不同的第一屏策略，并让开头带出问题、压力、异常、威胁、选择或反证。"
    if len(current_flags) >= 2 and not _has_first_screen_hook(text):
        return "章首使用时间/地点/环境式静态开场，但第一屏没有形成问题、压力、异常、威胁、选择或反证。"
    return ""


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


def manuscript_quality_report(
    text: str,
    context: dict[str, Any] | None = None,
    *,
    chapter_number: int | None = None,
    chapter_title: Any = "",
    stage: str = "正文",
) -> dict[str, Any]:
    context = context or {}
    cleaned = str(text or "").strip()
    visible_chars = _visible_length(cleaned)
    blockers: list[str] = []
    warnings: list[str] = []
    risk_flags: list[str] = []

    if not cleaned:
        blockers.append(f"{stage}为空，不能保存。")
    first_line = _first_nonempty_line(cleaned)
    if first_line and _looks_like_heading(first_line, chapter_number, chapter_title):
        blockers.append("正文第一行仍然包含章节号、章节名或标题行。")
    if _looks_like_structured_leak(cleaned):
        blockers.append("正文疑似混入 JSON、Markdown 代码块或结构化协议内容。")
    if _looks_like_summary(cleaned, visible_chars):
        blockers.append("正文像章节摘要或提纲，不像完整章节。")

    length_problem = _length_problem(visible_chars, context.get("chapter_word_target"))
    if length_problem:
        if length_problem.startswith("严重"):
            blockers.append(length_problem)
        else:
            warnings.append(length_problem)

    ending_problem = _ending_problem(cleaned)
    if ending_problem:
        blockers.append(ending_problem)

    template_hits = detect_template_phrases(cleaned)
    if template_hits:
        warnings.append("正文命中模板句或机器味表达。")
        risk_flags.extend(_hit_labels(template_hits))

    historical_hits: list[dict[str, int | str]] = []
    if _history_enabled(context):
        historical_hits = detect_historical_anachronisms(cleaned)
        if historical_hits:
            warnings.append("历史类作品中疑似出现现代词或时代违和词。")
            risk_flags.extend(_hit_labels(historical_hits))

    transition_warning = _transition_warning(cleaned, context)
    if transition_warning:
        warnings.append(transition_warning)

    opening_contract_problem = _opening_contract_problem(cleaned, context)
    if opening_contract_problem:
        blockers.append(opening_contract_problem)

    opening_warning = chapter_opening_warning(cleaned, context)
    if opening_warning:
        if opening_warning.startswith("章首连续使用"):
            blockers.append(opening_warning)
        else:
            warnings.append(opening_warning)

    return {
        "stage": stage,
        "blockers": _dedupe(blockers),
        "warnings": _dedupe(warnings),
        "template_hits": template_hits,
        "historical_hits": historical_hits,
        "risk_flags": _dedupe(risk_flags),
        "length_problem": "" if length_problem and length_problem.startswith("严重") else length_problem,
        "visible_chars": visible_chars,
        "opening_mode": detect_opening_mode(cleaned),
    }


def opening_ending_repair_issues(report: dict[str, Any] | None) -> list[str]:
    if not isinstance(report, dict):
        return []
    issues: list[str] = []
    for item in [*(report.get("blockers") or []), *(report.get("warnings") or [])]:
        text = str(item or "").strip()
        if text and any(marker in text for marker in OPENING_ENDING_REPAIR_MARKERS):
            issues.append(text)
    return _dedupe(issues)


def quality_summary(report: dict[str, Any] | None) -> str:
    if not isinstance(report, dict):
        return ""
    parts = [f"{report.get('stage') or '正文'}：{report.get('visible_chars') or 0} 字符"]
    blockers = report.get("blockers") or []
    warnings = report.get("warnings") or []
    parts.append(f"阻断 {len(blockers)} 项")
    parts.append(f"警告 {len(warnings)} 项")
    return "，".join(parts)


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


def _visible_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _first_nonempty_line(text: str) -> str:
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _looks_like_heading(line: str, chapter_number: int | None, chapter_title: Any) -> bool:
    compact = _signature(line)
    title = _signature(str(chapter_title or ""))
    if title and compact == title:
        return True
    if _HEADING_LINE_RE.match(line) and len(compact) <= 40:
        return True
    if chapter_number is not None and re.match(rf"^\s*第\s*{int(chapter_number)}\s*章", line):
        return True
    return False


def _looks_like_structured_leak(text: str) -> bool:
    head = text.lstrip()[:300]
    if head.startswith(("```", "{", "[")):
        return True
    return any(marker in head for marker in ['"chapter_number"', '"summary"', '"handoff"', "```json"])


def _looks_like_summary(text: str, visible_chars: int) -> bool:
    head = text[:160]
    summary_markers = [
        "本章主要",
        "这一章主要",
        "本章讲述",
        "本章内容",
        "本章摘要",
        "章节摘要",
        "章节细纲",
        "本章细纲",
        "任务单",
        "本章目标",
        "核心冲突",
        "出场人物",
    ]
    if visible_chars < 260:
        return any(phrase in head for phrase in summary_markers)
    return visible_chars < 900 and any(phrase in head for phrase in summary_markers[:6])


def _length_problem(visible_chars: int, target: Any) -> str:
    if not isinstance(target, dict):
        return "正文长度偏短，可能不像完整章节。" if visible_chars < 800 else ""
    minimum = _int_or_none(target.get("min"))
    maximum = _int_or_none(target.get("max"))
    strict = bool(target.get("strict"))
    if strict and minimum and visible_chars < int(minimum * 0.55):
        return f"严重字数不足：当前约 {visible_chars} 字符，建议至少 {minimum}。"
    if minimum and visible_chars < int(minimum * 0.85):
        return f"字数偏低：当前约 {visible_chars} 字符，建议范围下限 {minimum}。"
    if maximum and visible_chars > int(maximum * 1.35):
        return f"字数明显偏高：当前约 {visible_chars} 字符，建议范围上限 {maximum}。"
    if not minimum and visible_chars < 800:
        return "正文长度偏短，可能不像完整章节。"
    return ""


def _ending_problem(text: str) -> str:
    tail = text[-240:]
    for phrase in EMPTY_ENDING_PHRASES:
        if phrase in tail:
            return f"章末使用空泛收束：{phrase}。"
    compact_tail = re.sub(r"\s+", "", tail)
    if any(word in compact_tail for word in ABSTRACT_ENDING_WORDS) and not _has_concrete_ending_anchor(compact_tail):
        return "章末落在抽象氛围或心理判断上，缺少下一章可承接的外部锚点。"
    return ""


def _has_concrete_ending_anchor(tail: str) -> bool:
    if "“" in tail or "”" in tail or '"' in tail:
        return True
    if CONCRETE_ENDING_ACTION_RE.search(tail) and any(word in tail for word in CONCRETE_ENDING_WORDS):
        return True
    return False


def _transition_warning(text: str, context: dict[str, Any]) -> str:
    contract = context.get("chapter_transition_contract")
    if not isinstance(contract, dict) or not contract:
        return ""
    anchor = str(contract.get("must_use_concrete_anchor") or "").strip()
    if not anchor:
        return ""
    first = re.split(r"\n\s*\n", text.strip(), maxsplit=1)[0][:360]
    tokens = _anchor_tokens(anchor)
    if tokens and not any(token in first for token in tokens):
        return "开篇可能没有接住上一章接力棒中的具体锚点。"
    return ""


def _opening_contract_problem(text: str, context: dict[str, Any]) -> str:
    detail = _outline_detail(context)
    first = first_paragraph(text, max_chars=360)
    if not first or not detail:
        return ""

    forbidden = " ".join(
        str(value or "")
        for value in [
            detail.get("forbidden_opening"),
            (context.get("chapter_transition_contract") or {}).get("forbidden_opening")
            if isinstance(context.get("chapter_transition_contract"), dict)
            else "",
        ]
    )
    violation = _forbidden_opening_violation(first, forbidden)
    if violation:
        return violation

    debt = str(detail.get("continuity_debt") or detail.get("previous_anchor") or "").strip()
    if debt and not _text_mentions_anchor(first, debt):
        return "前 300 字没有处理章节任务单中的承接债，容易让上下章断裂。"

    trigger = str(detail.get("opening_trigger") or "").strip()
    if trigger and not _text_mentions_anchor(first, trigger) and not _has_first_screen_hook(first):
        return "前 300 字没有兑现章节任务单中的开头触发事件。"

    expected_mode = str(detail.get("opening_mode") or "").strip()
    actual_mode = detect_opening_mode(first)
    if expected_mode and expected_mode in OPENING_MODE_VALUES and actual_mode != expected_mode:
        if expected_mode not in {"其他"}:
            if actual_mode not in OPENING_MODE_COMPATIBLE.get(expected_mode, set()):
                return f"章首开头方式偏离任务单：要求“{expected_mode}”，实际更像“{actual_mode}”。"

    recent_modes = [
        str(item.get("opening_mode") or "").strip()
        for item in context.get("recent_chapter_openings") or []
        if isinstance(item, dict) and str(item.get("opening_mode") or "").strip()
    ]
    if actual_mode != "其他" and len(recent_modes) >= 2 and all(mode == actual_mode for mode in recent_modes[-2:]):
        return f"章首开头方式连续重复为“{actual_mode}”，需要换一种第一屏策略。"

    return ""


def _outline_detail(context: dict[str, Any]) -> dict[str, Any]:
    chapter = context.get("chapter")
    if not isinstance(chapter, dict):
        return {}
    detail = chapter.get("outline_detail")
    return detail if isinstance(detail, dict) else {}


def _forbidden_opening_violation(first: str, forbidden: str) -> str:
    if not forbidden.strip():
        return ""
    compact = re.sub(r"\s+", "", first[:180])
    for keyword in FORBIDDEN_OPENING_KEYWORDS:
        if keyword in forbidden and keyword in compact:
            return f"章首违反任务单禁用开头：出现“{keyword}”。"
    if "时间" in forbidden and opening_pattern_flags(first):
        if any(flag in opening_pattern_flags(first) for flag in ["时间/时辰", "古装氛围词"]):
            return "章首违反任务单禁用开头：使用了时间或时辰式切入。"
    if "天气" in forbidden or "环境" in forbidden:
        if any(flag in opening_pattern_flags(first) for flag in ["天气/环境", "古装氛围词"]):
            return "章首违反任务单禁用开头：使用了天气或环境氛围切入。"
    return ""


def _text_mentions_anchor(text: str, anchor: str) -> bool:
    tokens = _anchor_tokens(anchor)
    if not tokens:
        return False
    if any(token in text for token in tokens[:6]):
        return True
    anchor_keywords = [word for word in ANCHOR_KEYWORDS if word in anchor]
    if anchor_keywords and any(word in text for word in anchor_keywords):
        return True
    return False


def _copied_outline_opening_warning(text: str, context: dict[str, Any]) -> str:
    first = first_paragraph(text, max_chars=120)
    if not opening_pattern_flags(first):
        return ""
    chapter = context.get("chapter")
    if not isinstance(chapter, dict):
        return ""
    detail = chapter.get("outline_detail")
    if not isinstance(detail, dict):
        detail = {}
    candidates = [
        detail.get("story_time"),
        detail.get("outline"),
        chapter.get("outline"),
    ]
    first_sig = _opening_signature(first)
    for candidate in candidates:
        candidate_text = str(candidate or "").strip()
        if not candidate_text:
            continue
        candidate_sig = _opening_signature(candidate_text)
        if candidate_sig and (
            first_sig.startswith(candidate_sig[:18])
            or candidate_sig.startswith(first_sig[:18])
            or SequenceMatcher(None, first_sig[:60], candidate_sig[:60]).ratio() >= 0.72
        ):
            return "正文开头疑似照抄细纲或 story_time 的时间地点说明；请改成有叙事钩子的第一屏，让时间、地点、动作或环境带出问题、压力、异常、威胁、选择或反证。"
    return ""


def _opening_signature(text: str) -> str:
    first = first_paragraph(text, max_chars=120)
    first_sentence = re.split(r"[。！？!?]\s*", first, maxsplit=1)[0]
    return _signature(first_sentence)


def _anchor_tokens(anchor: str) -> list[str]:
    chunks = re.split(r"[，,。！？；;：:\s、]+", anchor)
    tokens = [chunk.strip("“”\"'") for chunk in chunks if 2 <= len(chunk.strip("“”\"'")) <= 16]
    return tokens[:5]


def _history_enabled(context: dict[str, Any]) -> bool:
    specialist = context.get("history_specialist")
    return isinstance(specialist, dict) and bool(specialist.get("enabled"))


def _hit_labels(hits: list[dict[str, int | str]]) -> list[str]:
    labels = []
    for item in hits:
        phrase = str(item.get("phrase") or "").strip()
        count = item.get("count")
        if phrase:
            labels.append(f"{phrase}×{count}")
    return labels


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _int_or_none(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _signature(text: str) -> str:
    normalized = re.sub(r"\s+", "", text)
    normalized = re.sub(r"第\s*\d+\s*章", "第N章", normalized)
    normalized = re.sub(r"[A-Z]-\d+", "X-N", normalized)
    normalized = re.sub(r"\d+", "N", normalized)
    return normalized
