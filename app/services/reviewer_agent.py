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
        story_plan = context.get("story_plan") if isinstance(context.get("story_plan"), dict) else {}
        scene_cards = story_plan.get("scene_cards") if isinstance(story_plan.get("scene_cards"), list) else []
        expected_scene_count = len(scene_cards)
        history_section = history_prompt_section(context, task="reviewer")
        historical_hits = (
            detect_historical_anachronisms(draft)
            if context.get("history_specialist", {}).get("enabled")
            else []
        )
        combined_hits = [*template_hits, *historical_hits]
        user_prompt = (
            "请审查以下章节，输出供程序解析的合法 JSON。\n"
            "本地质量报告已覆盖破折号、模板句、长度、开头和章尾的机械检测；只复核边界问题，不要重复罗列它。\n"
            "重点对照 scene_handoff 和 story_plan：检查开头是否承接，场景是否有因果推进，人物选择是否符合状态，本章是否产生实际变化。"
            "逐张核对 story_plan.scene_cards，scene_coverage 必须与场景卡一一对应；只有目标、阻碍、信息变化或场景出口实际写入正文才算完成。"
            "结尾可以自然收场，不要把缺少强行悬念当成问题。\n"
            "请额外给出 4 到 6 个 title_candidates。标题应概括本章实际完成的核心变化或关键行动，不泄露最后反转；"
            "候选必须覆盖不同角度，避免连续“X之Y”、抽象概念词和近章重复结构。\n\n"
            f"{history_section}\n"
            f"上下文：\n{json_dumps(context)}\n\n"
            f"本地模板句与历史穿帮检测：\n{json_dumps(combined_hits)}\n\n"
            f"章节正文：\n{draft}"
        )
        def validate_review(value: Any) -> list[str]:
            issues = REVIEW_VALIDATOR(value)
            coverage = value.get("scene_coverage") if isinstance(value, dict) else []
            if expected_scene_count and len(coverage or []) != expected_scene_count:
                issues.append(
                    f"scene_coverage 必须逐项核对 {expected_scene_count} 张场景卡，当前返回 {len(coverage or [])} 项"
                )
            if expected_scene_count and isinstance(coverage, list):
                indexes = {
                    int(item.get("scene_index") or 0)
                    for item in coverage
                    if isinstance(item, dict) and str(item.get("scene_index") or "").isdigit()
                }
                expected_indexes = set(range(1, expected_scene_count + 1))
                if indexes != expected_indexes:
                    issues.append("scene_coverage 的 scene_index 必须按场景卡顺序从 1 连续编号")
            return issues

        parsed = self.complete_json(
            user_prompt,
            validator=validate_review,
            default={},
            normalizer=lambda value: normalize_review(value, template_hits=combined_hits),
            mock_hint={
                "template_hits": combined_hits,
                "historical_enabled": bool(context.get("history_specialist", {}).get("enabled")),
                "repeat_risk": context.get("repeat_risk_warnings", []),
                "scene_cards": scene_cards,
            },
            repair_attempts=1,
        )
        return parsed
