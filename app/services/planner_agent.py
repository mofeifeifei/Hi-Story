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
            "JSON 字段：book_bible, title_candidates, summary, core_selling_points, target_readers, "
            "protagonist, supporting_characters, villains, world_rules, main_goal, first_volume_direction, historical_profile。"
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
        history_section = history_prompt_section(work_bundle)
        user_prompt = (
            "请根据作品资料生成全书大纲和分卷大纲，输出供程序解析的合法 JSON。\n"
            "这不是宣传简介，要像真正能指导长篇连载的编辑部大纲。\n"
            "full_outline 要分成 4 到 8 个自然段，段落之间用换行分隔；必须包含：主线问题、阶段推进、人物关系变化、核心反转、最终收束方向。\n"
            "volume_outline 每卷必须包含：volume_number, title, goal, main_conflict, turning_points, ending。\n"
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
        history_section = history_prompt_section(work_bundle)
        target_volume_number = int(volume_number or work_bundle.get("target_volume_number") or 1)
        target_volume = work_bundle.get("target_volume") or {}
        volume_title = target_volume.get("title") or f"第{target_volume_number}卷"
        user_prompt = (
            f"请生成从第 {start_chapter} 章开始的 {count} 章细纲，输出供程序解析的合法 JSON。\n"
            f"这些章节全部属于第 {target_volume_number} 卷（{volume_title}）。每个章节对象都必须写入 volume_number: {target_volume_number}。\n"
            "JSON 字段：chapters。\n"
            "chapters 内每项必须包含：chapter_number, volume_number, story_time, title, outline, opening_hook, scene_cards, chapter_goal, conflict, main_scene, "
            "reader_expectation, characters_present, clues, new_information, chapter_payoff, "
            "character_change, foreshadowing, emotional_turn, emotional_rhythm, "
            "ending_hook, handoff, forbidden。\n"
            "scene_cards 每章 3 到 6 个，必须写清 scene_goal, obstacle, information_gain, emotional_shift, scene_exit。\n"
            "story_time 必须写清本章在故事内部的时间锚点，例如“洪武二十五年秋，案发次日清晨”，不能留空或只写“当前”。\n"
            "chapter_goal 必须用“【目的词：...】”开头；emotional_rhythm 必须写目标情绪和情绪路线；"
            "opening_hook 和 ending_hook 必须写明钩子类型，ending_hook 还要标注强/中/弱。\n"
            "reader_expectation 要写清读者进入本章最想看到、知道或感受到什么；"
            "chapter_payoff 要写清本章实际给出的阅读回报，不能只写推进剧情。\n"
            "opening_hook 要写清本章前 300 字要落到的具体动作、冲突、异常、证据、情绪或选择，不能只写“制造悬念”。\n"
            "细纲必须能连续承接，不能每章孤立；相邻章节的 handoff 与下一章开头任务必须对应。\n"
            "每章必须写清楚具体事件、证据、阻力和信息增量，禁止只写“承接前文”“继续调查”“留下钩子”。\n"
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
