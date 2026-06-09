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
            "重点：handoff 必须生成可让下一章第一段直接承接的章节交接口，不能只写抽象悬念或氛围总结。\n\n"
            "同时：人物状态、伏笔、世界约束和接力棒要能服务下一章的 minimal_memory_pack，只保留不知道就会写错的信息。\n\n"
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
