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
            "写出本章正文，只输出小说内容。\n"
            "先执行 scene_handoff：直接承接时从上一章最后事件的下一刻写起；允许转场时，先让上一章后果抵达新场景。\n"
            "再按 story_plan 推进人物行动与局势变化。已成立事实和锁定设定优先，genre_contract 只校准题材承诺。\n"
            "让场景靠因果连接，按叙事动作自然分段。结尾停在本章事件形成的自然切点，不必强造悬念或余韵。\n"
            "保留人物声音和不均匀节奏；删去替读者下结论的解释、本质判断、整齐排比和总结金句。不要在正文中复述任何上下文字段名。\n"
            "遵守 chapter_word_target，不能写成摘要或提纲。\n\n"
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
