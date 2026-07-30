from __future__ import annotations

from typing import Any

from app.services.base_agent import BaseAgent
from app.utils.history import history_prompt_section
from app.utils.json_parser import json_dumps


class WriterAgent(BaseAgent):
    agent_name = "writer"
    prompt_file = "writer_prompt.md"

    def write_chapter(self, context: dict[str, Any]) -> str:
        chapter = context.get("chapter", {})
        history_section = history_prompt_section(context, task="writer")
        user_prompt = (
            "请根据以下上下文生成本章正文。\n"
            "优先级：chapter_execution_card、锁定事实和角色/世界约束高于 chapter_task_sheet；"
            "chapter_transition_contract 规定承接方式；genre_contract 只校准题材承诺，不可扩写成设定说明。\n"
            "第一屏：除非 allowed_shift 为真，第一段必须接住 last_visible_beat、first_screen_task 或 must_use_concrete_anchor 的下一拍，"
            "并在前 300 字处理承接债和第一屏冲突。转视角或跨阶段时，先写上一章后果如何落到新场景。\n"
            "推进：按 chapter_task_sheet 的场景卡写成目标、阻碍、行动、信息或情绪变化、场景出口；"
            "本章必须兑现读者问题和阶段回报，再交出具体的下一章承接债。\n"
            "段落：按动作结果、发言者、信息揭露、空间变化或情绪转折换段。对白和强冲突可短；解释性段落必须服务当前选择，"
            "不要连续堆背景或把每句都切成短视频式短段。\n"
            "语言：破折号原则上 0 到 2 处，章首前 300 字不用它承担解释或转折；对照判断句、环境铺垫和普通动作都只能在有叙事功能时使用。"
            "recent_style_signatures、opening_variation_policy 和 ending_variation_policy 只用于避开重复发动机和章尾指纹，不能套出新模板。\n"
            "结尾：用本章事件产生的动作、证据、关系压力、威胁、代价或选择作为外部锚点；不要以抽象感慨、预告旁白或重复物件收束。\n"
            "必须遵守 chapter_word_target，不能写成摘要、提纲或无效注水。若上下文冲突，以已成立事实和锁定设定为准。\n\n"
            f"{history_section}\n"
            f"上下文：\n{json_dumps(context)}"
        )
        return self.complete(
            user_prompt,
            mock_hint={
                "chapter_number": chapter.get("chapter_number", 1),
                "title": chapter.get("title", ""),
            },
        ).strip()
