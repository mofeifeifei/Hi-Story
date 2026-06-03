from __future__ import annotations

from typing import Any, Callable

from app.database.repository import Repository
from app.services.ai_client import AIClient
from app.services.memory_agent import MemoryAgent
from app.services.planner_agent import PlannerAgent
from app.services.reviewer_agent import ReviewerAgent
from app.services.reviser_agent import ReviserAgent
from app.services.writer_agent import WriterAgent
from app.utils.context_filter import filter_chapter_bundle
from app.utils.history import historical_context_for_bundle
from app.utils.json_parser import json_dumps, parse_json_object
from app.utils.name_normalizer import aliases_to_official_map, normalize_bundle_names, normalize_names
from app.utils.outline_utils import (
    blocking_outline_issues,
    parse_outline_detail,
    normalize_chapter_outline,
    outline_text_for_prompt,
    repeat_risk_warnings,
)
from app.utils.text_check import DEFAULT_TEMPLATE_BLACKLIST, blacklist_for_prompt, repeated_text_warnings


class NovelWorkflow:
    def __init__(self, repo: Repository | None = None, client: AIClient | None = None):
        self.repo = repo or Repository()
        self.client = client or AIClient()
        self.planner = PlannerAgent(self.client)
        self.writer = WriterAgent(self.client)
        self.reviewer = ReviewerAgent(self.client)
        self.reviser = ReviserAgent(self.client)
        self.memory = MemoryAgent(self.client)

    def create_work(self, inputs: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        plan = self.planner.generate_work_plan(inputs)
        work_id = self.repo.create_work(inputs, plan)
        self.repo.log_agent_run(
            work_id=work_id,
            chapter_id=None,
            agent_name="planner",
            model=self.client.model_for("planner"),
            prompt_name="planner_prompt.md",
            input_preview=json_dumps(inputs),
            output=json_dumps(plan),
        )
        return work_id, plan

    def generate_outline(self, work_id: int, *, should_stop: Callable[[], bool] | None = None) -> dict[str, Any]:
        bundle = self.normalized_work_bundle(work_id)
        bundle["history_specialist"] = historical_context_for_bundle(bundle)
        outline = self.planner.generate_outline(bundle)
        if should_stop and should_stop():
            raise RuntimeError("任务已停止：全书大纲已返回，但未保存。")
        self.save_generated_outline(work_id, bundle, outline)
        return outline

    def save_generated_outline(self, work_id: int, bundle: dict[str, Any], outline: dict[str, Any]) -> None:
        outline = self.normalize_output_names(work_id, outline)
        self.repo.save_outline(work_id, outline)
        self.repo.log_agent_run(
            work_id=work_id,
            chapter_id=None,
            agent_name="planner",
            model=self.client.model_for("planner"),
            prompt_name="planner_prompt.md",
            input_preview=json_dumps(bundle),
            output=json_dumps(outline),
        )

    def generate_chapter_outlines(
        self,
        work_id: int,
        *,
        start_chapter: int = 1,
        count: int = 30,
        volume_number: int | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        target_volume_number = int(volume_number or self._infer_volume_number(work_id, start_chapter) or 1)
        bundle = self.build_planning_context(
            work_id,
            start_chapter=start_chapter,
            volume_number=target_volume_number,
        )
        result = self.planner.generate_chapter_outlines(
            bundle,
            start_chapter=start_chapter,
            count=count,
            volume_number=target_volume_number,
        )
        if should_stop and should_stop():
            raise RuntimeError("任务已停止：章节细纲已返回，但未保存。")
        return self.save_generated_chapter_outlines(
            work_id,
            result,
            start_chapter=start_chapter,
            count=count,
            volume_number=target_volume_number,
        )

    def save_generated_chapter_outlines(
        self,
        work_id: int,
        result: dict[str, Any],
        *,
        start_chapter: int,
        count: int,
        volume_number: int | None = None,
    ) -> list[dict[str, Any]]:
        result = self.normalize_output_names(work_id, result)
        chapters = result.get("chapters", [])
        target_volume_number = int(volume_number or self._infer_volume_number(work_id, start_chapter) or 1)
        saved: list[dict[str, Any]] = []
        for item in chapters:
            chapter_number = int(item.get("chapter_number") or len(saved) + start_chapter)
            item = self._merge_chapter_outline_fields(work_id, chapter_number, item)
            item["volume_number"] = target_volume_number
            chapter_id = self.repo.upsert_chapter_outline(
                work_id=work_id,
                chapter_number=chapter_number,
                title=item.get("title", f"第{chapter_number}章"),
                outline=item.get("outline", ""),
                ending_hook=item.get("ending_hook", ""),
                outline_json=item,
                protect_written=True,
            )
            item["id"] = chapter_id
            saved.append(item)
        self.repo.log_agent_run(
            work_id=work_id,
            chapter_id=None,
            agent_name="planner",
            model=self.client.model_for("planner"),
            prompt_name="planner_prompt.md",
            input_preview=json_dumps(
                {
                    "work_id": work_id,
                    "start_chapter": start_chapter,
                    "count": count,
                    "volume_number": target_volume_number,
                }
            ),
            output=json_dumps(result),
        )
        return saved

    def _merge_chapter_outline_fields(self, work_id: int, chapter_number: int, item: dict[str, Any]) -> dict[str, Any]:
        try:
            existing = self.repo.get_chapter(work_id, chapter_number)
        except ValueError:
            return item
        previous = parse_outline_detail(existing.get("outline_json"))
        if not previous:
            return item
        merged = dict(previous)
        for key, value in item.items():
            if value not in (None, "", []):
                merged[key] = value
        merged["chapter_number"] = chapter_number
        return merged

    def build_planning_context(
        self,
        work_id: int,
        *,
        start_chapter: int,
        volume_number: int | None = None,
    ) -> dict[str, Any]:
        bundle = self.normalized_work_bundle(work_id)
        work = dict(bundle.get("work") or {})
        allowed_work_keys = [
            "title",
            "idea",
            "genre",
            "platform",
            "target_words",
            "style",
            "summary",
            "reader_profile",
            "forbidden_tropes",
            "protagonist_preference",
            "full_outline",
            "volume_outline",
            "locked_facts",
        ]
        compact_work = {key: work.get(key) for key in allowed_work_keys if work.get(key) not in (None, "")}
        characters = []
        for item in bundle.get("characters", [])[:10]:
            characters.append(
                {
                    "name": item.get("name", ""),
                    "role": item.get("role", ""),
                    "goal": item.get("goal", ""),
                    "current_goal": item.get("current_goal", ""),
                    "current_state": item.get("current_state", ""),
                    "relationship_stage": item.get("relationship_stage", ""),
                    "locked_rules": item.get("locked_rules", ""),
                }
            )
        threads = []
        for item in bundle.get("open_plot_threads", [])[:12]:
            threads.append(
                {
                    "first_chapter": item.get("first_chapter"),
                    "content": item.get("content", ""),
                    "planned_resolve_chapter": item.get("planned_resolve_chapter"),
                }
            )
        context = {
            "work": compact_work,
            "book_contract": bundle.get("book_contract", {}),
            "book_bible": bundle.get("book_bible", {}),
            "characters": characters,
            "world_rules": bundle.get("world_rules", []),
            "historical_profile": bundle.get("historical_profile", {}),
            "historical_facts": bundle.get("historical_facts", []),
            "open_plot_threads": threads,
            "recent_chapter_outlines": self.repo.get_recent_chapter_outlines(work_id, start_chapter, limit=5),
            "recent_summaries": self.repo.get_recent_summaries(work_id, start_chapter, limit=3),
        }
        target_volume_number = int(volume_number or self._infer_volume_number(work_id, start_chapter) or 1)
        context["target_volume_number"] = target_volume_number
        context["target_volume"] = self._volume_info(work.get("volume_outline"), target_volume_number)
        context["history_specialist"] = historical_context_for_bundle(context)
        return self.normalize_output_names(work_id, context)

    def _infer_volume_number(self, work_id: int, chapter_number: int) -> int:
        work = self.repo.get_work(work_id)
        volumes = self._volume_list(work.get("volume_outline"))
        if not volumes:
            return 1
        chapters = self.repo.list_chapter_outlines(work_id)
        if not chapters:
            return int(volumes[0].get("volume_number") or 1)
        per_volume = max(1, (len(chapters) + len(volumes) - 1) // len(volumes))
        index = min(len(volumes) - 1, max(0, (max(1, chapter_number) - 1) // per_volume))
        return int(volumes[index].get("volume_number") or index + 1)

    def _volume_info(self, value: Any, volume_number: int) -> dict[str, Any]:
        for volume in self._volume_list(value):
            if int(volume.get("volume_number") or 0) == int(volume_number):
                return volume
        return {"volume_number": int(volume_number)}

    def _volume_list(self, value: Any) -> list[dict[str, Any]]:
        volumes = value
        if isinstance(volumes, str):
            volumes = parse_json_object(volumes or "[]", default=[])
        if not isinstance(volumes, list):
            return []
        return [dict(item) for item in volumes if isinstance(item, dict)]

    def generate_chapter(
        self,
        work_id: int,
        chapter_number: int,
        *,
        do_review: bool = True,
        do_revise: bool = True,
        do_memory: bool = False,
        should_stop: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        def stop_requested() -> bool:
            return bool(should_stop and should_stop())

        try:
            chapter = self.repo.get_chapter(work_id, chapter_number)
        except ValueError as exc:
            raise ValueError(f"第 {chapter_number} 章不存在，请先在大纲与细纲中新增并填写细纲。") from exc
        outline_issues = blocking_outline_issues(chapter)
        if outline_issues:
            raise ValueError(
                f"第 {chapter_number} 章细纲不合格，不能生成正文："
                + "；".join(outline_issues)
                + "。请先补全细纲。"
            )
        context = self.build_chapter_context(work_id, chapter_number)

        draft = self.writer.write_chapter(context)
        if stop_requested():
            raise RuntimeError("任务已停止：第 {0} 章初稿已返回，但未保存。".format(chapter_number))
        draft_repeat_warnings = self._repeated_text_warnings(work_id, chapter_number, draft)
        if draft_repeat_warnings:
            raise ValueError("本章初稿疑似重复，已停止保存：" + "；".join(draft_repeat_warnings))
        draft = self.normalize_output_names(work_id, draft)
        if str(chapter.get("memory_json") or "").strip():
            self.repo.clear_chapter_memory(work_id, chapter["id"])
            chapter = self.repo.get_chapter(work_id, chapter_number)
        self.repo.save_draft(work_id, chapter["id"], draft)
        self.repo.log_agent_run(
            work_id=work_id,
            chapter_id=chapter["id"],
            agent_name="writer",
            model=self.client.model_for("writer"),
            prompt_name="writer_prompt.md",
            input_preview=json_dumps(context),
            output=draft,
        )

        review: dict[str, Any] | None = None
        if do_review:
            review = self.reviewer.review_chapter(context, draft)
            if stop_requested():
                raise RuntimeError("任务已停止：第 {0} 章审稿已返回，但未继续修订。".format(chapter_number))
            review = self.normalize_output_names(work_id, review)
            self.repo.save_review(work_id, chapter["id"], review)
            self.repo.log_agent_run(
                work_id=work_id,
                chapter_id=chapter["id"],
                agent_name="reviewer",
                model=self.client.model_for("reviewer"),
                prompt_name="reviewer_prompt.md",
                input_preview=json_dumps({"context": context, "draft": draft[:3000]}),
                output=json_dumps(review),
            )

        final_text = draft
        if do_revise and review is not None:
            final_text = self.reviser.revise_chapter(context, draft, review)
            if stop_requested():
                raise RuntimeError("任务已停止：第 {0} 章修订稿已返回，但未保存最终稿。".format(chapter_number))
            final_repeat_warnings = self._repeated_text_warnings(work_id, chapter_number, final_text)
            if final_repeat_warnings:
                raise ValueError("本章修订稿疑似重复，已停止保存：" + "；".join(final_repeat_warnings))
            final_text = self.normalize_output_names(work_id, final_text)
            self.repo.log_agent_run(
                work_id=work_id,
                chapter_id=chapter["id"],
                agent_name="reviser",
                model=self.client.model_for("reviser"),
                prompt_name="reviser_prompt.md",
                input_preview=json_dumps({"context": context, "review": review, "draft": draft[:3000]}),
                output=final_text,
            )

        self.repo.save_final(work_id, chapter["id"], final_text)

        memory_card: dict[str, Any] | None = None
        if do_memory:
            refreshed_context = self.build_chapter_context(work_id, chapter_number)
            memory_card = self.memory.make_memory_card(refreshed_context, final_text)
            if stop_requested():
                raise RuntimeError("任务已停止：第 {0} 章记忆卡已返回，但未入库。".format(chapter_number))
            memory_card = self.normalize_output_names(work_id, memory_card)
            self.repo.apply_memory_card(
                work_id=work_id,
                chapter_id=chapter["id"],
                chapter_number=chapter_number,
                memory=memory_card,
            )
            self.repo.log_agent_run(
                work_id=work_id,
                chapter_id=chapter["id"],
                agent_name="memory",
                model=self.client.model_for("memory"),
                prompt_name="memory_prompt.md",
                input_preview=json_dumps({"context": refreshed_context, "final_text": final_text[:3000]}),
                output=json_dumps(memory_card),
            )

        return {
            "chapter": self.repo.get_chapter(work_id, chapter_number),
            "draft": draft,
            "review": review,
            "final_text": final_text,
            "memory": memory_card,
        }

    def _repeated_text_warnings(self, work_id: int, chapter_number: int, text: str) -> list[str]:
        recent_texts = self.repo.get_recent_chapter_texts(work_id, chapter_number, limit=5)
        return repeated_text_warnings(text, recent_texts)

    def generate_chapters(
        self,
        work_id: int,
        *,
        start_chapter: int,
        count: int,
        do_review: bool = True,
        do_revise: bool = True,
        do_memory: bool = False,
        should_stop: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        results = []
        for chapter_number in range(start_chapter, start_chapter + count):
            if should_stop and should_stop():
                break
            results.append(
                self.generate_chapter(
                    work_id,
                    chapter_number,
                    do_review=do_review,
                    do_revise=do_revise,
                    do_memory=do_memory,
                    should_stop=should_stop,
                )
            )
        return results

    def build_chapter_context(self, work_id: int, chapter_number: int) -> dict[str, Any]:
        chapter = self.repo.get_chapter(work_id, chapter_number)
        outline_detail = normalize_chapter_outline(chapter)
        bundle = filter_chapter_bundle(self.normalized_work_bundle(work_id), outline_detail)
        recent_outlines = self.repo.get_recent_chapter_outlines(work_id, chapter_number, limit=5)
        previous_chapter = self.repo.get_previous_chapter_context(work_id, chapter_number)
        context = {
            **bundle,
            "chapter": {
                "id": chapter["id"],
                "chapter_number": chapter["chapter_number"],
                "title": chapter.get("title", ""),
                "outline": chapter.get("outline", ""),
                "outline_detail": outline_detail,
                "outline_task_sheet": outline_text_for_prompt(outline_detail),
                "ending_hook": chapter.get("ending_hook", ""),
            },
            "recent_three_chapter_summaries": self.repo.get_recent_summaries(work_id, chapter_number, limit=3),
            "recent_chapter_outlines": recent_outlines,
            "repeat_risk_warnings": repeat_risk_warnings(outline_detail, recent_outlines),
            "chapter_notes": self.repo.list_chapter_notes(work_id, chapter_number),
            "previous_chapter": previous_chapter,
            "chapter_transition_contract": self._chapter_transition_contract(previous_chapter),
            "forbidden_template_phrases": DEFAULT_TEMPLATE_BLACKLIST,
            "forbidden_template_guidance": blacklist_for_prompt(),
            "generation_policy": {
                "batch_supported": True,
                "per_chapter_memory_loop": "每章生成后必须审稿、修订、生成记忆卡，再进入下一章。",
                "locked_fact_rule": "锁定设定、人物档案、世界观规则不能擅自修改。",
                "revision_layers": "修订时按结构、情绪、语言三层内部检查，只输出最终正文。",
            },
        }
        context["history_specialist"] = historical_context_for_bundle(context)
        return self.normalize_output_names(work_id, context)

    def _chapter_transition_contract(self, previous_chapter: dict[str, Any] | None) -> dict[str, Any]:
        if not previous_chapter:
            return {}
        handoff = self._handoff_dict(previous_chapter.get("handoff"))
        required_opening = (
            handoff.get("next_first_paragraph_task")
            or handoff.get("next_opening_must_continue")
            or previous_chapter.get("ending_hook")
            or ""
        )
        forbidden_opening = (
            handoff.get("forbidden_opening")
            or handoff.get("forbidden_jump")
            or "禁止跳过上一章结尾，禁止先写天气、时间跳转、回忆或背景说明。"
        )
        return {
            "previous_chapter_number": previous_chapter.get("chapter_number"),
            "previous_title": previous_chapter.get("title", ""),
            "previous_tail": previous_chapter.get("tail", ""),
            "previous_ending_hook": previous_chapter.get("ending_hook", ""),
            "handoff": handoff,
            "required_first_paragraph": required_opening,
            "forbidden_opening": forbidden_opening,
            "must_use_concrete_anchor": (
                handoff.get("active_object")
                or handoff.get("last_external_action")
                or handoff.get("last_spoken_line")
                or handoff.get("current_conflict")
                or previous_chapter.get("ending_hook", "")
            ),
        }

    @staticmethod
    def _handoff_dict(value: Any) -> dict[str, Any]:
        parsed = parse_json_object(value, default={}) if isinstance(value, str) else value
        return parsed if isinstance(parsed, dict) else {}

    def normalized_work_bundle(self, work_id: int) -> dict[str, Any]:
        return normalize_bundle_names(self.repo.get_work_bundle(work_id), strip_aliases=True)

    def name_alias_map(self, work_id: int) -> dict[str, str]:
        return aliases_to_official_map(self.repo.list_characters(work_id))

    def normalize_output_names(self, work_id: int, value: Any) -> Any:
        return normalize_names(value, self.name_alias_map(work_id), strip_aliases=False)

    def _ensure_chapter(self, work_id: int, chapter_number: int) -> dict[str, Any]:
        try:
            return self.repo.get_chapter(work_id, chapter_number)
        except ValueError:
            self.repo.upsert_chapter_outline(
                work_id=work_id,
                chapter_number=chapter_number,
                title=f"第{chapter_number}章",
                outline="承接前文和全书大纲推进本章核心冲突，结尾留下下一章钩子。",
                ending_hook="下一章必须承接本章结尾冲突。",
            )
            return self.repo.get_chapter(work_id, chapter_number)
