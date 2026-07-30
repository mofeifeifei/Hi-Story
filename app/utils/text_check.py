from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import re
from typing import Any, Iterable


HARD_TEMPLATE_BLACKLIST = [
    "重生归来",
    "系统觉醒",
    "全网震惊",
    "她冷笑一声",
    "他冷笑一声",
    "三年之期已到",
    "恐怖如斯",
    "所有人都愣住了",
    "你可知我是谁",
    "前所未有的震撼",
    "命运的齿轮开始转动",
    "不容置疑的力量",
    "由此可见",
    "综上所述",
    "前途无量",
    "未来可期",
    "新的篇章",
]
DEFAULT_TEMPLATE_BLACKLIST = HARD_TEMPLATE_BLACKLIST

ENDING_TEMPLATE_PHRASES = [
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
]

DENSITY_SENSITIVE_PHRASES = [
    "不易察觉",
    "眼中闪过",
    "眼底闪过",
    "嘴角微扬",
    "嘴角勾起",
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
    "与此同时",
]

DEFAULT_TEMPLATE_PATTERNS: list[tuple[str, str]] = [
    ("对照判断句式-转折型", r"不是[^，。！？\n]{1,24}[，,]\s*而是[^，。！？\n]{1,40}"),
    ("对照判断句式-逗号判断型", r"不是[^，。！？\n—-]{1,36}(?:[，,]|——|—|--)\s*(?!而)是[^，。！？\n]{1,50}"),
    ("对照判断句式-破折号型", r"不是[^。！？\n]{1,48}(?:——|—|--)[^。！？\n]{1,60}"),
    ("对照判断句式-让步型", r"不是[^，。！？\n]{1,36}[，,]?\s*却[^，。！？\n]{1,50}"),
    ("对照判断句式-短句判断型", r"不是[^。！？\n]{1,24}。\s*是[^。！？\n]{1,30}"),
    ("对照判断句式-连续堆叠型", r"不是[^，。！？\n]{1,16}[，,]\s*不是[^，。！？\n]{1,16}[，,]\s*而是"),
    ("对照判断句式-连续重复型", r"不是[^。！？\n]{0,80}不是[^。！？\n]{0,80}"),
    ("万能带着状语", r"[，,]\s*带着[^，。！？\n]{1,24}"),
    ("万能声音状语模板", r"声音不大[，,]\s*却[^。！？\n]{1,40}"),
    ("章末预告式空悬念", r"不?知道的是[^。！？\n]{1,40}(风暴|危险|真相|阴谋|开始)"),
    ("章末总结顿悟", r"(终于明白|这才意识到|这一刻[^。！？\n]{0,20}明白)"),
    ("眼神闪动模板", r"(眼中|眼底|眸中)[^。！？\n]{0,10}闪过[^。！？\n]{0,12}(一丝|一抹|几分)"),
    ("嘴角弧度模板", r"嘴角[^。！？\n]{0,8}(勾起|扬起)[^。！？\n]{0,12}(一抹|一丝)"),
]

DENSITY_SENSITIVE_LABELS = {
    "不易察觉": "含糊感知词",
    "眼中闪过": "眼神闪动模板",
    "眼底闪过": "眼神闪动模板",
    "嘴角微扬": "嘴角弧度模板",
    "嘴角勾起": "嘴角弧度模板",
    "嘴角勾起一抹": "嘴角弧度模板",
    "心中涌起": "心绪涌动模板",
    "心头一震": "心绪震动模板",
    "心中暗道": "内心独白模板",
    "深吸一口气": "泛化动作模板",
    "映入眼帘": "镜头套话",
    "不由自主": "泛化反应词",
    "不禁": "泛化反应词",
    "仿佛": "泛化比喻词",
    "宛若": "泛化比喻词",
    "犹如": "泛化比喻词",
    "与此同时": "机械转场词",
}

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

ENDING_ANCHOR_GROUPS = {
    "证据/文书": [
        "证据",
        "线索",
        "账册",
        "录簿",
        "抄本",
        "册页",
        "案卷",
        "牍",
        "文书",
        "移文",
        "批文",
        "封筒",
        "便笺",
        "纸条",
        "条记",
        "拓片",
        "原单",
        "残件",
        "保甲册",
        "奏疏",
        "草稿",
    ],
    "物件状态": [
        "鱼符",
        "蜡丸",
        "蜡封",
        "铜镇尺",
        "镇尺",
        "鹅卵石",
        "钥匙",
        "令牌",
        "刀",
        "匕首",
        "箭杆",
        "门闩",
        "窗扇",
        "封条",
        "茶盏",
        "木疤",
        "疤结",
    ],
    "威胁抵达": [
        "脚步",
        "靴底",
        "巡兵",
        "追兵",
        "暗梢",
        "皇城司",
        "内侍",
        "书吏",
        "敲门",
        "逼近",
        "搜查",
        "盘查",
        "召见",
        "传旨",
    ],
    "关系压力": ["王氏", "夫人", "赵构", "官家", "万俟卨", "冯益", "龚茂良", "陈四", "摊牌", "质问", "审视", "决定"],
    "行动中断": ["停住", "停下", "回头", "转身", "钻进", "推开", "合上", "塞进", "压住", "握着", "站起", "走向", "跨过"],
    "时间/地点转换": ["鼓声", "梆子", "更夫", "午时", "申时", "夜色", "日光", "府门", "政事堂", "驿铺", "码头", "渡口"],
}

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
    "章尾",
    "结尾",
    "承接债",
    "开头方式",
    "开头触发",
    "表层锚点",
    "剧情发动方式",
    "句式形状",
    "第一眼",
    "语言专项修订",
    "破折号",
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
    "便条",
    "纸边",
    "墨迹",
    "草稿",
    "名单",
    "账册",
    "文书",
    "书信",
    "移文",
    "录簿",
    "抄本",
    "保甲册",
    "档房",
    "封条",
    "启封",
    "会验",
    "画押",
    "急报",
    "告假条",
    "名帖",
    "令牌",
    "钥匙",
    "铜镇尺",
    "镇尺",
    "鹅卵石",
    "角门",
    "门闩",
    "脚印",
    "脚步",
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
    "人物动作": {"物件", "对白", "异常", "后果", "反应", "命令", "缺席", "冲突", "时间压力", "环境异常"},
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

OPENING_SURFACE_ANCHORS: dict[str, list[str]] = {
    "时间声音": [
        "更鼓",
        "鼓声",
        "鼓楼",
        "梆子",
        "钟声",
        "铃声",
        "警报",
        "广播",
        "号角",
        "汽笛",
        "钟响",
        "铃响",
        "闹钟",
    ],
    "时间标记": [
        "卯时",
        "辰时",
        "巳时",
        "午时",
        "子时",
        "清晨",
        "黄昏",
        "入夜",
        "深夜",
        "黎明",
        "拂晓",
        "翌日",
        "次日",
    ],
    "天气光线": [
        "晨光",
        "日光",
        "阳光",
        "天光",
        "月色",
        "夜色",
        "雨声",
        "风声",
        "雪",
        "雾",
        "灯火",
        "烛火",
    ],
    "门窗出入": [
        "门",
        "窗",
        "轿帘",
        "帘",
        "廊",
        "门槛",
        "门闩",
        "舱门",
        "车门",
        "电梯门",
        "舱口",
    ],
    "文书消息": [
        "便条",
        "纸条",
        "信",
        "文书",
        "账册",
        "录簿",
        "抄本",
        "案卷",
        "奏疏",
        "草稿",
        "短信",
        "消息",
        "屏幕",
        "终端",
    ],
    "物件触感": [
        "硌",
        "压",
        "捏",
        "握",
        "攥",
        "木屑",
        "石",
        "钥匙",
        "令牌",
        "刀",
        "杯",
        "茶盏",
        "镇尺",
        "戒指",
        "项链",
    ],
    "普通人物动作": [
        "抬起头",
        "低头",
        "伸手",
        "站起",
        "坐下",
        "走进",
        "走出",
        "看了看",
        "看着",
        "拿起",
        "放下",
        "推开",
    ],
    "内心判断": [
        "意识到",
        "明白",
        "知道",
        "觉得",
        "想起",
        "心里",
        "念头",
        "判断",
        "他知道",
        "她知道",
    ],
}

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
DASH_RE = re.compile(r"——|--|—")
BUSHI_CONTRAST_RE = re.compile(
    r"不是[^。！？\n]{1,90}(?:而是|[，,]\s*是|。\s*是|(?:——|—|--)\s*是|却|不是)"
)


def first_paragraph(text: str, *, max_chars: int = 220) -> str:
    for part in re.split(r"\n\s*\n|\r\n\s*\r\n", str(text or "").strip()):
        compact = part.strip()
        if compact:
            return compact[:max_chars]
    return ""


def first_screen(text: str, *, max_chars: int = 520) -> str:
    parts: list[str] = []
    total = 0
    for part in re.split(r"\n\s*\n|\r\n\s*\r\n", str(text or "").strip()):
        compact = re.sub(r"\s+", " ", part.strip())
        if not compact:
            continue
        remaining = max_chars - total
        if remaining <= 0:
            break
        parts.append(compact[:remaining])
        total += len(parts[-1])
        if total >= max_chars:
            break
    return "\n".join(parts)


def last_screen(text: str, *, max_chars: int = 420) -> str:
    parts: list[str] = []
    total = 0
    paragraphs = [
        re.sub(r"\s+", " ", part.strip())
        for part in re.split(r"\n\s*\n|\r\n\s*\r\n", str(text or "").strip())
        if part.strip()
    ]
    for part in reversed(paragraphs):
        remaining = max_chars - total
        if remaining <= 0:
            break
        if len(part) > remaining and parts:
            parts.append(part[-remaining:])
            break
        parts.append(part[-remaining:])
        total += len(parts[-1])
        if total >= max_chars:
            break
    return "\n".join(reversed(parts))


def paragraph_structure_warnings(text: str) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n|\r\n\s*\r\n", str(text or "")) if part.strip()]
    visible_chars = _visible_length(str(text or ""))
    if not paragraphs or visible_chars < 1200:
        return []
    lengths = [len(re.sub(r"\s+", "", part)) for part in paragraphs]
    warnings: list[str] = []
    if len(paragraphs) < 8:
        warnings.append("正文段落过少，移动阅读时可能形成大段堆叠；请按动作、信息或情绪转折自然分段。")
    long_count = sum(1 for length in lengths if length > 320)
    if long_count >= 3 and long_count / len(lengths) >= 0.2:
        warnings.append("正文存在较多超长段落；保留必要说明，但应在行动、对白或信息变化处断开。")
    short_count = sum(1 for length in lengths if length <= 12)
    if len(paragraphs) >= 20 and short_count / len(lengths) >= 0.6:
        warnings.append("短段比例过高，可能削弱场景连贯性；请合并没有独立动作、信息或情绪功能的碎段。")
    return warnings


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


def opening_signature(text: str) -> dict[str, Any]:
    first = first_paragraph(text, max_chars=360)
    screen = first_screen(text, max_chars=560)
    mode = detect_opening_mode(first or screen)
    surface_anchors = _opening_surface_anchors(screen or first)
    syntax_shape = _opening_syntax_shape(first)
    return {
        "opening_engine": mode,
        "surface_anchors": surface_anchors,
        "primary_surface_anchor": surface_anchors[0] if surface_anchors else "其他",
        "subject_type": _opening_subject_type(first),
        "syntax_shape": syntax_shape,
    }


def rhetorical_pattern_flags(text: str, *, opening: bool = False) -> list[str]:
    sample = first_screen(text, max_chars=360) if opening else str(text or "")
    flags: list[str] = []
    if _has_bushi_contrast(sample):
        flags.append("对照判断句式")
    dash_count = _dash_count(sample)
    if opening and dash_count:
        first_sentence = re.split(r"[。！？!?]\s*", sample, maxsplit=1)[0].strip()
        sample_without_dialogue = _strip_dialogue_text(sample)
        first_sentence_without_dialogue = _strip_dialogue_text(first_sentence)
        if _dash_count(sample_without_dialogue) >= 2 or _dash_count(first_sentence_without_dialogue) >= 1:
            flags.append("破折号解释式开头")
    elif not opening and _dash_density_warning(sample):
        flags.append("破折号密度偏高")
    return _dedupe(flags)


def style_risk_profile(text: str) -> dict[str, Any]:
    content = str(text or "")
    opening = first_screen(content, max_chars=320)
    template_hits = detect_template_phrases(content)
    bushi_hits = [
        hit
        for hit in template_hits
        if "对照判断句式" in str(hit.get("phrase") or "")
    ]
    dash_total = _dash_count(content)
    dash_opening = _dash_count(_strip_dialogue_text(opening))
    return {
        "visible_chars": _visible_length(content),
        "dash_total": dash_total,
        "dash_opening": dash_opening,
        "bushi_contrast_total": sum(int(hit.get("count") or 0) for hit in bushi_hits),
        "template_hit_total": sum(int(hit.get("count") or 0) for hit in template_hits),
        "opening_flags": rhetorical_pattern_flags(content, opening=True),
        "rhetorical_flags": rhetorical_pattern_flags(content, opening=False),
    }


def style_regression_warnings(before: str, after: str) -> list[str]:
    old = style_risk_profile(before)
    new = style_risk_profile(after)
    warnings: list[str] = []
    if int(new["dash_opening"]) > int(old["dash_opening"]):
        warnings.append(
            f"修订稿章首破折号从 {old['dash_opening']} 处增加到 {new['dash_opening']} 处。"
        )
    if int(new["dash_total"]) >= max(3, int(old["dash_total"]) + 3):
        warnings.append(
            f"修订稿破折号从 {old['dash_total']} 处增加到 {new['dash_total']} 处。"
        )
    if int(new["bushi_contrast_total"]) > int(old["bushi_contrast_total"]):
        warnings.append(
            f"修订稿对照判断句式从 {old['bushi_contrast_total']} 处增加到 {new['bushi_contrast_total']} 处。"
        )
    old_opening = set(old.get("opening_flags") or [])
    new_opening = set(new.get("opening_flags") or [])
    added_opening = sorted(new_opening - old_opening)
    if added_opening:
        warnings.append("修订稿章首新增高风险句式：" + "、".join(added_opening) + "。")
    return warnings


def style_guard_warnings(text: str) -> list[str]:
    profile = style_risk_profile(text)
    warnings: list[str] = []
    if int(profile["dash_opening"]) >= 1:
        warnings.append("语言专项修订：章首前 300 字出现破折号解释式表达。")
    dash_total = int(profile["dash_total"])
    if dash_total >= max(_dash_density_limit(str(text or "")), 3):
        warnings.append(f"语言专项修订：正文破折号过多（约 {dash_total} 处）。")
    contrast_total = int(profile["bushi_contrast_total"])
    if contrast_total >= 3:
        warnings.append(f"语言专项修订：正文对照判断句式偏多（约 {contrast_total} 处）。")
    elif "对照判断句式" in set(profile.get("opening_flags") or []):
        warnings.append("语言专项修订：章首使用对照判断句式。")
    return _dedupe(warnings)


def ending_signature(text: str) -> dict[str, Any]:
    tail = last_screen(text)
    compact_tail = re.sub(r"\s+", "", tail)
    anchor_type = _ending_anchor_type(compact_tail)
    anchors = _ending_concrete_anchors(compact_tail)
    contrast_count = 1 if _has_bushi_contrast(compact_tail) else 0
    dash_count = _dash_count(_strip_dialogue_text(compact_tail))
    abstract_forecast = bool(
        any(phrase in compact_tail for phrase in EMPTY_ENDING_PHRASES)
        or (
            any(word in compact_tail for word in ABSTRACT_ENDING_WORDS)
            and not _has_concrete_ending_anchor(compact_tail)
        )
    )
    return {
        "tail": tail,
        "anchor_type": anchor_type,
        "concrete_anchors": anchors,
        "rhetorical_flags": rhetorical_pattern_flags(compact_tail, opening=False),
        "dash_count": dash_count,
        "contrast_count": contrast_count,
        "abstract_forecast": abstract_forecast,
    }


def chapter_ending_warning(text: str, context: dict[str, Any]) -> str:
    signature = ending_signature(text)
    anchor_type = str(signature.get("anchor_type") or "")
    anchors = [str(item) for item in signature.get("concrete_anchors") or [] if str(item).strip()]
    if signature.get("abstract_forecast") or (anchor_type == "抽象/氛围" and not anchors):
        return "章尾落在抽象预告或氛围判断上，缺少下一章第一段可直接承接的外部锚点。"

    recent = context.get("recent_chapter_endings")
    if not isinstance(recent, list):
        recent = []
    recent = [item for item in recent[-3:] if isinstance(item, dict)]
    if not recent:
        return ""

    recent_types = [str(item.get("anchor_type") or "") for item in recent if item.get("anchor_type")]
    if anchor_type and anchor_type != "其他" and recent_types.count(anchor_type) >= 2:
        return f"章尾落点连续重复为“{anchor_type}”，容易形成同款收束；请换成不同外部锚点或下一章动作。"

    if int(signature.get("contrast_count") or 0) and any(int(item.get("contrast_count") or 0) for item in recent):
        return "章尾连续使用对照判断句式，容易形成AI味；请改成动作、对白、物件状态或证据变化收束。"

    if int(signature.get("dash_count") or 0) and any(int(item.get("dash_count") or 0) for item in recent):
        return "章尾连续使用破折号解释或转折，容易形成模板化悬念；请用自然断句、动作推进或具体物件状态收束。"

    recent_anchors = [
        str(anchor)
        for item in recent
        for anchor in (item.get("concrete_anchors") or [])
        if str(anchor).strip()
    ]
    repeated_anchors = [anchor for anchor in anchors if recent_anchors.count(anchor) >= 2]
    if repeated_anchors:
        return "章尾连续围绕同一类锚点收束：" + "、".join(repeated_anchors[:4]) + "。请改换章末外部锚点。"
    return ""


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


def _opening_surface_anchors(text: str) -> list[str]:
    sample = first_screen(text, max_chars=360)
    anchors: list[str] = []
    for label, words in OPENING_SURFACE_ANCHORS.items():
        if any(word in sample for word in words):
            anchors.append(label)
    if OPENING_TIME_RE.search(sample[:120]) and "时间标记" not in anchors:
        anchors.append("时间标记")
    if (OPENING_ENV_RE.search(sample[:120]) or OPENING_ENV_NEAR_RE.search(sample[:140])) and "天气光线" not in anchors:
        anchors.append("天气光线")
    if (OPENING_PLACE_RE.search(sample[:120]) or OPENING_PLACE_NEAR_RE.search(sample[:140])) and "地点陈列" not in anchors:
        anchors.append("地点陈列")
    if "“" in sample[:160] or '"' in sample[:160]:
        anchors.append("对白")
    if FIRST_SCREEN_HOOK_RE.search(sample[:260]):
        anchors.append("问题/威胁/证据")
    return _dedupe(anchors)[:5]


def _opening_subject_type(first: str) -> str:
    text = first_paragraph(first, max_chars=180)
    if not text:
        return "其他"
    if text.startswith(("“", "\"")):
        return "对白"
    if any(word in text[:120] for word in ["信", "纸", "便条", "账册", "录簿", "钥匙", "令牌", "门", "窗", "杯", "石", "刀", "屏幕", "终端"]):
        return "物件"
    if any(word in text[:120] for word in ["不见", "没有来", "空无一人", "缺席", "无人"]):
        return "缺席者"
    if any(word in text[:120] for word in ["众人", "人群", "士卒", "巡兵", "同僚", "宾客", "队伍"]):
        return "群体"
    if re.match(r"^\s*[\u4e00-\u9fff]{1,4}(?:把|从|在|向|没有|低头|抬头|伸手|走|站|坐|跨|推|掀)", text):
        return "人物"
    return "场景/其他"


def _opening_syntax_shape(first: str) -> str:
    sentence = re.split(r"[。！？!?]\s*", first_paragraph(first, max_chars=180), maxsplit=1)[0].strip()
    if not sentence:
        return "其他"
    if DASH_RE.search(sentence):
        return "破折号解释"
    if _has_bushi_contrast(sentence):
        return "对照判断"
    if OPENING_TIME_RE.search(sentence):
        return "时间起句"
    if OPENING_PLACE_RE.search(sentence) or OPENING_PLACE_NEAR_RE.search(sentence[:90]):
        return "地点起句"
    if OPENING_ENV_RE.search(sentence) or OPENING_ENV_NEAR_RE.search(sentence[:90]):
        return "环境起句"
    if sentence.startswith(("“", "\"")):
        return "对白起句"
    if any(word in sentence[:80] for word in OPENING_SURFACE_ANCHORS.get("时间声音", [])):
        return "声音起句"
    if any(word in sentence[:100] for word in OPENING_SURFACE_ANCHORS.get("文书消息", [])):
        return "物件/消息起句"
    if re.match(r"^\s*[\u4e00-\u9fff]{1,4}(?:把|从|在|向|没有|低头|抬头|伸手|走|站|坐|跨|推|掀)", sentence):
        return "人物动作起句"
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


def _has_bushi_contrast(text: str) -> bool:
    return bool(BUSHI_CONTRAST_RE.search(str(text or "")))


def _dash_count(text: str) -> int:
    return len(DASH_RE.findall(str(text or "")))


def _dash_density_limit(text: str) -> int:
    visible = _visible_length(str(text or ""))
    if visible <= 1200:
        return 2
    if visible <= 5000:
        return 3
    return 4


def _dash_density_warning(text: str) -> str:
    count = _dash_count(text)
    if count < _dash_density_limit(text):
        return ""
    return f"语言专项修订：正文破折号使用偏多（约 {count} 处），容易形成解释式机器味；请只保留真正的对白打断、突发打断或关键揭示，其余改成动作承接、短句、对白反应、物件状态或证据差异。"


def _dash_density_blocker(text: str) -> str:
    count = _dash_count(text)
    limit = _dash_density_limit(text)
    first = first_screen(text, max_chars=320)
    first_without_dialogue = _strip_dialogue_text(first)
    if _dash_count(first_without_dialogue) >= 1:
        return "章首前 300 字使用破折号，容易形成解释式开头；除对白被打断或突发打断外，必须改成动作、对白、物件状态或证据差异承接。"
    if count > max(limit, 3):
        return f"正文破折号过多（约 {count} 处），超过正式稿阈值；必须先做语言专项修订，压到 1 到 2 处附近。"
    return ""


def _density_phrase_limit(phrase: str, text: str) -> int:
    visible = _visible_length(str(text or ""))
    if phrase in {"仿佛", "不禁", "与此同时"}:
        return 4 if visible >= 3000 else 3
    if visible >= 4500:
        return 3
    return 2


def _strip_dialogue_text(text: str) -> str:
    stripped = re.sub(r"“[^”]*”", "", str(text or ""))
    stripped = re.sub(r"“[^”]*$", "", stripped)
    stripped = re.sub(r'"[^"]*"', "", stripped)
    stripped = re.sub(r'"[^"]*$', "", stripped)
    return stripped


def _opening_rhetorical_warning(text: str, context: dict[str, Any]) -> str:
    first = first_paragraph(text, max_chars=360)
    if not first:
        return ""
    flags = rhetorical_pattern_flags(first, opening=True)
    if not flags:
        return ""
    recent = context.get("recent_chapter_openings")
    if not isinstance(recent, list):
        recent = []
    recent_flags: list[str] = []
    for item in recent[-3:]:
        if isinstance(item, dict):
            recent_flags.extend(str(flag) for flag in item.get("rhetorical_flags") or [])
    repeated = sorted(set(flags).intersection(recent_flags))
    if "对照判断句式" in flags:
        prefix = "章首连续使用" if "对照判断句式" in repeated else "章首使用"
        return (
            prefix
            + "对照判断句式，容易形成AI味；请保留上一章事实锚点，改成具体动作、对白、证据、物件变化或场面反应。"
        )
    if "破折号解释式开头" in flags:
        if "破折号解释式开头" in repeated:
            return "章首连续使用破折号解释式开头，AI味明显；请不用破折号补充说明，直接承接上一章的动作、对白、物件、证据、威胁或后果。"
        if _dash_count(first) >= 2:
            return "章首破折号使用偏多，容易把开篇写成解释/反转模板；请减少破折号，用动作、对白或证据自然承接上一章。"
    return ""


def _first_screen_hook_warning(text: str) -> str:
    first = first_paragraph(text, max_chars=220)
    screen = first_screen(text, max_chars=520)
    if not screen:
        return ""
    if _has_first_screen_hook(screen):
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
    signature_warning = _opening_signature_warning(text, context)
    if signature_warning:
        return signature_warning
    rhetorical_warning = _opening_rhetorical_warning(text, context)
    if rhetorical_warning:
        return rhetorical_warning
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


def _opening_signature_warning(text: str, context: dict[str, Any]) -> str:
    current = opening_signature(text)
    recent_raw = context.get("recent_chapter_openings")
    if not isinstance(recent_raw, list):
        recent_raw = []
    recent: list[dict[str, Any]] = []
    for item in recent_raw[-5:]:
        if not isinstance(item, dict):
            continue
        sig = item.get("opening_signature")
        if isinstance(sig, dict):
            recent.append(sig)
    if not recent:
        return ""

    current_anchor = str(current.get("primary_surface_anchor") or "")
    if current_anchor and current_anchor not in {"其他", "问题/威胁/证据", "对白"}:
        recent_anchors = [
            str(sig.get("primary_surface_anchor") or "")
            for sig in recent
            if str(sig.get("primary_surface_anchor") or "")
        ]
        if recent_anchors.count(current_anchor) >= 2:
            return (
                f"章首表层锚点连续偏向“{current_anchor}”，容易形成同款开场；"
                "请把它降为背景，改由证据、对白、威胁、关系冲突、选择或现场异常发动第一屏。"
            )

    engine = str(current.get("opening_engine") or "")
    recent_engines = [
        str(sig.get("opening_engine") or "")
        for sig in recent[-3:]
        if str(sig.get("opening_engine") or "")
    ]
    if engine and engine != "其他" and recent_engines.count(engine) >= 2:
        return (
            f"章首剧情发动方式连续接近“{engine}”，需要换一种第一屏发动机；"
            "不要只替换词语，要换成不同的动作、对白、证据、威胁、关系压力或选择。"
        )

    shape = str(current.get("syntax_shape") or "")
    recent_shapes = [
        str(sig.get("syntax_shape") or "")
        for sig in recent[-4:]
        if str(sig.get("syntax_shape") or "")
    ]
    if shape and shape not in {"其他"} and recent_shapes.count(shape) >= 2:
        return f"章首句式形状连续接近“{shape}”，容易模板化；请换成不同句法和不同第一眼落点。"

    subject = str(current.get("subject_type") or "")
    recent_subjects = [
        str(sig.get("subject_type") or "")
        for sig in recent[-4:]
        if str(sig.get("subject_type") or "")
    ]
    if subject and subject == "人物" and recent_subjects.count(subject) >= 3:
        return "最近章首第一眼连续落在人物动作上，本章优先从物件、对白、缺席者、对手动作或现场异常切入。"
    return ""


def detect_template_phrases(
    text: str,
    blacklist: Iterable[str] = HARD_TEMPLATE_BLACKLIST,
) -> list[dict[str, int | str]]:
    hits: list[dict[str, int | str]] = []
    for phrase in blacklist:
        count = text.count(phrase)
        if count:
            hits.append(
                {
                    "phrase": DENSITY_SENSITIVE_LABELS.get(phrase, "密度慎用表达"),
                    "count": count,
                    "severity": "high",
                    "reason": "强套路或非小说化表达，建议避免。",
                }
            )
    for label, pattern in DEFAULT_TEMPLATE_PATTERNS:
        count = len(re.findall(pattern, text))
        if count:
            hits.append(
                {
                    "phrase": label,
                    "count": count,
                    "severity": "medium",
                    "reason": "结构性模板句，少量也容易显得机器味。",
                }
            )
    for phrase in DENSITY_SENSITIVE_PHRASES:
        count = text.count(phrase)
        if count >= _density_phrase_limit(phrase, text):
            hits.append(
                {
                    "phrase": phrase,
                    "count": count,
                    "severity": "low",
                    "reason": "普通词或常见动作重复偏多，建议减少密度而非绝对禁用。",
                }
            )
    dash_count = _dash_count(text)
    if dash_count >= _dash_density_limit(text):
        hits.append(
            {
                "phrase": "破折号高频使用",
                "count": dash_count,
                "severity": "medium",
                "reason": "破折号不是禁用，但高频用于解释或转折会形成机器味，需要语言专项修订。",
            }
        )
    return hits


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
        severities = {str(item.get("severity") or "") for item in template_hits if isinstance(item, dict)}
        if severities <= {"low"}:
            warnings.append("正文存在高频慎用词或标点密度风险。")
        else:
            warnings.append("正文命中模板句或机器味表达。")
        risk_flags.extend(_hit_labels(template_hits))
    dash_warning = _dash_density_warning(cleaned)
    if dash_warning:
        warnings.append(dash_warning)
    dash_blocker = _dash_density_blocker(cleaned)
    if dash_blocker:
        blockers.append(dash_blocker)
    style_warnings = style_guard_warnings(cleaned)
    for item in style_warnings:
        if "章首使用对照判断句式" in item or "对照判断句式偏多" in item:
            blockers.append(item)
        else:
            warnings.append(item)

    historical_hits: list[dict[str, int | str]] = []
    if _history_enabled(context):
        historical_hits = detect_historical_anachronisms(cleaned)
        if historical_hits:
            warnings.append("历史类作品中疑似出现现代词或时代违和词。")
            risk_flags.extend(_hit_labels(historical_hits))

    transition_warning = _transition_warning(cleaned, context)
    if transition_warning:
        warnings.append(transition_warning)

    scene_continuity_problem = _scene_continuity_problem(cleaned, context)
    if scene_continuity_problem:
        blockers.append(scene_continuity_problem)

    opening_contract_problem = _opening_contract_problem(cleaned, context)
    if opening_contract_problem:
        blockers.append(opening_contract_problem)

    opening_warning = chapter_opening_warning(cleaned, context)
    if opening_warning:
        if (
            opening_warning.startswith("章首连续使用")
            or "对照判断句式" in opening_warning
            or "章首表层锚点" in opening_warning
            or "章首剧情发动方式" in opening_warning
            or "章首句式形状" in opening_warning
            or "第一眼连续落在" in opening_warning
        ):
            blockers.append(opening_warning)
        else:
            warnings.append(opening_warning)

    ending_warning = chapter_ending_warning(cleaned, context)
    if ending_warning:
        warnings.append(ending_warning)
    warnings.extend(paragraph_structure_warnings(cleaned))

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
        "opening_signature": opening_signature(cleaned),
        "ending_signature": ending_signature(cleaned),
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
    hard_lines = [f"- {phrase}" for phrase in HARD_TEMPLATE_BLACKLIST]
    pattern_lines = [f"- {label}" for label, _ in DEFAULT_TEMPLATE_PATTERNS]
    return "\n".join(
        [
            "强禁套路：",
            *hard_lines,
            "慎用句式：",
            *pattern_lines,
            "章尾慎用：",
            "- 空泛预告、命运式旁白、顿悟式收束、泛化新篇章表达。",
            "密度慎用，可合理少量使用：",
            "- 万能状语、眼神闪动、嘴角弧度、心绪涌动、无功能轻动作、泛化比喻和过度连接词。",
            "原则：普通词可以合理使用，但不要在章首章尾、高频连续或相邻章节重复使用。",
        ]
    )


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


def _ending_anchor_type(tail: str) -> str:
    counts = {
        label: sum(1 for word in words if word in tail)
        for label, words in ENDING_ANCHOR_GROUPS.items()
    }
    best_label = ""
    best_count = 0
    for label, count in counts.items():
        if count > best_count:
            best_label = label
            best_count = count
    if best_label:
        return best_label
    if any(word in tail for word in ABSTRACT_ENDING_WORDS):
        return "抽象/氛围"
    return "其他"


def _ending_concrete_anchors(tail: str) -> list[str]:
    anchors: list[str] = []
    for words in ENDING_ANCHOR_GROUPS.values():
        anchors.extend(word for word in words if word in tail)
    anchors.extend(word for word in CONCRETE_ENDING_WORDS if word in tail)
    return _dedupe(anchors)[:8]


def _transition_warning(text: str, context: dict[str, Any]) -> str:
    contract = context.get("chapter_transition_contract")
    if not isinstance(contract, dict) or not contract:
        return ""
    anchor = str(contract.get("must_use_concrete_anchor") or "").strip()
    if not anchor:
        return ""
    first = first_screen(text, max_chars=520)
    if not _text_mentions_anchor(first, anchor):
        return "开篇可能没有接住上一章接力棒中的具体锚点。"
    return ""


def _scene_continuity_problem(text: str, context: dict[str, Any]) -> str:
    contract = context.get("chapter_transition_contract")
    if not isinstance(contract, dict) or not contract:
        return ""
    if bool(contract.get("allowed_shift")):
        return ""
    screen = first_screen(text, max_chars=560)
    if not screen:
        return ""
    last_visible = str(contract.get("last_visible_beat") or "").strip()
    required_next = str(contract.get("required_next_beat") or contract.get("required_first_paragraph") or "").strip()
    anchor_text = " ".join(part for part in [last_visible, required_next] if part)
    if anchor_text and not _text_mentions_anchor(screen, anchor_text):
        return "章首没有接住上一章最后可见画面，疑似重新开场；第一屏必须出现上一章留下的人、物、动作、证据、威胁或现场后果。"
    if _looks_like_protagonist_reset(screen, context):
        return "章首疑似使用“主角名+普通动作”重新开场；请改成上一章最后画面的下一拍动作或物件/对白/威胁承接。"
    return ""


def _opening_contract_problem(text: str, context: dict[str, Any]) -> str:
    detail = _outline_detail(context)
    first = first_paragraph(text, max_chars=220)
    screen = first_screen(text, max_chars=560)
    if not screen or not detail:
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
    violation = _forbidden_opening_violation(first, screen, forbidden)
    if violation:
        return violation

    debt = str(detail.get("continuity_debt") or detail.get("previous_anchor") or "").strip()
    if debt and not _text_mentions_anchor(screen, debt):
        return "前 300 字没有处理章节任务单中的承接债，容易让上下章断裂。"

    trigger = str(detail.get("opening_trigger") or "").strip()
    if trigger and not _text_mentions_anchor(screen, trigger) and not _has_first_screen_hook(screen):
        return "前 300 字没有兑现章节任务单中的开头触发事件。"

    expected_mode = str(detail.get("opening_mode") or "").strip()
    actual_mode = detect_opening_mode(screen)
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


def _forbidden_opening_violation(first: str, screen: str, forbidden: str) -> str:
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
        if any(flag in opening_pattern_flags(first) for flag in ["天气/环境", "古装氛围词"]) and not _has_first_screen_hook(screen):
            return "章首违反任务单禁用开头：使用了天气或环境氛围切入。"
    return ""


def _text_mentions_anchor(text: str, anchor: str) -> bool:
    tokens = _anchor_tokens(anchor)
    if tokens and any(token in text for token in tokens[:8]):
        return True
    anchor_keywords = [word for word in ANCHOR_KEYWORDS if word in anchor]
    if len(anchor_keywords) == 1 and anchor_keywords[0] in text:
        return True
    if len(anchor_keywords) >= 2 and sum(1 for word in anchor_keywords if word in text) >= 2:
        return True
    if _shared_chinese_terms(text, anchor) >= 2:
        return True
    return False


def _looks_like_protagonist_reset(first: str, context: dict[str, Any]) -> bool:
    first_sentence = re.split(r"[。！？!?]\s*", first_paragraph(first, max_chars=220), maxsplit=1)[0].strip()
    if not first_sentence:
        return False
    names = _protagonist_names(context)
    if not names:
        names = ["秦桧", "主角"]
    if not any(first_sentence.startswith(name) for name in names):
        return False
    if _has_first_screen_hook(first):
        return False
    if any(word in first_sentence[:120] for word in ["没有起身", "没有立刻", "停在", "递来", "接过", "拆开", "展开", "便条", "脚步", "门闩", "封条", "铜镇尺"]):
        return False
    reset_verbs = [
        "走到",
        "站在",
        "坐在",
        "看着",
        "望见",
        "睁眼",
        "抬头",
        "低头",
        "伸手",
        "用指尖",
        "在轿中",
        "从",
        "将",
        "把",
    ]
    return any(verb in first_sentence[:80] for verb in reset_verbs)


def _protagonist_names(context: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for item in context.get("characters") or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        name = str(item.get("name") or "").strip()
        if name and ("主角" in role or role.lower() == "protagonist"):
            result.append(name)
    return result[:3]


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
    tokens: list[str] = []
    for chunk in chunks:
        cleaned = chunk.strip("“”\"'（）()")
        if not cleaned:
            continue
        if 2 <= len(cleaned) <= 18:
            tokens.append(cleaned)
            continue
        tokens.extend(re.findall(r"[\u4e00-\u9fff]{2,6}(?:册|稿|条|纸|信|令|文|印|石|门|窗|鼓|声|影|官|吏|人|案|房|角|页|名|帖|录|簿|抄本|封条|便条)", cleaned))
    return _dedupe(tokens)[:10]


def _shared_chinese_terms(text: str, anchor: str) -> int:
    text_terms = set(re.findall(r"[\u4e00-\u9fff]{2,6}", str(text or "")))
    anchor_terms = {
        term
        for term in re.findall(r"[\u4e00-\u9fff]{2,6}", str(anchor or ""))
        if not _is_weak_anchor_term(term)
    }
    return len(text_terms.intersection(anchor_terms))


def _is_weak_anchor_term(term: str) -> bool:
    weak_terms = {
        "下一章",
        "第一句",
        "第一段",
        "必须",
        "接住",
        "承接",
        "画面",
        "立刻",
        "随后",
        "方向",
        "是否",
        "决定",
        "没有",
        "一个",
        "这一",
        "那个",
        "正是",
        "仍在",
        "尚未",
    }
    return term in weak_terms or len(term) <= 1


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
