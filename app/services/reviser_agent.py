from __future__ import annotations

from typing import Any

from app.services.base_agent import BaseAgent
from app.utils.history import history_prompt_section
from app.utils.json_parser import json_dumps


class ReviserAgent(BaseAgent):
    agent_name = "reviser"
    prompt_file = "reviser_prompt.md"

    def revise_chapter(self, context: dict[str, Any], draft: str, review: dict[str, Any]) -> str:
        history_section = history_prompt_section(context)
        user_prompt = (
            "请根据审稿意见修订章节正文，只输出修订后的正文。\n\n"
            "修订时必须保留并兑现章节目的词、目标情绪、读者期待和本章回报；必要事实以 minimal_memory_pack 为准。\n\n"
            "如果审稿意见指出字数问题，必须依据 chapter_word_target 的动态目标修订，不能写成短摘要，也不能注水。\n\n"
            f"{history_section}\n"
            f"上下文：\n{json_dumps(context)}\n\n"
            f"审稿意见：\n{json_dumps(review)}\n\n"
            f"初稿：\n{draft}"
        )
        return self.complete(user_prompt, mock_hint={"draft": draft, "review": review}).strip()

    def revise_with_instruction(self, context: dict[str, Any], draft: str, instruction: str) -> str:
        history_section = history_prompt_section(context)
        user_prompt = (
            "请根据用户修改意见修订章节正文，只输出修订后的正文。\n"
            "用户意见优先级最高；在不违背锁定设定、细纲和上下文的前提下，尽量保留当前正文中可用的段落、对白和事件，"
            "不要从零重写成另一章。\n\n"
            "必要事实以 minimal_memory_pack 为准；不要为局部修订新增无关设定或改掉章末交接口。\n\n"
            "同时保留 chapter_word_target 的动态字数要求；扩写要增加有效剧情，压缩要删冗余表达。\n\n"
            f"{history_section}\n"
            f"上下文：\n{json_dumps(context)}\n\n"
            f"用户修改意见：\n{instruction.strip()}\n\n"
            f"当前正文：\n{draft}"
        )
        return self.complete(user_prompt, mock_hint={"draft": draft, "instruction": instruction}).strip()
