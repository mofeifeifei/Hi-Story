from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from typing import Any

from app.utils.config import load_config
from app.utils.history import default_historical_profile, is_historical_inputs


class AIClientError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


class AIClient:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or load_config()
        self._session: Any | None = None

    def model_for(self, agent_name: str) -> str:
        agent_models = self.config.get("agent_models", {})
        if agent_name == "reviewer" and self.config.get("review_model"):
            return str(self.config["review_model"])
        return agent_models.get(agent_name) or self.config.get("default_model", "")

    def complete(
        self,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
        mock_hint: dict[str, Any] | None = None,
    ) -> str:
        api_key = self.config.get("api_key") or os.getenv("NOVEL_AI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if self.config.get("mock_mode", True):
            return self._mock_response(agent_name, user_prompt, json_mode=json_mode, hint=mock_hint or {})
        if self.config.get("requires_openai_auth", True) and not api_key:
            raise AIClientError("缺少 API Key。请在工作台的“设置”页填写，或重新开启 mock 模式。")

        wire_api = str(self.config.get("wire_api", "chat_completions")).lower()
        started = time.perf_counter()
        logger.info(
            "AI request start agent=%s model=%s wire=%s json=%s input_chars=%s",
            agent_name,
            self.model_for(agent_name),
            wire_api,
            json_mode,
            len(system_prompt) + len(user_prompt),
        )
        try:
            if wire_api == "responses":
                return self._call_responses_api(
                    agent_name=agent_name,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    api_key=api_key,
                    json_mode=json_mode,
                )

            return self._call_chat_completions(
                agent_name=agent_name,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                api_key=api_key,
                json_mode=json_mode,
            )
        finally:
            logger.info(
                "AI request end agent=%s elapsed=%.1fs",
                agent_name,
                time.perf_counter() - started,
            )

    def test_connection(self) -> dict[str, Any]:
        if self.config.get("mock_mode", True):
            return {
                "ok": True,
                "message": "当前为 mock 模式，程序流程可用，但没有调用外部 API。",
                "wire_api": self.config.get("wire_api", ""),
                "model": self.model_for("planner"),
            }
        text = self.complete(
            "planner",
            "你是 API 连通性测试助手。只需要回答短句。",
            "请只回复：连接成功",
        )
        return {
            "ok": True,
            "message": text[:200] or "连接成功",
            "wire_api": self.config.get("wire_api", ""),
            "model": self.model_for("planner"),
        }

    def _call_chat_completions(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
        api_key: str,
        json_mode: bool,
    ) -> str:
        try:
            import requests
        except ImportError as exc:
            raise AIClientError("缺少 requests，请先运行 pip install -r requirements.txt") from exc

        base_url = str(self.config.get("base_url", "")).rstrip("/")
        if not base_url:
            raise AIClientError("config.json 缺少 base_url")

        payload: dict[str, Any] = {
            "model": self.model_for(agent_name),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": float(self.config.get("temperature", 0.8)),
        }
        max_output_tokens = int(self.config.get("max_output_tokens", 0) or 0)
        if max_output_tokens > 0:
            payload["max_tokens"] = max_output_tokens
        if json_mode and self._supports_response_format():
            payload["response_format"] = {"type": "json_object"}

        response = self._post_json(
            requests_module=requests,
            url=f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
            api_name="AI Chat Completions API",
        )
        self._raise_for_status(response, "AI Chat Completions API")

        data = self._response_json(response, "AI Chat Completions API")
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIClientError(f"AI Chat Completions API 返回格式异常，程序没有找到正文内容。返回片段：{str(data)[:500]}") from exc

    def _call_responses_api(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_prompt: str,
        api_key: str,
        json_mode: bool,
    ) -> str:
        try:
            import requests
        except ImportError as exc:
            raise AIClientError("缺少 requests，请先运行 pip install -r requirements.txt") from exc

        base_url = str(self.config.get("base_url", "")).rstrip("/")
        if not base_url:
            raise AIClientError("config.json 缺少 base_url")

        payload: dict[str, Any] = {
            "model": self.model_for(agent_name),
            "instructions": system_prompt,
            "input": user_prompt,
        }
        reasoning_effort = str(self.config.get("model_reasoning_effort", "") or "").strip()
        if reasoning_effort and self._supports_reasoning():
            payload["reasoning"] = {"effort": reasoning_effort}
        if self.config.get("disable_response_storage", True) and self._supports_response_storage_flag():
            payload["store"] = False
        if json_mode and self._supports_response_format():
            payload["text"] = {"format": {"type": "json_object"}}
        max_output_tokens = int(self.config.get("max_output_tokens", 0) or 0)
        if max_output_tokens > 0:
            payload["max_output_tokens"] = max_output_tokens

        response = self._post_json(
            requests_module=requests,
            url=f"{base_url}/responses",
            headers=self._headers(api_key),
            payload=payload,
            api_name="AI Responses API",
        )
        self._raise_for_status(response, "AI Responses API")

        data = self._response_json(response, "AI Responses API")
        text = self._extract_response_text(data)
        if text is None:
            raise AIClientError(f"AI Responses API 返回格式异常，程序没有找到正文内容。返回片段：{str(data)[:500]}")
        return text

    def _post_json(
        self,
        *,
        requests_module: Any,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
        api_name: str,
    ) -> Any:
        timeout = int(self.config.get("timeout", 300) or 300)
        max_retries = max(0, int(self.config.get("max_retries", 2) or 0))
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            session = self._requests_session(requests_module)
            session.trust_env = bool(self.config.get("use_system_proxy", False))
            try:
                response = session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                    proxies=self._request_proxies(),
                )
                if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
                    if attempt < max_retries:
                        delay = self._retry_delay(attempt, response)
                        logger.warning(
                            "%s temporary HTTP %s, retry %s/%s after %.1fs",
                            api_name,
                            response.status_code,
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        time.sleep(delay)
                        continue
                return response
            except requests_module.exceptions.RequestException as exc:
                last_error = exc
                if attempt >= max_retries:
                    break
                delay = self._retry_delay(attempt, None)
                logger.warning(
                    "%s request error, retry %s/%s after %.1fs: %s",
                    api_name,
                    attempt + 1,
                    max_retries,
                    delay,
                    exc,
                )
                time.sleep(delay)
        raise AIClientError(self._friendly_request_error(last_error, api_name, url, timeout))

    def _requests_session(self, requests_module: Any) -> Any:
        if self._session is None:
            self._session = requests_module.Session()
        return self._session

    @staticmethod
    def _retry_delay(attempt: int, response: Any | None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), 20.0)
                except ValueError:
                    pass
        return min(2.0 * (2 ** attempt), 20.0)

    def _request_proxies(self) -> dict[str, str] | None:
        proxy_url = str(self.config.get("proxy_url", "") or "").strip()
        if proxy_url:
            return {"http": proxy_url, "https": proxy_url}
        if self.config.get("use_system_proxy", False):
            return None
        return {}

    @staticmethod
    def _response_json(response: Any, api_name: str) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise AIClientError(f"{api_name} 返回的不是合法 JSON。返回片段：{response.text[:500]}") from exc
        if not isinstance(data, dict):
            raise AIClientError(f"{api_name} 返回格式异常，不是 JSON 对象。返回片段：{str(data)[:500]}")
        return data

    @staticmethod
    def _raise_for_status(response: Any, api_name: str) -> None:
        if response.status_code < 400:
            return
        body = response.text[:500]
        lower_body = body.lower()
        if response.status_code == 401:
            message = "API Key 无效或没有被服务接受"
        elif response.status_code == 403:
            message = "API Key 权限不足、账户被限制，或该模型不可用"
        elif response.status_code == 400 and ("not supported model" in lower_body or "model" in lower_body):
            message = (
                "请求参数错误：当前 Base URL 不支持所填写的模型名称。"
                "请在服务商后台或文档中确认模型 ID，并把“主模型”和高级设置里的 Agent 模型改成受支持的精确名称"
            )
        elif response.status_code == 400:
            message = "请求参数错误，请检查模型名称、Wire API、最大输出 Token、推理强度等配置是否被当前服务商支持"
        elif response.status_code == 404:
            message = "接口地址不存在，请检查 Base URL 和 Wire API 是否匹配"
        elif response.status_code == 408:
            message = "服务端等待超时"
        elif response.status_code == 429:
            message = "请求过于频繁或额度不足"
        elif response.status_code >= 500:
            message = "服务端或中转网关异常"
        else:
            message = "HTTP 请求失败"
        raise AIClientError(f"{api_name} 调用失败：{response.status_code}，{message}。返回片段：{body}")

    @staticmethod
    def _friendly_request_error(exc: Exception | None, api_name: str, url: str, timeout: int) -> str:
        if exc is None:
            return f"{api_name} 调用失败：未知网络错误。"
        exc_name = exc.__class__.__name__
        detail = str(exc)
        lower_detail = detail.lower()
        if "proxy" in exc_name.lower() or "proxy" in lower_detail:
            reason = "代理连接失败。程序请求外部 API 时经过了代理，但代理没有正确转发请求，或被远端断开。"
            advice = "请在设置页关闭“使用系统代理”，或填写可用的代理地址；也可以把 Wire API 切到 chat_completions 再测试。"
        elif "read timed out" in lower_detail or "readtimeout" in exc_name.lower():
            reason = f"读取超时。外部 API 在 {timeout} 秒内没有返回完整结果。"
            advice = "请把超时时间调大，降低推理强度，或减少一次生成的章节数量。"
        elif "connecttimeout" in exc_name.lower() or "timed out" in lower_detail:
            reason = f"连接超时。程序在 {timeout} 秒内没有连上 API 服务。"
            advice = "请检查网络、Base URL、代理设置，或稍后重试。"
        elif "ssl" in exc_name.lower() or "certificate" in lower_detail:
            reason = "SSL / 证书校验失败。"
            advice = "请检查系统时间、代理证书和 Base URL 是否正确。"
        elif "connection" in exc_name.lower() or "remote end closed" in lower_detail:
            reason = "连接被远端关闭。API 服务或中转网关没有返回完整响应。"
            advice = "请稍后重试；如果一直失败，尝试切换 Wire API 或检查 tokenflux.dev 服务状态。"
        else:
            reason = "网络请求失败。"
            advice = "请检查 Base URL、网络连接、代理设置和 API 服务状态。"
        return f"{api_name} 调用失败：{reason}\n请求地址：{url}\n建议：{advice}\n原始错误：{detail[:500]}"

    def _headers(self, api_key: str) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.get("requires_openai_auth", True):
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _provider_name(self) -> str:
        return str(self.config.get("model_provider") or self.config.get("provider") or "").strip().lower()

    def _supports_response_format(self) -> bool:
        if "supports_response_format" in self.config:
            return bool(self.config.get("supports_response_format"))
        provider = self._provider_name()
        return provider not in {"deepseek"}

    def _supports_reasoning(self) -> bool:
        if "supports_reasoning" in self.config:
            return bool(self.config.get("supports_reasoning"))
        provider = self._provider_name()
        return provider in {"openai", "tokenflux"}

    def _supports_response_storage_flag(self) -> bool:
        if "supports_response_storage_flag" in self.config:
            return bool(self.config.get("supports_response_storage_flag"))
        provider = self._provider_name()
        return provider in {"openai", "tokenflux"}

    def _extract_response_text(self, data: dict[str, Any]) -> str | None:
        output_text = data.get("output_text")
        if isinstance(output_text, str):
            return output_text

        chunks: list[str] = []
        for output in data.get("output", []) or []:
            for item in output.get("content", []) or []:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
                    elif isinstance(item.get("output_text"), str):
                        chunks.append(item["output_text"])
        if chunks:
            return "".join(chunks)
        return None

    def _mock_response(
        self,
        agent_name: str,
        user_prompt: str,
        *,
        json_mode: bool,
        hint: dict[str, Any],
    ) -> str:
        seed = self._seed(user_prompt)
        if agent_name == "planner":
            task = hint.get("task", "")
            if task == "work_plan":
                return json.dumps(self._mock_work_plan(user_prompt), ensure_ascii=False, indent=2)
            if task == "outline":
                return json.dumps(self._mock_outline(user_prompt), ensure_ascii=False, indent=2)
            if task == "chapter_outlines":
                count = int(hint.get("count", 1))
                start = int(hint.get("start_chapter", 1))
                volume_number = int(hint.get("volume_number") or 0)
                return json.dumps(
                    self._mock_chapter_outlines(user_prompt, start, count, volume_number),
                    ensure_ascii=False,
                    indent=2,
                )

        if agent_name == "writer":
            chapter_number = int(hint.get("chapter_number", 1))
            title = hint.get("title") or f"第{chapter_number}章"
            return self._mock_chapter_text(user_prompt, chapter_number, title, seed)

        if agent_name == "reviewer":
            return json.dumps(self._mock_review(hint), ensure_ascii=False, indent=2)

        if agent_name == "reviser":
            return self._mock_revision(hint)

        if agent_name == "memory":
            chapter_number = int(hint.get("chapter_number", 1))
            return json.dumps(self._mock_memory(user_prompt, chapter_number), ensure_ascii=False, indent=2)

        return "{}" if json_mode else "Mock response"

    @staticmethod
    def _seed(text: str) -> int:
        digest = hashlib.md5(text.encode("utf-8")).hexdigest()
        return int(digest[:8], 16)

    @staticmethod
    def _extract_label(user_prompt: str, label: str, fallback: str = "") -> str:
        pattern = rf"{re.escape(label)}[:：]\s*(.+)"
        match = re.search(pattern, user_prompt)
        if not match:
            return fallback
        return match.group(1).splitlines()[0].strip().strip('"')

    @staticmethod
    def _extract_first_json(user_prompt: str) -> dict[str, Any]:
        starts = [idx for idx in [user_prompt.find("{"), user_prompt.find("[")] if idx != -1]
        if not starts:
            return {}
        decoder = json.JSONDecoder()
        for start in sorted(starts):
            try:
                value, _ = decoder.raw_decode(user_prompt[start:])
            except json.JSONDecodeError:
                continue
            return value if isinstance(value, dict) else {}
        return {}

    @staticmethod
    def _first_text(*values: Any, fallback: str = "") -> str:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return fallback

    @staticmethod
    def _short_text(value: str, fallback: str, *, limit: int = 18) -> str:
        cleaned = re.sub(r"\s+", "", value or "")
        cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "", cleaned)
        return cleaned[:limit] or fallback

    def _mock_profile(self, user_prompt: str) -> dict[str, str]:
        data = self._extract_first_json(user_prompt)
        work = data.get("work") if isinstance(data.get("work"), dict) else {}
        chapter = data.get("chapter") if isinstance(data.get("chapter"), dict) else {}
        characters = data.get("characters") if isinstance(data.get("characters"), list) else []
        first_character = characters[0] if characters and isinstance(characters[0], dict) else {}
        second_character = characters[1] if len(characters) > 1 and isinstance(characters[1], dict) else {}

        title = self._first_text(
            work.get("title"),
            self._extract_label(user_prompt, "作品名称"),
            fallback="未命名作品",
        )
        idea = self._first_text(
            work.get("idea"),
            self._extract_label(user_prompt, "一句话创意"),
            fallback="主角被卷入一条长期主线，并必须在选择与代价之间推进目标。",
        )
        genre = self._first_text(work.get("genre"), self._extract_label(user_prompt, "题材"), fallback="长篇小说")
        platform = self._first_text(work.get("platform"), self._extract_label(user_prompt, "目标平台"), fallback="目标平台")
        protagonist = self._first_text(first_character.get("name"), fallback="主角")
        partner = self._first_text(second_character.get("name"), fallback="重要同伴")
        obstacle = "阶段阻力"
        rule = "核心规则"
        if isinstance(data.get("world_rules"), list) and data["world_rules"]:
            first_rule = data["world_rules"][0]
            if isinstance(first_rule, dict):
                rule = self._first_text(first_rule.get("rule_name"), fallback=rule)
        chapter_title = self._first_text(chapter.get("title"), fallback="")
        return {
            "title": title,
            "idea": idea,
            "genre": genre,
            "platform": platform,
            "protagonist": protagonist,
            "partner": partner,
            "obstacle": obstacle,
            "rule": rule,
            "chapter_title": chapter_title,
        }

    def _mock_title_candidates(self, title: str, idea: str, genre: str) -> list[str]:
        base = self._short_text(title, "未命名作品") if title != "未命名作品" else self._short_text(idea, "未命名长篇", limit=10)
        genre_key = self._short_text(genre, "长篇", limit=6)
        candidates = [base, f"{base}纪事", f"{genre_key}主线"]
        deduped: list[str] = []
        for item in candidates:
            if item and item not in deduped:
                deduped.append(item)
        return deduped

    def _mock_work_plan(self, user_prompt: str) -> dict[str, Any]:
        profile = self._mock_profile(user_prompt)
        idea = profile["idea"]
        genre_text = profile["genre"]
        platform_text = profile["platform"]
        title = profile["title"]
        historical_profile = (
            default_historical_profile({"idea": idea, "genre": genre_text, "prompt": user_prompt})
            if is_historical_inputs({"idea": idea, "genre": genre_text, "prompt": user_prompt})
            else {}
        )
        return {
            "book_bible": {
                "core_reading_promise": f"围绕“{idea}”持续兑现读者期待，每一阶段都给出明确目标、阻力、代价和新信息。",
                "primary_genre": genre_text,
                "secondary_genres": ["人物成长", "关系推进", "长篇连载"],
                "emotional_tone": "节奏清晰、情绪递进、冲突有代价",
                "narrative_driver": "阶段目标、人物选择、关系变化、伏笔回收和更大的主线问题共同驱动追读。",
                "protagonist_end_goal": "完成核心目标，同时付清前期选择带来的代价，并改变自己与关键关系的状态。",
                "long_form_engine": "每卷提出新的阶段问题，每章提供可见进展和结尾接力棒，避免原地打转。",
                "must_keep_rules": ["重要设定必须前后一致", "关键胜利必须付出代价", "伏笔必须有计划地回收"],
                "forbidden_drift": ["禁止把主角写成无代价万能解法", "禁止跳过关键冲突直接给结果"],
                "ending_direction": "结局回收主线问题、人物成长和关键伏笔，保留与题材相符的余味。",
            },
            "title_candidates": self._mock_title_candidates(title, idea, genre_text),
            "summary": f"{idea}。在{genre_text}框架下，主角从一个具体问题切入，逐步卷入更大的长期主线，并在选择、关系和代价中完成成长。",
            "core_selling_points": [
                "每章都有明确目标、阻力和信息增量，方便测试连载流程",
                f"节奏适配{platform_text}读者：开篇进入事件，章末保留下一步行动钩子",
                "人物关系和主线伏笔同步推进，避免只有事件没有变化",
            ],
            "target_readers": [f"喜欢{genre_text}的读者", "喜欢长篇主线和人物成长的读者"],
            "protagonist": {
                "name": "主角",
                "role": "主角",
                "personality": "目标感强，面对压力时会先寻找可执行路径",
                "goal": "解决当前主线问题，并弄清背后更大的原因",
                "secret": "曾经做过一次影响后续选择的错误判断",
                "speaking_style": "表达直接，遇到关键问题会追问到底",
                "relationship": "与重要同伴从试探合作逐步走向互相信任",
                "locked_rules": "不能无代价解决所有问题，必须受世界观和人物能力边界限制",
            },
            "supporting_characters": [
                {
                    "name": "重要同伴",
                    "role": "主角的阶段盟友",
                    "personality": "理性谨慎，重视事实和结果",
                    "goal": "确认主角的判断是否值得继续投入",
                    "secret": "与主线问题存在尚未公开的旧关联",
                    "speaking_style": "先指出风险，再给出可执行建议",
                    "relationship": "从互相试探走向有限信任",
                    "locked_rules": "不会无条件配合主角，必须看到行动价值",
                }
            ],
            "villains": [
                {
                    "name": "阶段阻力",
                    "role": "阶段反派或外部压力",
                    "personality": "善于利用信息差和规则漏洞",
                    "goal": "阻止主角接近阶段目标",
                    "secret": "背后还有更深层的主线动机",
                    "speaking_style": "回避正面答案，用条件和代价施压",
                    "relationship": "与第一卷核心冲突相关",
                    "locked_rules": "不能过早暴露最终动机",
                }
            ],
            "world_rules": [
                {
                    "rule_name": "核心规则",
                    "rule_content": "主角推进目标时必须遵守当前题材和世界观建立的限制。",
                    "limitations": "线索、资源或能力只能提供阶段性帮助，不能替代选择、行动和代价。",
                    "forbidden_changes": "不能临时新增万能设定解决冲突，不能推翻已锁定设定。",
                }
            ],
            "main_goal": "让主角从当前创意中的核心问题出发，逐步逼近主线真相或最终目标。",
            "first_volume_direction": "第一卷建立世界观规则、核心关系和阶段目标，在卷末确认更大的主线问题仍未解决。",
            "historical_profile": historical_profile,
        }

    def _mock_outline(self, user_prompt: str) -> dict[str, Any]:
        profile = self._mock_profile(user_prompt)
        protagonist = profile["protagonist"]
        partner = profile["partner"]
        obstacle = profile["obstacle"]
        idea = profile["idea"]
        return {
            "full_outline": (
                f"第一阶段从“{idea}”切入，{protagonist}先面对一个可以立刻行动的问题。这个阶段重点建立世界观规则、主角的能力边界或资源边界，以及读者最需要追下去的主线疑问。\n\n"
                f"第二阶段扩大冲突范围，{partner}与{protagonist}形成有限合作，但双方目标并不完全一致。新的证据或事件会证明早期判断不完整，迫使主角付出更具体的代价。\n\n"
                f"第三阶段让{obstacle}主动反击，前期伏笔开始回收，同时暴露主角过去选择的后果。人物关系进入拉扯期，主角必须在短期胜利和长期目标之间做选择。\n\n"
                "第四阶段收束主线问题，关键伏笔被重新解释，人物成长完成最终转折。结局不靠临时新增设定，而是用已经建立的规则、关系和代价完成最终解决。"
            ),
            "volume_outline": [
                {
                    "volume_number": 1,
                    "title": "主线启动",
                    "target_chapters": 10,
                    "min_chapters": 6,
                    "soft_max_chapters": 12,
                    "hard_max_chapters": 15,
                    "entry_condition": "主角被迫进入核心事件，明确第一阶段行动目标。",
                    "exit_condition": "第一阶段追读问题获得阶段进展，并确认更大的主线问题存在。",
                    "required_milestones": ["主角被迫进入事件", "重要同伴提出条件", "第一条线索被证伪"],
                    "goal": "建立核心设定、人物目标和第一阶段追读问题。",
                    "main_conflict": f"{protagonist}必须在信息不足和资源有限的情况下完成第一次关键推进。",
                    "turning_points": ["主角被迫进入事件", "重要同伴提出条件", "第一条线索被证伪", "阶段阻力主动施压"],
                    "ending": "阶段目标取得进展，但更大的主线问题被确认存在。",
                },
                {
                    "volume_number": 2,
                    "title": "冲突扩张",
                    "target_chapters": 12,
                    "min_chapters": 8,
                    "soft_max_chapters": 15,
                    "hard_max_chapters": 18,
                    "entry_condition": "主角确认第一阶段问题背后存在更大的结构性阻力。",
                    "exit_condition": "隐藏规则第一次显形，主角以代价换到进入下一阶段的关键机会。",
                    "required_milestones": ["早期判断出现偏差", "同伴关系短暂破裂", "隐藏规则第一次显形"],
                    "goal": "扩大舞台，揭示早期线索背后的真实结构。",
                    "main_conflict": f"{protagonist}想继续推进，{obstacle}则利用规则漏洞制造误导。",
                    "turning_points": ["早期判断出现偏差", "同伴关系短暂破裂", "隐藏规则第一次显形", "主角以代价换到关键机会"],
                    "ending": "主角确认自己面对的不是单点事件，而是一条持续运转的主线。",
                },
                {
                    "volume_number": 3,
                    "title": "代价反噬",
                    "target_chapters": 12,
                    "min_chapters": 8,
                    "soft_max_chapters": 15,
                    "hard_max_chapters": 18,
                    "entry_condition": "主角过去的做法开始反噬，短期解法无法继续覆盖长期矛盾。",
                    "exit_condition": "主角承认旧方法失效，并找到改变解决问题方式的入口。",
                    "required_milestones": ["关键伏笔反向解释", "主角失去重要资源", "同伴做出独立选择"],
                    "goal": "回收前期伏笔，让人物选择带来后果。",
                    "main_conflict": "主角过去的做法开始反噬，短期解法无法继续覆盖长期矛盾。",
                    "turning_points": ["关键伏笔反向解释", "主角失去重要资源", "同伴做出独立选择", "阶段阻力暴露更高层目标"],
                    "ending": "主角承认旧方法失效，必须改变解决问题的方式。",
                },
                {
                    "volume_number": 4,
                    "title": "最终收束",
                    "target_chapters": 10,
                    "min_chapters": 6,
                    "soft_max_chapters": 12,
                    "hard_max_chapters": 15,
                    "entry_condition": "主角获得完整真相和最终行动条件。",
                    "exit_condition": "主线问题被解决，人物关系和世界状态进入新的平衡。",
                    "required_milestones": ["最终目标被重新定义", "同伴关系完成确认", "关键规则被用到极限"],
                    "goal": "完成主线问题、人物成长和核心伏笔回收。",
                    "main_conflict": "主角必须在完整真相和最终代价之间做出不可撤销的选择。",
                    "turning_points": ["最终目标被重新定义", "同伴关系完成确认", "关键规则被用到极限", "主角承担最终代价"],
                    "ending": "主线问题被解决，人物关系和世界状态进入新的平衡。",
                },
            ],
        }

    def _mock_chapter_outlines(self, user_prompt: str, start: int, count: int, volume_number: int = 0) -> dict[str, Any]:
        profile = self._mock_profile(user_prompt)
        protagonist = profile["protagonist"]
        partner = profile["partner"]
        obstacle = profile["obstacle"]
        base_titles = [
            "新的缺口",
            "被打断的计划",
            "不一致的证词",
            "临时同盟",
            "必须支付的代价",
        ]
        goals = [
            f"让{protagonist}确认当前阶段的第一个可执行目标，并建立限制条件。",
            "让原定计划被外部压力打断，迫使主角调整行动路径。",
            "用互相冲突的信息制造判断压力，推动主角重新审视早期结论。",
            f"让{partner}以条件交换方式参与行动，关系从试探进入有限合作。",
            "让主角用一个具体代价换取关键进展，并把下一章问题抬高。",
        ]
        conflicts = [
            f"{protagonist}掌握的信息不足以直接证明判断，只能先找到可落地的行动切口。",
            f"{obstacle}提前封住一条路线，主角必须在时间压力下寻找替代证据或资源。",
            "新的信息指向错误目标，主角需要分辨误导和真正的信息增量。",
            f"{partner}愿意帮忙，但要求主角公开一部分动机或承担一个风险。",
            "关键机会即将消失，主角必须在保全自己和推进主线之间做选择。",
        ]
        scenes = ["主线事件现场", "临时会面地点", "关键资料所在处", "冲突公开爆发点", "下一阶段入口"]
        chapters = []
        for number in range(start, start + count):
            index = (number - 1) % len(base_titles)
            title = base_titles[index]
            chapters.append(
                {
                    "chapter_number": number,
                    "volume_number": volume_number or max(1, (number - 1) // 10 + 1),
                    "story_time": f"第{number}章对应的故事时间段，紧接上一章后推进",
                    "title": title,
                    "opening_hook": f"前 300 字从{protagonist}发现“{title}”相关异常开始，让冲突和行动先出现，再补充背景。",
                    "outline": (
                        f"第{number}章在{scenes[index]}展开。{goals[index]}主角需要面对的阻力是："
                        f"{conflicts[index]}本章必须给出一个新的行动结果，同时保留尚未解决的下一步问题。"
                    ),
                    "scene_cards": [
                        {
                            "scene_goal": f"在{scenes[index]}确认上一章留下的新线索",
                            "obstacle": "线索不完整，相关人物也在回避关键信息",
                            "information_gain": f"发现“{title}”不是孤立事件，而是阶段目标的一部分",
                            "emotional_shift": "从迟疑转向必须主动试探",
                            "scene_exit": f"{protagonist}找到一个可以继续推进的切口",
                        },
                        {
                            "scene_goal": f"让{partner}判断是否继续配合{protagonist}",
                            "obstacle": "同伴需要看到行动价值，而不是只听主角解释",
                            "information_gain": "两人确认当前目标背后还有更大的限制条件",
                            "emotional_shift": "互相试探转为有限信任",
                            "scene_exit": "两人决定先处理最能验证判断的一步",
                        },
                        {
                            "scene_goal": "把本章钩子落到具体发现上",
                            "obstacle": "证据即将被清理或转移",
                            "information_gain": f"“{title}”指向一个尚未登场的关键条件",
                            "emotional_shift": "紧迫感压过犹豫",
                            "scene_exit": "下一章必须从验证新条件开始",
                        },
                    ],
                    "chapter_goal": goals[index],
                    "reader_expectation": f"读者会期待{protagonist}如何把零散信息转化成可执行行动。",
                    "conflict": conflicts[index],
                    "main_scene": scenes[index],
                    "characters_present": f"{protagonist}、{partner}、与本章目标相关的人物",
                    "clues": ["异常记录", "矛盾信息", title],
                    "new_information": f"{title}不是孤立线索，而是阶段主线中的一块拼图。",
                    "chapter_payoff": "本章给出一次可见进展，同时证明主角无法绕过规则和代价。",
                    "character_change": f"{protagonist}更清楚当前方法的限制，{partner}对继续合作产生保留信任。",
                    "foreshadowing": "早期异常会在后续章节被重新解释，但本章不能提前揭开最终答案。",
                    "emotional_turn": "从发现异常的压迫感，转向必须抢在证据被清理前行动的紧迫感。",
                    "emotional_rhythm": "开场压迫，中段推理拉扯，结尾以新证据制造紧迫感。",
                    "ending_hook": f"{protagonist}刚把“{title}”相关证据按到灯下，门外就有人敲门索要这份证据。",
                    "handoff": f"下一章第一段必须从门外敲门声和桌上的“{title}”证据承接，写{protagonist}如何保护或交出证据；禁止跳到次日或直接给出最终答案。",
                    "forbidden": "禁止临时新增万能设定解决冲突，禁止重复同一开场场景。",
                }
            )
        return {"chapters": chapters}

    def _mock_chapter_text(self, user_prompt: str, chapter_number: int, title: str, seed: int) -> str:
        profile = self._mock_profile(user_prompt)
        protagonist = profile["protagonist"]
        partner = profile["partner"]
        rule = profile["rule"]
        scenes = [
            ("主线事件现场", "第一条线索并不完整", "记录末尾多出一个从未出现过的名字"),
            ("临时会面地点", "原定计划被提前打断", "门外传来一段不该被公开的录音"),
            ("关键资料所在处", "证据和证词互相矛盾", "资料背面留下了下一阶段入口"),
            ("冲突公开爆发点", "同伴提出了合作条件", "人群里有人说出了主角没有公开过的信息"),
            ("下一阶段入口", "胜利需要支付代价", "通往下一步的门只打开了一半"),
        ]
        scene, clue, hook = scenes[(chapter_number + seed) % len(scenes)]
        return (
            f"{scene}比{protagonist}预想得更安静。桌面上只有编号 A-{chapter_number:03d} 的记录，"
            f"旁边压着一张被折过两次的纸，纸上写着：{clue}。\n\n"
            f"这句话不足以解释全部问题，却足够推翻上一章留下的判断。{rule}在这里第一次显出边界："
            "它能提供方向，却不能替主角完成选择。\n\n"
            f"{partner}没有立刻表态，只把记录推回主角面前：“如果你要继续，就拿出一个能让别人相信的理由。”\n\n"
            f"{protagonist}看着那行字，意识到真正的阻力不是没有线索，而是每一条线索都要求他付出新的代价。"
            "他可以暂时隐瞒动机，也可以立刻把风险摊开，但两种选择都会改变接下来的关系。\n\n"
            "短暂的沉默后，他把最关键的一页抽出来，按在灯下。纸面背后透出另一层字迹，"
            "像是有人故意把答案留在看得见却不能直接拿走的位置。\n\n"
            f"下一秒，{hook}。\n"
        )

    @staticmethod
    def _mock_review(hint: dict[str, Any]) -> dict[str, Any]:
        template_hits = hint.get("template_hits", [])
        historical_hits = [
            item
            for item in template_hits
            if "历史穿帮" in str(item.get("phrase", "") if isinstance(item, dict) else item)
        ]
        historical_enabled = bool(hint.get("historical_enabled"))
        problems = [
            "核心规则需要在后续章节继续保持限制，不能让主角无代价解决问题。",
            "主角与重要同伴的互信还应保持递进，不宜推进过快。",
        ]
        if historical_hits:
            problems.append("本章存在疑似现代词或后世概念误入，需要按历史设定卡逐条替换。")
        return {
            "continuity_score": 86,
            "character_score": 88,
            "emotion_score": 80,
            "rhythm_score": 84,
            "foreshadow_score": 82,
            "payoff_score": 84,
            "hook_score": 83,
            "historical_score": 62 if historical_hits else (90 if historical_enabled else 0),
            "readability_score": 82,
            "repeat_risk": hint.get("repeat_risk", []),
            "problems": problems,
            "suggestions": [
                "保留本章结尾的新条件作为下一章承接点。",
                "下一章应继续验证新线索，并让早期异常成为可回收伏笔。",
            ],
            "template_hits": template_hits,
            "risk_flags": [],
        }

    @staticmethod
    def _mock_revision(hint: dict[str, Any]) -> str:
        draft = hint.get("draft") or ""
        if not draft:
            return "修订稿为空：没有收到初稿。"
        return draft.replace("那不是完整的句子，更像", "那声音不成句，更像")

    def _mock_memory(self, user_prompt: str, chapter_number: int) -> dict[str, Any]:
        profile = self._mock_profile(user_prompt)
        protagonist = profile["protagonist"]
        partner = profile["partner"]
        final_text = ""
        marker = "最终稿："
        if marker in user_prompt:
            final_text = user_prompt.split(marker, 1)[1].strip()
        excerpt = self._first_text(final_text.splitlines()[0] if final_text else "", fallback=f"第{chapter_number}章")
        historical_updates = []
        if is_historical_inputs({"prompt": user_prompt}):
            historical_updates = [
                {
                    "category": "虚构边界",
                    "content": "本章新增或沿用的历史细节必须继续服从当前历史设定卡，不能混入现代制度和现代器物。",
                    "chapter_impact": "后续章节写同一场景、称谓、官制或生活细节时需要保持一致。",
                    "future_constraint": "下一章承接时优先检查称谓、交通、通信、器物和制度是否符合时代背景。",
                }
            ]
        return {
            "summary": f"{protagonist}在《{excerpt}》中确认了一条新的阶段线索，但线索不足以直接解决问题。{partner}要求看到更可靠的行动理由，双方关系从观望进入有限合作，同时下一章留下新的验证任务。",
            "character_changes": [
                f"{protagonist}意识到单靠直觉或资源不足以推进主线，必须把判断转化为可执行行动。",
                f"{partner}对主角的判断保留疑虑，但愿意继续观察并提供有限帮助。",
            ],
            "character_state_updates": [
                {
                    "name": protagonist,
                    "current_goal": "验证本章留下的新条件，并找到下一步可执行切口",
                    "current_fear": "再次因为信息不完整做出错误判断",
                    "current_state": "掌握部分线索，但仍受规则和外部压力限制",
                    "relationship_stage": f"与{partner}建立有限合作",
                    "secret_exposure": "部分动机或判断方式被同伴察觉，但尚未完全公开",
                    "arc_stage": "主线启动后的推进阶段",
                    "arc_notes": f"第{chapter_number}章后意识到推进目标必须付出具体代价",
                }
            ],
            "new_foreshadows": [
                {
                    "content": "本章出现的异常记录可能与更大的阶段阻力有关。",
                    "planned_resolve_chapter": chapter_number + 4,
                }
            ],
            "resolved_foreshadows": [],
            "timeline_events": [
                {
                    "story_time": f"第{chapter_number}章当前时间段",
                    "event": f"{protagonist}确认新的阶段线索，并与{partner}形成有限合作。",
                    "characters_involved": f"{protagonist}, {partner}",
                }
            ],
            "ability_changes": [],
            "relationship_changes": [f"{protagonist}与{partner}从试探转向有限合作。"],
            "historical_updates": historical_updates,
            "ending_hook": "本章结尾出现新的验证条件，下一章必须从现场继续处理。",
            "handoff": {
                "current_scene": "本章结尾的新线索现场",
                "current_time": f"第{chapter_number}章结尾后",
                "current_characters": [protagonist, partner],
                "current_conflict": "新条件已经出现，但证据、动机或资源仍不完整。",
                "unresolved_questions": ["新条件是谁留下的", "阶段阻力真正目的是什么", "主角需要付出什么代价"],
                "next_opening_must_continue": "从本章结尾的新条件继续验证，不能直接跳到阶段结果。",
                "forbidden_jump": "禁止跳过验证过程，禁止直接揭露最终答案。",
                "last_external_action": f"{protagonist}把关键线索按在灯下，准备验证背后的第二层信息。",
                "last_spoken_line": "",
                "active_object": "灯下的关键线索",
                "open_conflict": "线索已经暴露，但还没有完成验证，外部压力可能随时打断。",
                "next_first_paragraph_task": f"下一章第一段从{protagonist}继续查看灯下线索写起，让{partner}立刻追问或阻止，不能先跳时间。",
                "forbidden_opening": "禁止以天气、次日、回忆、背景介绍或新地点开头。",
                "ending_style": "证据出现",
            },
        }
