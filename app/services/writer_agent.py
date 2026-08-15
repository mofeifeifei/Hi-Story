from __future__ import annotations

from typing import Any

from app.services.base_agent import BaseAgent
from app.utils.history import history_prompt_section
from app.utils.json_parser import json_dumps


class WriterAgent(BaseAgent):
    agent_name = "writer"
    prompt_file = "writer_prompt.md"
    output_attempts = 2
    allow_truncated_output = True

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

    def continue_chapter(self, context: dict[str, Any], partial_text: str) -> str:
        history_section = history_prompt_section(context, task="writer")
        user_prompt = (
            "下面的章节正文被模型中途截断。请只续写截断位置之后的正文，不要重复已有段落，不要输出标题或说明。\n"
            "先接完当前句子，再完成 story_plan 中尚未落地的场景与章节回报，并停在本章事件形成的自然切点。\n"
            "不得改变已有正文中的事实、人物选择和事件顺序。\n\n"
            f"{history_section}\n"
            f"上下文：\n{json_dumps(context)}\n\n"
            f"已有正文：\n{partial_text}"
        )
        return self.complete(user_prompt, mock_hint={"draft": partial_text}).strip()

    def complete_short_chapter(self, context: dict[str, Any], partial_text: str) -> str:
        history_section = history_prompt_section(context, task="writer")
        target = context.get("chapter_word_target") if isinstance(context.get("chapter_word_target"), dict) else {}
        user_prompt = (
            "下面正文已经正常结束，但篇幅不足，通常意味着后续场景、选择后果或章节回报没有真正写完。\n"
            "只输出接在现有末尾之后的新正文，不要重复、摘要、改写或解释已有内容。\n"
            "逐张核对 story_plan.scene_cards，续写尚未落地的目标、阻碍、信息变化和场景出口；"
            "让新增内容与已有末句形成因果连接，最终完成 chapter_payoff。\n"
            f"当前篇幅目标：{json_dumps(target)}。新增内容应让整章接近最低范围，但不得用心理复述、环境描写或同义解释凑字数。\n"
            "如果已有正文已经写到后段，就从现有结果继续写其反应、选择和代价，不得回头重演同一场景。\n\n"
            f"{history_section}\n"
            f"上下文：\n{json_dumps(context)}\n\n"
            f"已有正文：\n{partial_text}"
        )
        return self.complete(user_prompt, mock_hint={"draft": partial_text, "completion": True}).strip()
