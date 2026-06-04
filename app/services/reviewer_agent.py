from __future__ import annotations

from typing import Any

from app.core.contracts import REVIEW_VALIDATOR, normalize_review
from app.services.base_agent import BaseAgent
from app.utils.history import history_prompt_section
from app.utils.json_parser import json_dumps
from app.utils.text_check import detect_historical_anachronisms, detect_template_phrases


class ReviewerAgent(BaseAgent):
    agent_name = "reviewer"
    prompt_file = "reviewer_prompt.md"

    def review_chapter(self, context: dict[str, Any], draft: str) -> dict[str, Any]:
        template_hits = detect_template_phrases(draft)
        history_section = history_prompt_section(context)
        historical_hits = (
            detect_historical_anachronisms(draft)
            if context.get("history_specialist", {}).get("enabled")
            else []
        )
        combined_hits = [*template_hits, *historical_hits]
        user_prompt = (
            "请审查以下章节，输出供程序解析的合法 JSON。\n"
            "本地模板句检测结果也需要纳入 template_hits。\n\n"
            "重点检查：第一段是否执行 chapter_transition_contract，章末是否留下下一章可直接承接的外部锚点。\n\n"
            "同时检查：是否兑现章节目的词、目标情绪、读者期待、本章回报，是否使用 minimal_memory_pack 中的必要状态和约束。\n\n"
            "还要根据 chapter_word_target 检查正文长度是否符合动态目标，不能把完整章节误写成短摘要或为凑字数注水。\n\n"
            f"{history_section}\n"
            f"上下文：\n{json_dumps(context)}\n\n"
            f"本地模板句与历史穿帮检测：\n{json_dumps(combined_hits)}\n\n"
            f"章节正文：\n{draft}"
        )
        parsed = self.complete_json(
            user_prompt,
            validator=REVIEW_VALIDATOR,
            default={},
            normalizer=lambda value: normalize_review(value, template_hits=combined_hits),
            mock_hint={
                "template_hits": combined_hits,
                "historical_enabled": bool(context.get("history_specialist", {}).get("enabled")),
                "repeat_risk": context.get("repeat_risk_warnings", []),
            },
        )
        return parsed
