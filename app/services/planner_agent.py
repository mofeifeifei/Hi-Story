from __future__ import annotations

from typing import Any

from app.core.contracts import (
    PLANNER_CHAPTER_OUTLINES_VALIDATOR,
    PLANNER_OUTLINE_VALIDATOR,
    PLANNER_WORK_PLAN_VALIDATOR,
    normalize_chapter_outlines,
    normalize_outline,
    normalize_work_plan,
)
from app.services.base_agent import BaseAgent
from app.utils.config import load_prompt
from app.utils.history import history_prompt_section, is_historical_inputs
from app.utils.json_parser import json_dumps


def _prompt_value(value: Any) -> str:
    if value in (None, "", 0):
        return "未填写"
    return str(value)


class PlannerAgent(BaseAgent):
    agent_name = "planner"
    prompt_file = "planner_prompt.md"

    def generate_work_plan(self, inputs: dict[str, Any]) -> dict[str, Any]:
        history_section = ""
        if is_historical_inputs(inputs):
            history_section = (
                "\n\n检测到这是历史类或古代类题材。请额外遵守以下历史专项约束，并生成 historical_profile：\n"
                f"{load_prompt('history_prompt.md')}\n"
            )
        user_prompt = (
            "请根据以下信息生成小说项目设定，输出供程序解析的合法 JSON。\n"
            f"作品名称：{_prompt_value(inputs.get('title'))}\n"
            f"一句话创意：{_prompt_value(inputs.get('idea'))}\n"
            f"题材：{_prompt_value(inputs.get('genre'))}\n"
            f"目标平台：{_prompt_value(inputs.get('platform'))}\n"
            f"目标字数：{_prompt_value(inputs.get('target_words'))}\n"
            f"写作风格：{_prompt_value(inputs.get('style'))}\n"
            f"禁用套路：{_prompt_value(inputs.get('forbidden_tropes'))}\n"
            f"主角偏好：{_prompt_value(inputs.get('protagonist_preference'))}\n"
            f"读者定位：{_prompt_value(inputs.get('reader_profile'))}\n\n"
            f"锁定设定：{_prompt_value(inputs.get('locked_facts'))}\n"
            f"其他写作控制：{_prompt_value(inputs.get('writing_controls'))}\n\n"
            f"{history_section}"
            "JSON 字段：book_bible, book_contract, title_candidates, summary, core_selling_points, target_readers, "
            "protagonist, supporting_characters, villains, world_rules, main_goal, first_volume_direction, historical_profile。"
            "book_contract 是轻量题材契约卡，只写短句，字段包含 genre_core, reader_promise, conflict_engine, chapter_payoff, opening_preference, avoid, language_texture。"
        )
        parsed = self.complete_json(
            user_prompt,
            validator=PLANNER_WORK_PLAN_VALIDATOR,
            default={},
            normalizer=normalize_work_plan,
            mock_hint={"task": "work_plan"},
        )
        return parsed

    def generate_outline(self, work_bundle: dict[str, Any]) -> dict[str, Any]:
        history_section = history_prompt_section(work_bundle, task="outline")
        user_prompt = (
            "请根据作品资料生成全书大纲和分卷大纲，输出供程序解析的合法 JSON。\n"
            "这不是宣传简介，要像真正能指导长篇连载的编辑部大纲。\n"
            "full_outline 要分成 4 到 8 个自然段，段落之间用换行分隔；必须包含：主线问题、阶段推进、人物关系变化、核心反转、最终收束方向。\n"
            "volume_outline 每卷必须包含：volume_number, title, target_chapters, min_chapters, soft_max_chapters, hard_max_chapters, "
            "entry_condition, exit_condition, required_milestones, goal, main_conflict, turning_points, ending。\n"
            "target/min/soft_max/hard_max 是弹性章数边界，不是平均分配；必须根据本卷剧情容量设定，长卷可以更长，过渡卷可以更短。\n"
            "entry_condition 和 exit_condition 必须是可判断的剧情状态；required_milestones 至少 3 条，用来判断本卷是否可以收束。\n"
            "每卷 turning_points 至少 4 条，必须具体到事件，不要写“矛盾升级”“真相浮出水面”这类空话。\n\n"
            f"{history_section}\n"
            f"作品资料：\n{json_dumps(work_bundle)}"
        )
        parsed = self.complete_json(
            user_prompt,
            validator=PLANNER_OUTLINE_VALIDATOR,
            default={},
            normalizer=normalize_outline,
            mock_hint={"task": "outline"},
        )
        return parsed

    def generate_chapter_outlines(
        self,
        work_bundle: dict[str, Any],
        *,
        start_chapter: int = 1,
        count: int = 30,
        volume_number: int | None = None,
    ) -> dict[str, Any]:
        history_section = history_prompt_section(work_bundle, task="chapter_outlines")
        target_volume_number = int(volume_number or work_bundle.get("target_volume_number") or 0)
        volume_instruction = ""
        if target_volume_number:
            target_volume = work_bundle.get("target_volume") or {}
            volume_title = target_volume.get("title") or f"第{target_volume_number}卷"
            volume_instruction = (
                f"这些章节全部属于第 {target_volume_number} 卷（{volume_title}）。"
                f"每个章节对象都必须写入 volume_number: {target_volume_number}。\n"
            )
        else:
            volume_instruction = (
                "请根据作品资料里的 volume_outline、已有章节细纲、最近章节摘要和剧情阶段，自行判断每章所属分卷。\n"
                "章节号必须按全书连续编号，不要因为进入新分卷就从第 1 章重新开始。\n"
                "你可以提出进入下一卷，但系统会校验：不能跳卷；当前卷未达到 min_chapters 时不能换卷；超过 hard_max_chapters 时必须进入下一卷或收束。\n"
                "判断是否换卷时必须参考 active_volume、chapter_counts、entry_condition、exit_condition 和 required_milestones。\n"
                "如果当前卷 exit_condition 和核心里程碑尚未完成，应继续当前卷；如果已完成且达到 min_chapters，可以把后续章节归入下一卷。\n"
                "不要把所有章节默认放进第一卷，也不要因为界面当前选中了某个分卷就强行归入该卷。\n"
            )
        user_prompt = (
            f"请生成从第 {start_chapter} 章开始的 {count} 章细纲，输出供程序解析的合法 JSON。\n"
            f"{volume_instruction}"
            "JSON 字段：chapters。\n"
            "chapters 内每项必须包含：chapter_number, volume_number, story_time, title, outline, opening_hook, continuity_debt, debt_type, opening_mode, opening_subject, opening_trigger, time_or_environment_function, "
            "previous_anchor, first_screen_conflict, forbidden_opening, reader_question_in, reader_answer_out, new_question_out, scene_cards, chapter_goal, conflict, main_scene, "
            "reader_expectation, characters_present, clues, new_information, chapter_payoff, "
            "character_change, foreshadowing, emotional_turn, emotional_rhythm, "
            "ending_external_anchor, next_opening_action, next_continuity_debt, ending_hook, handoff, forbidden。\n"
            "scene_cards 每章 3 到 6 个，必须写清 scene_goal, obstacle, information_gain, emotional_shift, scene_exit。\n"
            "story_time 必须写清本章在故事内部的时间锚点，例如“案发次日清晨”“行动当晚”“上一章后半日”，不能留空或只写“当前”；它只是时间线参考，不是正文第一句。\n"
            "outline 可以保留必要时间信息，但必须写事件链，不能连续章节都写成“时间/地点 + 人物普通动作 + 出发/抵达/整备”；即使同一时段推进，也要用新证据、新威胁、新选择或新关系压力体现变化。\n"
            "chapter_goal 必须用“【目的词：...】”开头；emotional_rhythm 必须写目标情绪和情绪路线；"
            "opening_hook 和 ending_hook 必须写明钩子类型，ending_hook 还要标注强/中/弱。\n"
            "reader_expectation 要写清读者进入本章最想看到、知道或感受到什么；"
            "chapter_payoff 要写清本章实际给出的阅读回报，不能只写推进剧情。\n"
            "opening_hook 要写成本章前 300 字的第一屏方案，必须包含开头类型、第一屏问题、切入方式和读者钩子，不能只写“制造悬念”。\n"
            "continuity_debt 必须写上一章留下、本章必须处理的未闭合内容；第 1 章写本书开场必须处理的第一问题。它可以是对话、动作、物件、威胁、选择、证据、关系、缺席或环境异常，不要求上一章必须用对白结尾。\n"
            "debt_type 必须从对话、动作、物件、威胁、选择、证据、关系、缺席、环境异常中选择一个或两个。\n"
            "opening_mode 必须从物件、对白、异常、后果、反应、命令、缺席、冲突、时间压力、环境异常、人物动作中选择；同一批章节必须轮换，不得连续三章同一种 opening_mode。\n"
            "opening_subject 必须写清开头主体是主角、配角、物件、对手、群体、命令文书、缺席的人还是环境异常；不得连续三章都以主角为开头主体。\n"
            "opening_trigger 必须写本章开头触发的新事件，不能只写上马、看一眼、推门、整理东西、赶路或醒来。\n"
            "time_or_environment_function 只在使用时间、地点、天气或环境时填写它制造的压力、异常、倒计时、威胁或反证；如果本章不用时间环境开头，写“无”。\n"
            "previous_anchor 必须写上一章末尾可见的外部锚点，例如具体动作、对白、物件、证据、威胁、伤势或命令；第 1 章写本书开场要抓住的第一个可见锚点。\n"
            "first_screen_conflict 必须写成本章前 300 字内必须出现的问题、压力、异常、威胁、选择或反证，不能写成氛围或主题。\n"
            "forbidden_opening 必须根据最近章节开头和本章任务，写清本章禁用的开头方式，例如禁止重复时间、地点、天气、环境铺垫、醒来、普通检查、普通整备或照抄 story_time。\n"
            "reader_question_in 必须写读者进入本章时最想知道的具体问题；reader_answer_out 必须写本章至少回答什么；new_question_out 必须写本章结尾新产生的具体问题。\n"
            "开头类型可在动作承接、对白逼问、证据异常、威胁抵达、后果反噬、关系冲突、时间压迫、环境反常、选择逼迫、反证出现中选择。\n"
            "时间、地点、环境和人物动作都可以作为开头，但必须带出问题、压力、异常、威胁、选择、误会、反证或上一章后果；禁止只有普通动作或氛围铺垫。\n"
            "细纲必须能连续承接，不能每章孤立；相邻章节的 handoff 与下一章开头任务必须对应。\n"
            "每章 outline 必须包含连续事件链：承接债 -> 开头触发事件 -> 本章行动 -> 新阻力 -> 信息增量 -> 本章回答 -> 新问题 -> 下一章接力点。\n"
            "同一批章节的 opening_hook 切入方式必须轮换；不要连续几章都用人物加普通动作，也不要连续几章都用时间地点环境式切入。\n"
            "写作阶段会把 story_time 视为后台时间锚点，而不是正文开头来源；请不要让 opening_hook 依赖照抄 story_time 才能成立。\n"
            "每章必须写清楚具体事件、证据、阻力和信息增量，禁止只写“承接前文”“继续调查”“留下钩子”。\n"
            "ending_external_anchor 必须写本章最后 150 字要落住的外部动作、对白、证据、威胁、命令或物件变化；禁止写成意味、命运、夜色、倒计时等抽象氛围。\n"
            "next_opening_action 必须写下一章第一段应直接执行的动作、对白、证据处理、威胁应对或关系逼问，并且要和 ending_external_anchor 一一对应。\n"
            "next_continuity_debt 必须写交给下一章的具体承接债，不能写“继续调查”“处理余波”“推进主线”。\n"
            "同一批章节之间不得复用同一段 outline，不得只替换章节号或标题。\n"
            "如果已有章节、伏笔、时间线，必须承接，不得重启案件或重复第一章场景。\n\n"
            f"{history_section}\n"
            f"作品资料：\n{json_dumps(work_bundle)}"
        )
        parsed = self.complete_json(
            user_prompt,
            validator=PLANNER_CHAPTER_OUTLINES_VALIDATOR,
            default={"chapters": []},
            normalizer=normalize_chapter_outlines,
            mock_hint={
                "task": "chapter_outlines",
                "start_chapter": start_chapter,
                "count": count,
                "volume_number": target_volume_number,
            },
        )
        return parsed
