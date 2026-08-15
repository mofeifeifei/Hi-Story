from __future__ import annotations

from typing import Any

from app.services.base_agent import BaseAgent
from app.utils.history import history_prompt_section
from app.utils.json_parser import json_dumps


class ReviserAgent(BaseAgent):
    agent_name = "reviser"
    prompt_file = "reviser_prompt.md"
    # A larger single budget is safer than repeating the same expensive full-chapter request.
    output_attempts = 1

    def revise_chapter(self, context: dict[str, Any], draft: str, review: dict[str, Any]) -> str:
        history_section = history_prompt_section(context, task="reviser")
        revision_plan = review.get("revision_plan") if isinstance(review, dict) else []
        if not isinstance(revision_plan, list):
            revision_plan = []
        revision_tasks = [item for item in revision_plan if isinstance(item, dict)][:5]
        user_prompt = (
            "按修订任务局部编辑正文，只输出修订后的完整正文。\n"
            "最多执行五项；未列出的内容保持原样。scene_handoff、story_plan、既有事实和人物选择不可被改坏。\n"
            "除非任务明确要求压缩，否则修订稿不得明显短于初稿，也不得低于 chapter_word_target.min；补写缺失场景时不能删除已有有效场景。\n"
            "连续性优先，其次是因果和人物，再处理结尾与语言。结尾可以自然收场，不要强造悬念。\n"
            "语言清理只改命中句段：保留人物声音，删去替读者解释、格言式总结和整齐造势，不做同义词轮换。\n"
            "不要在正文中复述任何上下文字段名。\n\n"
            f"{history_section}\n"
            f"上下文：\n{json_dumps(context)}\n\n"
            f"修订任务单：\n{json_dumps(revision_tasks)}\n\n"
            f"初稿：\n{draft}"
        )
        return self.complete(user_prompt, mock_hint={"draft": draft, "revision_plan": revision_tasks}).strip()

    def revise_with_instruction(
        self,
        context: dict[str, Any],
        draft: str,
        instruction: str,
        known_issues: list[str] | None = None,
    ) -> str:
        history_section = history_prompt_section(context, task="reviser")
        issue_section = (
            f"\n程序预检发现的问题：\n{json_dumps((known_issues or [])[:8])}\n"
            if known_issues
            else ""
        )
        user_prompt = (
            "请根据用户修改意见修订章节正文，只输出修订后的正文。\n"
            "用户意见优先级最高；在不违背锁定设定、细纲和上下文的前提下，尽量保留当前正文中可用的段落、对白和事件，"
            "不要从零重写成另一章。\n\n"
            "除非用户明确要求压缩或删减，否则输出长度不得明显短于当前正文，也不得低于 chapter_word_target.min。"
            "新增开头、场景或结尾时保留其他已经成立的场景，不能用新段落替换掉整章。\n"
            "必要事实以 minimal_memory_pack、story_plan 和 scene_handoff 为准；不要新增无关设定或破坏下一章所需事实。"
            "开头、结尾和语言的改动同时遵守 style_guard 和 chapter_word_target。\n\n"
            f"{history_section}\n"
            f"上下文：\n{json_dumps(context)}\n\n"
            f"用户修改意见：\n{instruction.strip()}\n\n"
            f"{issue_section}"
            f"当前正文：\n{draft}"
        )
        return self.complete(user_prompt, mock_hint={"draft": draft, "instruction": instruction}).strip()

    def refine_revision(
        self,
        context: dict[str, Any],
        draft: str,
        instruction: str,
        review: dict[str, Any],
        issues: list[str],
    ) -> str:
        history_section = history_prompt_section(context, task="reviser")
        revision_plan = review.get("revision_plan") if isinstance(review, dict) else []
        if not isinstance(revision_plan, list):
            revision_plan = []
        user_prompt = (
            "这是同一次修订任务的定向返修。只输出返修后的完整正文。\n"
            "第一轮已经完成的有效修改必须保留；只修复复审仍然确认存在的问题，不要从头换一种写法。\n"
            "用户原始修改意见仍是最高目标。依次保证上下文承接、场景完成、人物因果、内容保留和语言自然。\n"
            "不得通过删除场景规避问题，不得明显缩短正文，不得输出解释、清单或字段名。\n\n"
            f"{history_section}\n"
            f"上下文：\n{json_dumps(context)}\n\n"
            f"用户原始修改意见：\n{instruction.strip()}\n\n"
            f"复审确认的问题：\n{json_dumps(issues[:8])}\n\n"
            f"复审任务单：\n{json_dumps([item for item in revision_plan if isinstance(item, dict)][:5])}\n\n"
            f"第一轮修订稿：\n{draft}"
        )
        return self.complete(
            user_prompt,
            mock_hint={"draft": draft, "instruction": instruction, "revision_plan": revision_plan[:5]},
        ).strip()

    def revise_opening_ending(self, context: dict[str, Any], draft: str, issues: list[str]) -> str:
        history_section = history_prompt_section(context, task="reviser")
        user_prompt = (
            "请对当前章节做首尾专项修订，只输出修订后的完整正文。\n"
            "重点只处理前 300 到 500 字和最后 200 到 300 字；中段剧情、事实、对白、人物关系和事件顺序尽量保持不变。\n"
            "开头执行 scene_handoff 中尚未完成的动作或后果；结尾在本章事件形成的自然切点停下。\n"
            "如果问题涉及语言或章尾重复，只做必要的定向改写，保留剧情事实、场景顺序、对白含义和章末交接口；"
            "不要把时间环境开头简单替换成人物普通动作模板。\n"
            "不要把正文改成另一章，不要新增无关设定，不要输出修改说明。\n\n"
            f"{history_section}\n"
            f"上下文：\n{json_dumps(context)}\n\n"
            f"需要修复的问题：\n{json_dumps(issues)}\n\n"
            f"当前正文：\n{draft}"
        )
        return self.complete(user_prompt, mock_hint={"draft": draft, "issues": issues}).strip()

    def sanitize_style(self, context: dict[str, Any], draft: str, issues: list[str]) -> str:
        history_section = history_prompt_section(context, task="reviser")
        user_prompt = (
            "请对当前章节做语言清理专修，只输出清理后的完整正文。\n"
            "本任务只处理语言风险：减少破折号解释式表达、删除对照判断句式、改掉章首解释式开头和机器味模板。\n"
            "不得扩写剧情，不得新增信息，不得改变场景顺序、人物行动、证据含义、对白意图和章末交接口。\n"
            "替换方式优先使用动作承接、对白反应、物件状态、证据差异、因果短句和自然断句。\n"
            "如果某个破折号确实是对白中断或突发打断，可以保留；其余尽量改写。\n"
            "不要解释修改理由，不要输出清单。\n\n"
            f"{history_section}\n"
            f"上下文：\n{json_dumps(context)}\n\n"
            f"需要清理的风险：\n{json_dumps(issues)}\n\n"
            f"当前正文：\n{draft}"
        )
        return self.complete(user_prompt, mock_hint={"draft": draft, "issues": issues}).strip()
