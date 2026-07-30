from __future__ import annotations

from typing import Any

from app.services.base_agent import BaseAgent
from app.utils.history import history_prompt_section
from app.utils.json_parser import json_dumps


class ReviserAgent(BaseAgent):
    agent_name = "reviser"
    prompt_file = "reviser_prompt.md"

    def revise_chapter(self, context: dict[str, Any], draft: str, review: dict[str, Any]) -> str:
        history_section = history_prompt_section(context, task="reviser")
        revision_plan = review.get("revision_plan") if isinstance(review, dict) else []
        user_prompt = (
            "请根据修订计划修订章节正文，只输出修订后的正文。\n\n"
            "优先修复高优先级的承接、因果、人物和回报问题；保留 chapter_task_sheet、chapter_execution_card、"
            "minimal_memory_pack 和锁定事实中的有效内容。开头必须继续执行交接口，结尾必须保留下一章可接的外部锚点。\n"
            "依据 recent_style_signatures 和避重策略处理重复章首、章尾、破折号或对照句，但不要把语言改成新模板。"
            "字数按 chapter_word_target 调整，扩写只增加有效场景，压缩只删重复表达。\n\n"
            f"{history_section}\n"
            f"上下文：\n{json_dumps(context)}\n\n"
            f"修订计划：\n{json_dumps(revision_plan)}\n\n"
            f"初稿：\n{draft}"
        )
        return self.complete(user_prompt, mock_hint={"draft": draft, "revision_plan": revision_plan}).strip()

    def revise_with_instruction(self, context: dict[str, Any], draft: str, instruction: str) -> str:
        history_section = history_prompt_section(context, task="reviser")
        user_prompt = (
            "请根据用户修改意见修订章节正文，只输出修订后的正文。\n"
            "用户意见优先级最高；在不违背锁定设定、细纲和上下文的前提下，尽量保留当前正文中可用的段落、对白和事件，"
            "不要从零重写成另一章。\n\n"
            "必要事实以 minimal_memory_pack、chapter_task_sheet 和章节交接口为准；不要新增无关设定或让下一章承接债失效。"
            "开头、结尾和语言的改动同时遵守 recent_style_signatures、避重策略和 chapter_word_target。\n\n"
            f"{history_section}\n"
            f"上下文：\n{json_dumps(context)}\n\n"
            f"用户修改意见：\n{instruction.strip()}\n\n"
            f"当前正文：\n{draft}"
        )
        return self.complete(user_prompt, mock_hint={"draft": draft, "instruction": instruction}).strip()

    def revise_opening_ending(self, context: dict[str, Any], draft: str, issues: list[str]) -> str:
        history_section = history_prompt_section(context, task="reviser")
        user_prompt = (
            "请对当前章节做首尾专项修订，只输出修订后的完整正文。\n"
            "重点只处理前 300 到 500 字和最后 200 到 300 字；中段剧情、事实、对白、人物关系和事件顺序尽量保持不变。\n"
            "开头接住 chapter_transition_contract 的具体锚点和第一屏冲突；结尾落到新的外部锚点并给下一章第一段留下可执行动作。\n"
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
