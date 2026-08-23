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


def _planner_context(bundle: dict[str, Any]) -> dict[str, Any]:
    context = dict(bundle)
    context.pop("history_specialist", None)
    return context


def _short_context(value: Any, limit: int = 360) -> Any:
    if isinstance(value, str):
        text = value.strip()
        return text if len(text) <= limit else text[:limit].rstrip("，,。；;：: ") + "…"
    if isinstance(value, list):
        return [_short_context(item, limit) for item in value[:12]]
    if isinstance(value, dict):
        return {key: _short_context(item, limit) for key, item in value.items()}
    return value


def _chapter_planner_context(bundle: dict[str, Any]) -> dict[str, Any]:
    """Keep chapter planning context focused without changing writer context."""
    context = _planner_context(bundle)
    # Historical titles are for program-side duplicate detection only. They
    # must not become examples that steer the next title toward the same mold.
    context.pop("recent_title_ledger", None)
    context["book_bible"] = _short_context(context.get("book_bible", {}), 720)
    context["characters"] = [
        _short_context(
            {
                key: item.get(key, "")
                for key in [
                    "name",
                    "role",
                    "goal",
                    "current_goal",
                    "current_state",
                    "relationship_stage",
                    "locked_rules",
                ]
            },
            300,
        )
        for item in context.get("characters", [])[:8]
        if isinstance(item, dict)
    ]
    context["world_rules"] = [
        _short_context(
            {
                key: item.get(key, "")
                for key in ["rule_name", "rule_content", "limitations", "forbidden_changes"]
            },
            300,
        )
        for item in context.get("world_rules", [])[:8]
        if isinstance(item, dict)
    ]
    context["open_plot_threads"] = [
        _short_context(
            {
                key: item.get(key, "")
                for key in ["first_chapter", "content", "planned_resolve_chapter"]
            },
            360,
        )
        for item in context.get("open_plot_threads", [])[:10]
        if isinstance(item, dict)
    ]
    for key in [
        "recent_chapter_outlines",
        "recent_summaries",
        "recent_chapter_openings",
        "recent_title_ledger",
        "volume_transition_context",
    ]:
        if key in context:
            context[key] = _short_context(context[key], 420)
    return context


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
            "book_contract 是轻量题材契约卡，只写短句，字段包含 genre_core, reader_promise, conflict_engine, chapter_payoff, "
            "opening_preference, avoid, language_texture, platform_rhythm, scene_variety, title_direction。"
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
            f"作品资料：\n{json_dumps(_planner_context(work_bundle))}"
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
        compact: bool = False,
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
                "判断是否换卷时必须参考 volume_transition_context.progress、volume_transition_context.volume_plot_threads、active_volume、chapter_counts、entry_condition、exit_condition、required_milestones、最近章节摘要和未回收伏笔。\n"
                "如果当前卷 exit_condition 和核心里程碑尚未完成，应继续当前卷；如果已完成且达到 min_chapters，可以把后续章节归入下一卷。\n"
                "你必须输出顶层 volume_decision：should_transition, from_volume, to_volume, reason, completed_milestones, unfinished_milestones, carry_over, next_volume_opening_focus。\n"
                "如果不换卷，should_transition 为 false，from_volume/to_volume 写当前卷，reason 写继续当前卷的剧情理由。\n"
                "不要把所有章节默认放进第一卷，也不要因为界面当前选中了某个分卷就强行归入该卷。\n"
            )
        compact_instruction = (
            "这是截断后的紧凑重试。只保留核心事实，每个普通字段 1 句，每个场景不超过 80 个中文字符；"
            "不要解释、不要重复同一事实，整个 planning_core 尽量控制在 3000 个中文字符以内。\n"
            if compact
            else "所有内容只写一次，普通字段 1 到 2 句，每个场景不超过 120 个中文字符；整个 planning_core 控制在 4500 个中文字符以内。\n"
        )
        user_prompt = (
            f"请生成从第 {start_chapter} 章开始的 {count} 章细纲，输出供程序解析的合法 JSON。\n"
            f"{volume_instruction}"
            f"{compact_instruction}"
            "顶层 JSON 只能包含 volume_decision 和 chapters。无论是否换卷，都必须输出 chapters 数组。\n"
            "每个 chapters 项只能包含 planning_core，不要输出旧版几十个平行字段。planning_core 必须包含：chapter, sequence, bridge, questions, scenes, result, handoff。\n"
            "chapter 必须包含 chapter_number, volume_number, title, chapter_core_change, title_anchor, title_focus, sequence_id, sequence_goal, sequence_position, continuity_mode, story_time。\n"
            "bridge 必须包含 previous_anchor, continuity_debt, debt_type, opening_mode, opening_subject, opening_action, opening_conflict, forbidden_opening。上一章存在时，previous_anchor 必须指向具体人物、物件、动作或未完问题。\n"
            "questions 必须包含 in, answer, out；result 必须包含 reader_expectation, new_information, clues, chapter_payoff, character_change。\n"
            "scenes 必须是 3 到 5 个对象，每项包含 location, characters, goal, obstacle, turn, emotional_shift, exit。每场必须改变信息、关系、行动方向或代价，不能只换地点。\n"
            "handoff 必须包含 ending_event, next_opening_action, next_continuity_debt, cut_reason, unresolved_question, forbidden。next_opening_action 必须直接承接 ending_event。\n"
            "每 3 到 5 章组成连续剧情单元并使用相同 sequence_id。continuity_mode 只能是 direct、shift、new_stage；转场时写清上一章后果如何进入新场景。\n"
            "开头先处理上一章留下的动作或压力，避开近期重复的发动方式；story_time 只记时间线，不能直接充当正文开头。结尾来自本章事件，不强造悬念或悠长意境。\n"
            "先完成本章剧情契约，再确定标题。chapter_core_change 只能写本章最独有的一项变化，不能并列罗列多个结果；title_anchor 必须说明标题对应的具体事实；title_focus 只能写行动、发现、决定、关系或代价之一。title 是细纲阶段确定的工作标题，优先简洁凝练，但不得为了四字而牺牲准确性。历史标题只用于程序查重，不是创作范本，不要模仿其词语、句式或意象。所有字段值使用自然中文，不写内部字段名、策略说明或 Markdown。\n\n"
            f"{history_section}\n"
            f"作品资料：\n{json_dumps(_chapter_planner_context(work_bundle))}"
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
                "planning_core": True,
            },
            repair_attempts=0,
        )
        return parsed
