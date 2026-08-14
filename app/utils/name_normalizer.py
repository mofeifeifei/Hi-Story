from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


ROLE_LABEL_PATTERN = r"主角|配角|反派|男主|女主|男配|女配|主人公|人物|角色|待补充|protagonist|supporting|villain"

_CHARACTER_NAME_BAD_STARTS = ("未", "只", "由", "通过", "其中", "全程", "决定", "继续", "首次", "仅", "不出场")
_CHARACTER_NAME_BAD_MARKERS = ("未直接", "口述", "转述", "提及", "出场", "出现", "呈现", "存在", "示意", "签名", "动作", "威胁", "同行")
_COMMON_SURNAMES = set("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵汪祁毛禹狄米贝明臧计伏成戴宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林钟徐邱骆高夏蔡田樊胡凌霍虞万支柯管卢莫经房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔吉龚程嵇邢裴陆荣翁荀羊甄曲封储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍桑桂濮牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公")
_PERSON_ROLE_SUFFIXES = (
    "官", "吏", "卒", "兵", "将", "仆", "仆役", "仆从", "亲随", "侍女", "仆妇", "老者",
    "掌柜", "书手", "书吏", "师爷", "幕僚", "管家", "信使", "传令兵", "押班", "押衙",
    "主事", "堂官", "郎中", "虞侯", "统制", "驿丞", "巡检", "仓吏", "副将", "内侍",
    "掾吏", "掾", "曹掾", "官员", "文官", "司使", "承旨", "都承旨", "知州", "汉子", "管事",
    "流民", "船工", "仆役", "火头军", "军", "亲随二人", "仆役若干",
)
_DISCOVERED_NAME_BAD_STARTS = ("在", "以", "从", "被", "将", "但", "后", "为", "对", "用", "持", "已", "正", "无")
_DISCOVERED_NAME_BAD_MARKERS = (
    "日期", "时间", "今日", "昨日", "明日", "今晨", "入夜", "午后", "清晨", "章尾", "三日后",
    "主持", "交出", "接收", "回报", "报告", "确认", "完成", "处理", "整理", "起草", "誊正", "核验",
    "目击", "展示", "提出", "写下", "收到", "携带", "带回", "留下", "进行", "开始", "结束",
    "交谈", "对话", "交锋", "摊牌", "传唤", "称病", "回府", "换回", "未换", "照面", "系统", "预读", "武器",
    "文书", "底册", "录白", "副本", "原单", "条款", "便条", "火把", "鱼符", "信筒", "封卷",
    "草案", "移文", "物证", "墨迹", "袖袋", "书房", "灶房", "值房", "签押房", "政事堂", "便笺", "公服",
)


def normalize_character_name(value: Any) -> str:
    name = str(value or "").strip()
    if not name:
        return ""
    name = re.sub(r"[（(【\[].*?[）)】\]]", "", name)
    name = re.sub(rf"^\s*(?:{ROLE_LABEL_PATTERN})\s*[:：\-—·、\s]+", "", name, flags=re.IGNORECASE)
    name = re.sub(rf"[:：\-—·、\s]+(?:{ROLE_LABEL_PATTERN})\s*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", "", name)
    return name.strip("：:，,。；;、-—·")


def is_valid_character_name(value: Any) -> bool:
    name = normalize_character_name(value)
    if not name or len(name) > 12:
        return False
    if any(mark in name for mark in ("/", "、", "，", "；", "(", ")", "（", "）", "[", "]", "【", "】")):
        return False
    if name.startswith(_CHARACTER_NAME_BAD_STARTS):
        return False
    if any(mark in name for mark in _CHARACTER_NAME_BAD_MARKERS):
        return False
    if name in {"主角", "配角", "反派", "男主", "女主", "人物", "角色", "待补充", "众人", "证人", "未知人物"}:
        return False
    return True


def is_valid_discovered_character_name(value: Any) -> bool:
    """Conservative validator for names extracted automatically from chapter outlines."""
    name = normalize_character_name(value)
    if not is_valid_character_name(name):
        return False
    if any(mark in name for mark in ('"', "'", "“", "”", "‘", "’")):
        return False
    if name.startswith(_DISCOVERED_NAME_BAD_STARTS):
        return False
    if any(marker in name for marker in _DISCOVERED_NAME_BAD_MARKERS):
        return False
    if name in {"一名", "另一名", "众臣", "主战派", "主视角", "技术官僚", "火把", "鱼符", "副本", "后", "不", "侦测"}:
        return False
    if any(name.endswith(suffix) for suffix in _PERSON_ROLE_SUFFIXES):
        return True
    if 2 <= len(name) <= 4 and (name[0] in _COMMON_SURNAMES or name.startswith(("老", "小"))):
        return True
    named_role_prefixes = ("侍女", "仆从", "老仆")
    if name.startswith(named_role_prefixes) and 3 <= len(name) <= 7:
        return True
    office_role_prefixes = ("三司使", "书铺", "皇城司", "枢密院", "转运司", "韩世忠副将")
    if name.startswith(office_role_prefixes) and any(char in _COMMON_SURNAMES for char in name[-3:]):
        return True
    return False


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
