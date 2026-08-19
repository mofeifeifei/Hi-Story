from __future__ import annotations

from typing import Any

from app.core.contracts import MEMORY_CARD_VALIDATOR, normalize_memory_card
from app.services.base_agent import BaseAgent
from app.utils.history import history_prompt_section
from app.utils.json_parser import json_dumps


class MemoryAgent(BaseAgent):
    agent_name = "memory"
    prompt_file = "memory_prompt.md"

    def make_memory_card(self, context: dict[str, Any], final_text: str) -> dict[str, Any]:
        chapter = context.get("chapter", {})
        history_section = history_prompt_section(context, task="memory")
        user_prompt = (
            "请根据最终稿生成章节记忆卡，输出供程序解析的合法 JSON。\n\n"
            "handoff 只记录正文末尾的剧情事实：当时的人物、地点、最后动作、尚未完成的事情，以及下一章最先需要发生的事件。"
            "字段内容使用小说事实描述，不写编辑术语、策略说明或抽象氛围。\n\n"
            "人物状态、伏笔和世界约束只保留不知道就会写错的信息。\n\n"
            "额外生成 chapter_result_card：只根据最终稿记录核心变化、读者回报、关键行动和关键代价。"
            "其中 title_decision 先用一句话概括谁做了什么、造成什么变化，再给出 4 到 6 个自然中文标题，"
            "选出唯一 recommended_title 并说明 reason。标题不能只摘地点、物件或人物名，不能写成公文状态、"
            "数据库标签或名词堆叠，也不要使用泛化概念、重复近章结构或泄露最后反转。\n\n"
            f"{history_section}\n"
            f"上下文：\n{json_dumps(context)}\n\n"
            f"最终稿：\n{final_text}"
        )
        parsed = self.complete_json(
            user_prompt,
            validator=MEMORY_CARD_VALIDATOR,
            default={},
            normalizer=normalize_memory_card,
            mock_hint={"chapter_number": chapter.get("chapter_number", 1)},
        )
        return parsed
