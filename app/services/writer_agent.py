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
            "注意：必须优先执行 chapter.outline_task_sheet 中的本章目标、场景卡、核心冲突、线索推进、信息增量和接力棒。\n"
            "必须优先使用 minimal_memory_pack；它只包含本章不知道就会写错的人物状态、伏笔和世界约束。\n"
            "必须优先服从 book_bible、chapter_notes、人物动态状态和用户批注。\n"
            "必须读取 genre_contract；它是本书的轻量题材契约卡，只按其中的题材核心、读者承诺、冲突发动机、章节回报、开头偏好、避雷和语言质感保持题材味道，不要扩写成新的题材专项提示词。\n"
            "必须读取 chapter_word_target，并按其中的动态目标字数、建议范围和规则生成完整章节。\n"
            "必须优先承接 chapter_transition_contract；第一段要直接接住上一章末尾的具体动作、对白、物件、证据或威胁。\n"
            "必须读取 chapter.outline_detail.continuity_debt、opening_mode、opening_subject、opening_trigger、reader_question_in、reader_answer_out、new_question_out、next_continuity_debt；它们分别约束本章承接债、开头功能、开头主体、触发事件、入章问题、本章回答、新问题和下一章承接债。\n"
            "必须读取 chapter.outline_detail.previous_anchor、first_screen_conflict、forbidden_opening、ending_external_anchor、next_opening_action；它们分别约束上一章锚点、第一屏冲突、禁用开头、章末锚点和下一章开场动作。\n"
            "story_time 只是时间线参考，outline 是事件链参考；正文第一句禁止照抄 story_time 或 outline 的时间地点说明。\n"
            "正文第一屏必须优先按 opening_hook、handoff 和上一章后果制造吸引力：问题、压力、异常、威胁、选择、误会、反证或代价至少出现一个。\n"
            "开头必须兑现 opening_mode 和 opening_trigger，但不要把它变成固定句式；时间、地点、环境和人物动作都可以开头，但必须有叙事功能，禁止写成普通动作模板或单纯氛围铺垫。\n"
            "第一段必须处理 continuity_debt，并让 reader_question_in 开始得到推进；本章结束前必须兑现 reader_answer_out，并把 new_question_out 或 next_continuity_debt 留成下一章可直接承接的外部问题。\n"
            "必须读取 recent_chapter_openings 和 opening_variation_policy；如果最近章首已经出现同类开头，本章必须换开头策略。\n"
            "章末必须留下可被下一章第一段承接的外部锚点；不能用意味悠长的空泛收束。\n"
            "不能擅自修改锁定设定；不要使用禁用模板句。\n"
            "如果细纲与前文冲突，优先服从前文和锁定设定，不要自行重启剧情。\n\n"
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
