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
        history_section = history_prompt_section(context)
        user_prompt = (
            "请根据以下上下文生成本章正文。\n"
            "注意：必须优先执行 chapter.outline_task_sheet 中的本章目标、场景卡、核心冲突、线索推进、信息增量和接力棒。\n"
            "必须优先使用 minimal_memory_pack；它只包含本章不知道就会写错的人物状态、伏笔和世界约束。\n"
            "必须优先服从 book_bible、chapter_notes、人物动态状态和用户批注。\n"
            "必须优先承接 chapter_transition_contract；第一段要直接接住上一章末尾的具体动作、对白、物件、证据或威胁。\n"
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
