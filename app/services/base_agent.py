from __future__ import annotations

import logging
import time
from typing import Any, Callable

from app.services.ai_client import AIClient
from app.utils.config import load_prompt
from app.utils.json_parser import json_dumps, parse_json_object


logger = logging.getLogger(__name__)


class BaseAgent:
    agent_name = "base"
    prompt_file = ""

    def __init__(self, client: AIClient):
        self.client = client
        self.system_prompt = load_prompt(self.prompt_file)

    def complete(self, user_prompt: str, *, json_mode: bool = False, mock_hint: dict | None = None) -> str:
        return self.client.complete(
            self.agent_name,
            self.system_prompt,
            user_prompt,
            json_mode=json_mode,
            mock_hint=mock_hint,
        )

    def complete_json(
        self,
        user_prompt: str,
        *,
        validator: Callable[[Any], list[str]],
        default: Any,
        normalizer: Callable[[Any], Any] | None = None,
        mock_hint: dict | None = None,
        repair_attempts: int = 1,
    ) -> Any:
        raw = self.complete(user_prompt, json_mode=True, mock_hint=mock_hint)
        parsed = parse_json_object(raw, default=default)
        if normalizer is not None:
            parsed = normalizer(parsed)
        issues = validator(parsed)
        if not issues:
            return parsed

        for _ in range(repair_attempts):
            started = time.perf_counter()
            logger.warning(
                "AI JSON validation failed agent=%s issues=%s; requesting repair",
                self.agent_name,
                "；".join(issues),
            )
            repair_prompt = (
                "你上一次输出的 JSON 无法写入程序数据库。请只修复 JSON 结构和缺失字段，"
                "不要输出 Markdown、解释或代码块。\n\n"
                f"校验问题：\n{json_dumps(issues)}\n\n"
                f"原始任务：\n{user_prompt}\n\n"
                f"上一次输出：\n{raw}"
            )
            raw = self.complete(repair_prompt, json_mode=True, mock_hint=mock_hint)
            logger.info(
                "AI JSON repair finished agent=%s elapsed=%.1fs",
                self.agent_name,
                time.perf_counter() - started,
            )
            parsed = parse_json_object(raw, default=default)
            if normalizer is not None:
                parsed = normalizer(parsed)
            issues = validator(parsed)
            if not issues:
                return parsed

        raise ValueError("AI 输出 JSON 未通过校验：" + "；".join(issues))
