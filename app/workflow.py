from __future__ import annotations

from typing import Any, Callable

from app.database.repository import Repository
from app.database.repository_legacy import now_text
from app.services.ai_client import AIClient
from app.services.base_agent import JsonValidationError
from app.services.memory_agent import MemoryAgent
from app.services.planner_agent import PlannerAgent
from app.services.reviewer_agent import ReviewerAgent
from app.services.reviser_agent import ReviserAgent
from app.services.writer_agent import WriterAgent
from app.utils.context_filter import (
    compact_genre_contract,
    context_for_memory,
    context_for_reviewer,
    context_for_reviser,
    filter_chapter_bundle,
)
from app.utils.history import historical_context_for_bundle
from app.utils.json_parser import json_dumps, parse_json_object
from app.utils.name_normalizer import aliases_to_official_map, normalize_bundle_names, normalize_names
from app.utils.outline_utils import (
    blocking_outline_issues,
    duplicate_outline_groups,
    parse_outline_detail,
    normalize_chapter_outline,
    outline_text_for_prompt,
    repeat_risk_warnings,
)
from app.utils.text_check import (
    DEFAULT_TEMPLATE_BLACKLIST,
    blacklist_for_prompt,
    detect_opening_mode,
    ending_signature,
    first_paragraph,
    last_screen,
    manuscript_quality_report,
    opening_ending_repair_issues,
    opening_pattern_flags,
    opening_pattern_label,
    opening_signature,
    quality_summary,
    repeated_text_warnings,
    rhetorical_pattern_flags,
    style_guard_warnings,
    style_regression_warnings,
)
from app.utils.text_cleaner import strip_chapter_heading
from app.utils.word_target import chapter_word_target_from_style


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
            **self.client.last_usage("planner"),
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
            **self.client.last_usage("planner"),
        )

    def generate_chapter_outlines(
        self,
        work_id: int,
        *,
        start_chapter: int = 1,
        count: int = 30,
        volume_number: int | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        bundle = self.build_planning_context(
            work_id,
            start_chapter=start_chapter,
            volume_number=volume_number,
        )
        try:
            result = self.planner.generate_chapter_outlines(
                bundle,
                start_chapter=start_chapter,
                count=count,
                volume_number=volume_number,
            )
        except JsonValidationError as exc:
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
                        "volume_number": volume_number,
                    }
                ),
                output=exc.raw or json_dumps(exc.parsed),
                status="failed",
                error=str(exc),
                **self.client.last_usage("planner"),
            )
            raise
        if should_stop and should_stop():
            raise RuntimeError("任务已停止：章节细纲已返回，但未保存。")
        return self.save_generated_chapter_outlines(
            work_id,
            result,
            start_chapter=start_chapter,
            count=count,
            volume_number=volume_number,
        )

    def save_generated_chapter_outlines(
        self,
        work_id: int,
        result: dict[str, Any],
        *,
        start_chapter: int,
        count: int,
        volume_number: int | None = None,
    ) -> dict[str, Any]:
        result = self.normalize_output_names(work_id, result)
        chapters = [dict(item) for item in result.get("chapters", []) if isinstance(item, dict)]
        if not chapters:
            raise ValueError("AI 没有返回可保存的章节细纲，请重新生成。")
        volume_state = self._volume_state(work_id)
        initial_active_volume = int(volume_state.get("active_volume") or 1)
        volume_decision = self._validated_volume_decision(
            volume_state,
            result.get("volume_decision"),
            explicit_volume=volume_number,
        )
        prepared: list[dict[str, Any]] = []
        for offset, item in enumerate(chapters[:count]):
            chapter_number = start_chapter + offset
            item["chapter_number"] = chapter_number
            item = self._merge_chapter_outline_fields(work_id, chapter_number, item)
            item["chapter_number"] = chapter_number
            if offset == 0 and volume_decision.get("applied") and volume_decision.get("to_volume"):
                item["volume_number"] = int(volume_decision["to_volume"])
            item["volume_number"] = self._assign_volume_number(
                volume_state,
                chapter_number,
                int(item.get("volume_number") or 0),
                explicit_volume=volume_number,
            )
            blockers = blocking_outline_issues(item)
            if blockers:
                raise ValueError(f"第 {chapter_number} 章细纲未通过结构校验：" + "；".join(blockers))
            prepared.append(item)
            self._advance_volume_state(volume_state, chapter_number, int(item["volume_number"]))
        duplicate_groups = duplicate_outline_groups(prepared)
        if duplicate_groups:
            labels = ["、".join(f"第{number}章" for number in group) for group in duplicate_groups]
            raise ValueError("本批细纲存在重复章节结构：" + "；".join(labels))

        saved: list[dict[str, Any]] = []
        for item in prepared:
            chapter_number = int(item["chapter_number"])
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
                    "volume_number": volume_number,
                }
            ),
            output=json_dumps(result),
            **self.client.last_usage("planner"),
        )
        return {
            "chapters": saved,
            "volume_transition": self._volume_transition_notice(volume_state, volume_decision, saved, initial_active_volume),
            "volume_decision": volume_decision,
        }

    def _volume_state(self, work_id: int) -> dict[str, Any]:
        work = self.repo.get_work(work_id)
        volumes = sorted(
            self._volume_list(work.get("volume_outline")),
            key=lambda item: int(item.get("volume_number") or 0),
        )
        volume_numbers = [int(item.get("volume_number") or index + 1) for index, item in enumerate(volumes)]
        chapters = self.repo.list_chapter_outlines(work_id)
        chapter_volumes: dict[int, int] = {}
        counts: dict[int, int] = {number: 0 for number in volume_numbers}
        for chapter in chapters:
            chapter_number = int(chapter.get("chapter_number") or 0)
            volume_number = int(chapter.get("volume_number") or parse_outline_detail(chapter.get("outline_json")).get("volume_number") or 0)
            if chapter_number and volume_number:
                chapter_volumes[chapter_number] = volume_number
                counts[volume_number] = counts.get(volume_number, 0) + 1
        active_volume = self._active_volume_number(volume_numbers, chapter_volumes)
        return {
            "volumes": volumes,
            "volume_numbers": volume_numbers,
            "chapter_volumes": chapter_volumes,
            "counts": counts,
            "active_volume": active_volume,
        }

    def _volume_transition_context(self, work_id: int, start_chapter: int, state: dict[str, Any]) -> dict[str, Any]:
        active_volume = int(state.get("active_volume") or 1)
        next_volume = self._next_volume_number(state.get("volume_numbers") or [], active_volume)
        current_plan = self._volume_plan(state, active_volume)
        next_plan = self._volume_plan(state, next_volume) if next_volume else {}
        current_count = int((state.get("counts") or {}).get(active_volume, 0))
        min_chapters = self._int_field(current_plan, "min_chapters")
        target_chapters = self._int_field(current_plan, "target_chapters")
        soft_max_chapters = self._int_field(current_plan, "soft_max_chapters")
        hard_max_chapters = self._int_field(current_plan, "hard_max_chapters")
        open_threads = self.repo.list_plot_threads(work_id, status="open")
        return {
            "active_volume": active_volume,
            "active_volume_title": current_plan.get("title", ""),
            "next_volume": next_volume,
            "next_volume_title": next_plan.get("title", "") if next_plan else "",
            "current_count": current_count,
            "min_chapters": min_chapters,
            "target_chapters": target_chapters,
            "soft_max_chapters": soft_max_chapters,
            "hard_max_chapters": hard_max_chapters,
            "progress": self._volume_progress(current_count, min_chapters, target_chapters, soft_max_chapters, hard_max_chapters),
            "entry_condition": current_plan.get("entry_condition", ""),
            "exit_condition": current_plan.get("exit_condition", ""),
            "required_milestones": current_plan.get("required_milestones", []),
            "recent_summaries": self.repo.get_recent_summaries(work_id, start_chapter, limit=5),
            "open_plot_threads": open_threads[:12],
            "volume_plot_threads": self._volume_plot_threads(open_threads, state, active_volume, start_chapter),
            "rule": "AI 判断剧情是否该换卷；程序硬校验：未达 min_chapters 不得换卷，达到 hard_max_chapters 强制换卷，不得跳卷，下一卷必须存在。",
        }

    def _validated_volume_decision(
        self,
        state: dict[str, Any],
        decision: Any,
        *,
        explicit_volume: int | None,
    ) -> dict[str, Any]:
        if not isinstance(decision, dict):
            decision = {}
        active_volume = int(state.get("active_volume") or 1)
        volume_numbers = state.get("volume_numbers") or []
        next_volume = self._next_volume_number(volume_numbers, active_volume)
        current_plan = self._volume_plan(state, active_volume)
        current_count = int((state.get("counts") or {}).get(active_volume, 0))
        min_chapters = self._int_field(current_plan, "min_chapters")
        hard_max = self._int_field(current_plan, "hard_max_chapters")

        normalized = {
            "should_transition": bool(decision.get("should_transition")),
            "from_volume": self._optional_int(decision.get("from_volume")) or active_volume,
            "to_volume": self._optional_int(decision.get("to_volume")) or active_volume,
            "reason": str(decision.get("reason") or "").strip(),
            "completed_milestones": self._string_list(decision.get("completed_milestones")),
            "unfinished_milestones": self._string_list(decision.get("unfinished_milestones")),
            "carry_over": self._string_list(decision.get("carry_over")),
            "next_volume_opening_focus": str(decision.get("next_volume_opening_focus") or "").strip(),
            "applied": False,
            "forced": False,
            "blocked_reason": "",
        }
        if explicit_volume:
            normalized["should_transition"] = False
            normalized["from_volume"] = int(explicit_volume)
            normalized["to_volume"] = int(explicit_volume)
            normalized["blocked_reason"] = "本次已显式指定目标卷，自动换卷判断不生效。"
            return normalized

        if next_volume and hard_max and current_count >= hard_max:
            normalized["should_transition"] = True
            normalized["from_volume"] = active_volume
            normalized["to_volume"] = int(next_volume)
            normalized["applied"] = True
            normalized["forced"] = True
            if not normalized["reason"]:
                normalized["reason"] = f"当前卷已达到 hard_max_chapters={hard_max}，系统强制进入下一卷。"
            return normalized

        if not normalized["should_transition"]:
            normalized["from_volume"] = active_volume
            normalized["to_volume"] = active_volume
            return normalized
        if not next_volume:
            normalized["from_volume"] = active_volume
            normalized["to_volume"] = active_volume
            normalized["blocked_reason"] = "没有下一卷可切换。"
            return normalized
        if min_chapters and current_count < min_chapters:
            normalized["from_volume"] = active_volume
            normalized["to_volume"] = active_volume
            normalized["blocked_reason"] = f"当前卷仅 {current_count} 章，未达到 min_chapters={min_chapters}。"
            return normalized
        if normalized["to_volume"] != int(next_volume):
            normalized["to_volume"] = int(next_volume)
        normalized["from_volume"] = active_volume
        normalized["applied"] = True
        return normalized

    def _assign_volume_number(
        self,
        state: dict[str, Any],
        chapter_number: int,
        proposed_volume: int,
        *,
        explicit_volume: int | None = None,
    ) -> int:
        volume_numbers = state.get("volume_numbers") or []
        if explicit_volume:
            return int(explicit_volume)
        if not volume_numbers:
            return proposed_volume or 1
        existing_volume = int((state.get("chapter_volumes") or {}).get(int(chapter_number)) or 0)
        if existing_volume not in volume_numbers:
            existing_volume = 0
        previous_volume = self._previous_volume_for_chapter(state, chapter_number)
        current_volume = existing_volume or previous_volume or state.get("active_volume") or volume_numbers[0]
        if current_volume not in volume_numbers:
            current_volume = volume_numbers[0]
        next_volume = self._next_volume_number(volume_numbers, current_volume)
        current_plan = self._volume_plan(state, current_volume)
        current_count = int((state.get("counts") or {}).get(current_volume, 0))
        if existing_volume == current_volume:
            current_count = max(0, current_count - 1)
        min_chapters = self._int_field(current_plan, "min_chapters")
        hard_max = self._int_field(current_plan, "hard_max_chapters")

        if next_volume and hard_max and current_count >= hard_max:
            return next_volume
        if proposed_volume == current_volume:
            return current_volume
        if next_volume and proposed_volume == next_volume:
            if min_chapters and current_count < min_chapters:
                return current_volume
            return next_volume
        if proposed_volume in volume_numbers and proposed_volume < current_volume:
            return current_volume
        if proposed_volume in volume_numbers and next_volume and proposed_volume > next_volume:
            return next_volume if (not min_chapters or current_count >= min_chapters) else current_volume
        return current_volume

    def _advance_volume_state(self, state: dict[str, Any], chapter_number: int, volume_number: int) -> None:
        chapter_volumes = state.setdefault("chapter_volumes", {})
        counts = state.setdefault("counts", {})
        previous_volume = int(chapter_volumes.get(int(chapter_number)) or 0)
        if previous_volume and previous_volume != int(volume_number):
            counts[previous_volume] = max(0, int(counts.get(previous_volume, 0)) - 1)
        if previous_volume != int(volume_number):
            counts[volume_number] = int(counts.get(volume_number, 0)) + 1
        chapter_volumes[int(chapter_number)] = int(volume_number)
        state["active_volume"] = volume_number

    def _volume_transition_notice(
        self,
        state: dict[str, Any],
        decision: dict[str, Any],
        saved: list[dict[str, Any]],
        initial_active_volume: int | None = None,
    ) -> dict[str, Any]:
        if not saved:
            return {}
        from_volume = int(decision.get("from_volume") or initial_active_volume or 0)
        to_volume = int(decision.get("to_volume") or 0)
        first_switched_chapter = saved[0]
        if not decision.get("applied"):
            from_volume = int(initial_active_volume or from_volume or 0)
            for chapter in saved:
                chapter_volume = int(chapter.get("volume_number") or 0)
                if from_volume and chapter_volume and chapter_volume != from_volume:
                    to_volume = chapter_volume
                    first_switched_chapter = chapter
                    break
        if not from_volume or not to_volume or from_volume == to_volume:
            return {}
        from_plan = self._volume_plan(state, from_volume)
        to_plan = self._volume_plan(state, to_volume)
        reason = decision.get("reason", "")
        if not reason and not decision.get("applied"):
            reason = "本批细纲保存时触发分卷硬约束，后续章节已自动归入下一卷。"
        return {
            "changed": True,
            "forced": bool(decision.get("forced")),
            "from_volume": from_volume,
            "to_volume": to_volume,
            "from_title": from_plan.get("title", ""),
            "to_title": to_plan.get("title", ""),
            "reason": reason,
            "carry_over": decision.get("carry_over", []),
            "next_volume_opening_focus": decision.get("next_volume_opening_focus", ""),
            "first_chapter": first_switched_chapter.get("chapter_number"),
        }

    @staticmethod
    def _volume_progress(
        current_count: int,
        min_chapters: int,
        target_chapters: int,
        soft_max_chapters: int,
        hard_max_chapters: int,
    ) -> dict[str, Any]:
        return {
            "reached_min": bool(min_chapters and current_count >= min_chapters),
            "near_target": bool(target_chapters and current_count >= max(1, target_chapters - 1)),
            "at_or_over_soft_max": bool(soft_max_chapters and current_count >= soft_max_chapters),
            "at_or_over_hard_max": bool(hard_max_chapters and current_count >= hard_max_chapters),
            "chapters_until_min": max(0, min_chapters - current_count) if min_chapters else 0,
            "chapters_until_target": max(0, target_chapters - current_count) if target_chapters else 0,
            "chapters_until_soft_max": max(0, soft_max_chapters - current_count) if soft_max_chapters else 0,
            "chapters_until_hard_max": max(0, hard_max_chapters - current_count) if hard_max_chapters else 0,
        }

    def _volume_plot_threads(
        self,
        threads: list[dict[str, Any]],
        state: dict[str, Any],
        active_volume: int,
        start_chapter: int,
    ) -> list[dict[str, Any]]:
        volume_chapters = [
            int(chapter)
            for chapter, volume in (state.get("chapter_volumes") or {}).items()
            if int(volume or 0) == int(active_volume)
        ]
        max_current_chapter = max(volume_chapters or [max(1, int(start_chapter) - 1)])
        relevant: list[dict[str, Any]] = []
        for thread in threads:
            planned = self._optional_int(thread.get("planned_resolve_chapter"))
            first = self._optional_int(thread.get("first_chapter"))
            if planned and planned <= max_current_chapter + 3:
                relevant.append(thread)
            elif first and max_current_chapter - 5 <= first <= max_current_chapter and not planned:
                relevant.append(thread)
        return sorted(
            relevant,
            key=lambda item: (
                self._optional_int(item.get("planned_resolve_chapter")) or 999999,
                -(self._optional_int(item.get("first_chapter")) or 0),
                self._optional_int(item.get("id")) or 0,
            ),
        )[:8]

    def _previous_volume_for_chapter(self, state: dict[str, Any], chapter_number: int) -> int | None:
        chapter_volumes = state.get("chapter_volumes") or {}
        previous = [
            number
            for number in chapter_volumes
            if int(number) < int(chapter_number)
        ]
        if not previous:
            return None
        return int(chapter_volumes[max(previous)])

    @staticmethod
    def _active_volume_number(volume_numbers: list[int], chapter_volumes: dict[int, int]) -> int:
        if not volume_numbers:
            return 1
        if not chapter_volumes:
            return volume_numbers[0]
        last_chapter = max(chapter_volumes)
        return int(chapter_volumes[last_chapter] or volume_numbers[0])

    @staticmethod
    def _next_volume_number(volume_numbers: list[int], current_volume: int) -> int | None:
        ordered = sorted(int(number) for number in volume_numbers)
        for number in ordered:
            if number > int(current_volume):
                return number
        return None

    @staticmethod
    def _volume_plan(state: dict[str, Any], volume_number: int) -> dict[str, Any]:
        for volume in state.get("volumes") or []:
            if int(volume.get("volume_number") or 0) == int(volume_number):
                return volume
        return {}

    @staticmethod
    def _int_field(data: dict[str, Any], key: str) -> int:
        try:
            return max(0, int(data.get(key) or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item or "").strip()]

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
            "genre_contract": compact_genre_contract(bundle.get("book_contract", {})),
            "book_bible": bundle.get("book_bible", {}),
            "characters": characters,
            "world_rules": bundle.get("world_rules", []),
            "historical_profile": bundle.get("historical_profile", {}),
            "historical_facts": bundle.get("historical_facts", []),
            "open_plot_threads": threads,
            "recent_chapter_outlines": self.repo.get_recent_chapter_outlines(work_id, start_chapter, limit=5),
            "recent_summaries": self.repo.get_recent_summaries(work_id, start_chapter, limit=3),
        }
        recent_openings = self._recent_chapter_openings(work_id, start_chapter)
        context["recent_chapter_openings"] = recent_openings
        context["opening_variation_policy"] = self._opening_variation_policy(recent_openings)
        volume_state = self._volume_state(work_id)
        volume_transition_context = self._volume_transition_context(work_id, start_chapter, volume_state)
        context["volume_state"] = {
            "active_volume": volume_state.get("active_volume"),
            "volume_numbers": volume_state.get("volume_numbers", []),
            "chapter_counts": volume_state.get("counts", {}),
            "last_chapter_volume": self._previous_volume_for_chapter(volume_state, start_chapter),
            "rule": "系统会校验 AI 的分卷提案：不得跳卷；当前卷未达到 min_chapters 时不得进入下一卷；达到 hard_max_chapters 后会强制进入下一卷。",
        }
        context["volume_transition_context"] = volume_transition_context
        if volume_number is not None:
            target_volume_number = int(volume_number or 1)
            context["target_volume_number"] = target_volume_number
            context["target_volume"] = self._volume_info(work.get("volume_outline"), target_volume_number)
        else:
            context["target_volume_number"] = None
            context["target_volume"] = {}
            context["volume_assignment_policy"] = {
                "mode": "ai_decides",
                "rule": "章节号按全书连续编号；请根据 volume_outline、已有章节和剧情阶段判断每章所属分卷。",
            }
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
        draft = strip_chapter_heading(draft, chapter_number, chapter.get("title"))
        if stop_requested():
            raise RuntimeError("任务已停止：第 {0} 章初稿已返回，但未保存。".format(chapter_number))
        draft_repeat_warnings = self._repeated_text_warnings(work_id, chapter_number, draft)
        draft = self.normalize_output_names(work_id, draft)
        draft_quality = self._manuscript_quality_report("初稿", context, chapter, draft)
        if draft_repeat_warnings:
            draft_quality["blockers"] = self._dedupe_texts(
                [
                    *self._as_list(draft_quality.get("blockers")),
                    *[f"初稿疑似重复：{warning}" for warning in draft_repeat_warnings],
                ]
            )
        auto_revise = bool(do_review and do_revise)
        draft_repair_issues = opening_ending_repair_issues(draft_quality) if auto_revise else []
        draft_blockers = self._quality_blockers(draft_quality, ignored=draft_repair_issues)
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
            **self.client.last_usage("writer"),
        )
        if draft_blockers:
            review = self._local_quality_review(draft_quality)
            self.repo.save_review(work_id, chapter["id"], review)
            self.repo.save_problem_draft(work_id, chapter["id"], draft)
            return self._problem_draft_result(
                work_id=work_id,
                chapter=chapter,
                chapter_number=chapter_number,
                draft=draft,
                review=review,
                draft_quality=draft_quality,
                blockers=draft_blockers,
            )

        review: dict[str, Any] | None = None
        if do_review:
            reviewer_context = context_for_reviewer(context)
            review = self.reviewer.review_chapter(reviewer_context, draft)
            if stop_requested():
                raise RuntimeError("任务已停止：第 {0} 章审稿已返回，但未继续修订。".format(chapter_number))
            review = self.normalize_output_names(work_id, review)
            review = self._merge_quality_report_into_review(review, draft_quality)
            self.repo.save_review(work_id, chapter["id"], review)
            self.repo.log_agent_run(
                work_id=work_id,
                chapter_id=chapter["id"],
                agent_name="reviewer",
                model=self.client.model_for("reviewer"),
                prompt_name="reviewer_prompt.md",
                input_preview=json_dumps({"context": reviewer_context, "draft": draft[:3000]}),
                output=json_dumps(review),
                **self.client.last_usage("reviewer"),
            )

        final_text = draft
        if auto_revise:
            reviser_context = context_for_reviser(context)
            if review is None:
                review = self._local_quality_review(draft_quality)
                self.repo.save_review(work_id, chapter["id"], review)
            final_text = self.reviser.revise_chapter(reviser_context, draft, review)
            final_text = strip_chapter_heading(final_text, chapter_number, chapter.get("title"))
            if stop_requested():
                raise RuntimeError("任务已停止：第 {0} 章修订稿已返回，但未保存最终稿。".format(chapter_number))
            regression_warnings = self._dedupe_texts(
                [*style_regression_warnings(draft, final_text), *style_guard_warnings(final_text)]
            )
            if regression_warnings:
                self.repo.add_version(
                    work_id,
                    chapter["id"],
                    f"reviser_rejected_style_{now_text()}",
                    final_text,
                )
                rejected_text = final_text
                cleaned_text = self.reviser.sanitize_style(reviser_context, final_text, regression_warnings)
                cleaned_text = strip_chapter_heading(cleaned_text, chapter_number, chapter.get("title"))
                if stop_requested():
                    raise RuntimeError("任务已停止：第 {0} 章语言清理稿已返回，但未保存最终稿。".format(chapter_number))
                cleaned_text = self.normalize_output_names(work_id, cleaned_text)
                cleaned_warnings = self._dedupe_texts(
                    [*style_regression_warnings(draft, cleaned_text), *style_guard_warnings(cleaned_text)]
                )
                if cleaned_warnings:
                    final_text = draft
                    review = self._merge_quality_report_into_review(
                        review or {},
                        {
                            "warnings": [
                                "修订稿因风格退化未覆盖初稿：" + "；".join(regression_warnings)
                            ],
                            "template_hits": [],
                            "risk_flags": ["修订风格退化"],
                        },
                    )
                    self.repo.save_review(work_id, chapter["id"], review)
                else:
                    final_text = cleaned_text
                    self.repo.log_agent_run(
                        work_id=work_id,
                        chapter_id=chapter["id"],
                        agent_name="reviser",
                        model=self.client.model_for("reviser"),
                        prompt_name="reviser_prompt.md",
                        input_preview=json_dumps({"context": reviser_context, "style_cleanup": regression_warnings, "draft": rejected_text[:3000]}),
                        output=cleaned_text,
                        **self.client.last_usage("reviser"),
                    )
            final_repeat_warnings = self._repeated_text_warnings(work_id, chapter_number, final_text)
            if final_repeat_warnings:
                raise ValueError("本章修订稿疑似重复，已停止保存：" + "；".join(final_repeat_warnings))
            final_text = self.normalize_output_names(work_id, final_text)
            final_quality = self._manuscript_quality_report("修订稿", context, chapter, final_text)
            if self._revision_degraded_opening(draft_quality, final_quality):
                final_text = draft
                final_quality = draft_quality
            focus_issues = opening_ending_repair_issues(final_quality)
            if focus_issues:
                final_text = self._revise_opening_ending_once(
                    work_id,
                    chapter,
                    chapter_number,
                    context,
                    reviser_context,
                    final_text,
                    focus_issues,
                    should_stop=stop_requested,
                )
                final_quality = self._manuscript_quality_report("首尾专项修订稿", context, chapter, final_text)
            final_blockers = self._quality_blockers(final_quality)
            if final_blockers:
                review = self._merge_quality_report_into_review(review or {}, final_quality)
                self.repo.save_review(work_id, chapter["id"], review)
                self.repo.save_problem_draft(work_id, chapter["id"], final_text)
                return self._problem_draft_result(
                    work_id=work_id,
                    chapter=chapter,
                    chapter_number=chapter_number,
                    draft=final_text,
                    review=review,
                    draft_quality=final_quality,
                    blockers=final_blockers,
                )
            self.repo.log_agent_run(
                work_id=work_id,
                chapter_id=chapter["id"],
                agent_name="reviser",
                model=self.client.model_for("reviser"),
                prompt_name="reviser_prompt.md",
                input_preview=json_dumps({"context": reviser_context, "review": review, "draft": draft[:3000]}),
                output=final_text,
                **self.client.last_usage("reviser"),
            )
        else:
            final_quality = draft_quality

        self.repo.save_final(work_id, chapter["id"], final_text)

        memory_card: dict[str, Any] | None = None
        if do_memory:
            refreshed_context = self.build_chapter_context(work_id, chapter_number)
            memory_context = context_for_memory(refreshed_context)
            memory_card = self.memory.make_memory_card(memory_context, final_text)
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
                input_preview=json_dumps({"context": memory_context, "final_text": final_text[:3000]}),
                output=json_dumps(memory_card),
                **self.client.last_usage("memory"),
            )

        return {
            "chapter": self.repo.get_chapter(work_id, chapter_number),
            "draft": draft,
            "review": review,
            "final_text": final_text,
            "memory": memory_card,
            "quality_gate": {
                "draft": draft_quality,
                "final": final_quality,
                "summary": "；".join(
                    item
                    for item in [quality_summary(draft_quality), quality_summary(final_quality)]
                    if item
                ),
            },
        }

    def _repeated_text_warnings(self, work_id: int, chapter_number: int, text: str) -> list[str]:
        recent_texts = self.repo.get_recent_chapter_texts(work_id, chapter_number, limit=5)
        return repeated_text_warnings(text, recent_texts)

    def _manuscript_quality_report(
        self,
        stage: str,
        context: dict[str, Any],
        chapter: dict[str, Any],
        text: str,
    ) -> dict[str, Any]:
        return manuscript_quality_report(
            text,
            context,
            chapter_number=int(chapter.get("chapter_number") or 0) or None,
            chapter_title=chapter.get("title", ""),
            stage=stage,
        )

    def _revise_opening_ending_once(
        self,
        work_id: int,
        chapter: dict[str, Any],
        chapter_number: int,
        context: dict[str, Any],
        reviser_context: dict[str, Any],
        final_text: str,
        issues: list[str],
        *,
        should_stop: Callable[[], bool],
    ) -> str:
        revised = self.reviser.revise_opening_ending(reviser_context, final_text, issues)
        revised = strip_chapter_heading(revised, chapter_number, chapter.get("title"))
        if should_stop():
            raise RuntimeError("任务已停止：第 {0} 章首尾专项修订稿已返回，但未保存最终稿。".format(chapter_number))
        repeat_warnings = self._repeated_text_warnings(work_id, chapter_number, revised)
        if repeat_warnings:
            raise ValueError("本章首尾专项修订稿疑似重复，已停止保存：" + "；".join(repeat_warnings))
        regression_warnings = self._dedupe_texts(
            [*style_regression_warnings(final_text, revised), *style_guard_warnings(revised)]
        )
        if regression_warnings:
            self.repo.add_version(
                work_id,
                chapter["id"],
                f"reviser_rejected_style_{now_text()}",
                revised,
            )
            cleaned = self.reviser.sanitize_style(reviser_context, revised, regression_warnings)
            cleaned = strip_chapter_heading(cleaned, chapter_number, chapter.get("title"))
            if should_stop():
                raise RuntimeError("任务已停止：第 {0} 章语言清理稿已返回，但未保存最终稿。".format(chapter_number))
            cleaned = self.normalize_output_names(work_id, cleaned)
            cleaned_warnings = self._dedupe_texts(
                [*style_regression_warnings(final_text, cleaned), *style_guard_warnings(cleaned)]
            )
            if cleaned_warnings:
                return final_text
            revised = cleaned
        revised = self.normalize_output_names(work_id, revised)
        self.repo.log_agent_run(
            work_id=work_id,
            chapter_id=chapter["id"],
            agent_name="reviser",
            model=self.client.model_for("reviser"),
            prompt_name="reviser_prompt.md",
            input_preview=json_dumps({"context": reviser_context, "focus_issues": issues, "draft": final_text[:3000]}),
            output=revised,
            **self.client.last_usage("reviser"),
        )
        return revised

    @staticmethod
    def _revision_degraded_opening(draft_quality: dict[str, Any], final_quality: dict[str, Any]) -> bool:
        draft_issues = opening_ending_repair_issues(draft_quality)
        final_issues = opening_ending_repair_issues(final_quality)
        if not final_issues:
            return False
        if not draft_issues:
            return True

        draft_blockers = [
            str(item)
            for item in draft_quality.get("blockers", [])
            if str(item).strip() and any(marker in str(item) for marker in ("章首", "开篇", "第一屏", "承接债", "结尾", "章末"))
        ]
        final_blockers = [
            str(item)
            for item in final_quality.get("blockers", [])
            if str(item).strip() and any(marker in str(item) for marker in ("章首", "开篇", "第一屏", "承接债", "结尾", "章末"))
        ]
        if len(final_blockers) > len(draft_blockers):
            return True
        if len(final_issues) > len(draft_issues):
            return True
        return False

    @staticmethod
    def _quality_blockers(report: dict[str, Any] | None, *, ignored: list[str] | None = None) -> list[str]:
        ignored_set = {str(item).strip() for item in (ignored or []) if str(item).strip()}
        if not isinstance(report, dict):
            return []
        return [
            str(item)
            for item in report.get("blockers") or []
            if str(item).strip() and str(item).strip() not in ignored_set
        ]

    @staticmethod
    def _raise_quality_blockers(chapter_number: int, report: dict[str, Any], *, ignored: list[str] | None = None) -> None:
        blockers = NovelWorkflow._quality_blockers(report, ignored=ignored)
        if blockers:
            raise ValueError(f"第 {chapter_number} 章未通过质量闸门：" + "；".join(blockers))

    @staticmethod
    def _local_quality_review(report: dict[str, Any]) -> dict[str, Any]:
        blockers = NovelWorkflow._quality_blockers(report)
        warnings = [str(item) for item in report.get("warnings") or [] if str(item).strip()]
        problems = [
            {
                "type": "quality_gate",
                "severity": "high",
                "evidence": item,
                "why_it_matters": "该问题会影响章节承接、正文完整度或读者阅读体验。",
            }
            for item in blockers
        ]
        problems.extend(
            {
                "type": "quality_gate",
                "severity": "medium",
                "evidence": item,
                "why_it_matters": "该问题暂未阻断保存，但建议在定稿前处理。",
            }
            for item in warnings
        )
        return {
            "continuity_score": 45 if blockers else 70,
            "character_score": 60,
            "emotion_score": 55,
            "rhythm_score": 55,
            "foreshadow_score": 55,
            "payoff_score": 55,
            "hook_score": 45 if blockers else 70,
            "historical_score": 60,
            "problems": problems,
            "suggestions": [
                "这份内容已保存为问题草稿，请先处理质量闸门列出的阻断项，再保存为最终稿。",
                "优先检查章首承接、章节任务完成度、正文完整度和章末牵引。",
            ],
            "template_hits": report.get("template_hits") or [],
            "risk_flags": report.get("risk_flags") or [],
            "length_problem": report.get("length_problem") or "",
            "repeat_risk": [item for item in blockers if "重复" in item],
        }

    def _problem_draft_result(
        self,
        *,
        work_id: int,
        chapter: dict[str, Any],
        chapter_number: int,
        draft: str,
        review: dict[str, Any],
        draft_quality: dict[str, Any],
        blockers: list[str],
    ) -> dict[str, Any]:
        return {
            "chapter": self.repo.get_chapter(work_id, chapter_number),
            "draft": draft,
            "review": review,
            "final_text": "",
            "memory": None,
            "problem_draft": True,
            "quality_gate": {
                "problem_draft": True,
                "draft": draft_quality,
                "final": {},
                "blockers": blockers,
                "summary": f"问题草稿已保存：第 {chapter_number} 章初稿未通过质量闸门，阻断 {len(blockers)} 项。",
            },
        }

    @staticmethod
    def _merge_quality_report_into_review(review: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
        merged = dict(review or {})
        warnings = [str(item) for item in report.get("warnings") or [] if str(item).strip()]
        blockers = [str(item) for item in report.get("blockers") or [] if str(item).strip()]
        if warnings or blockers:
            merged["problems"] = NovelWorkflow._dedupe_texts([*NovelWorkflow._as_list(merged.get("problems")), *blockers, *warnings])
            merged["suggestions"] = NovelWorkflow._dedupe_texts(
                [
                    *NovelWorkflow._as_list(merged.get("suggestions")),
                    "按质量闸门提示检查开篇承接、章末钩子、字数、模板句和历史违和词。",
                ]
            )
        if report.get("length_problem"):
            merged["length_problem"] = str(report.get("length_problem") or "")
        merged["template_hits"] = NovelWorkflow._dedupe_review_items(
            [*NovelWorkflow._as_list(merged.get("template_hits")), *NovelWorkflow._as_list(report.get("template_hits"))]
        )
        merged["risk_flags"] = NovelWorkflow._dedupe_texts(
            [*NovelWorkflow._as_list(merged.get("risk_flags")), *NovelWorkflow._as_list(report.get("risk_flags"))]
        )
        return merged

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        return value if isinstance(value, list) else ([] if value in (None, "") else [value])

    @staticmethod
    def _dedupe_texts(values: list[Any]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
        return result

    @staticmethod
    def _dedupe_review_items(values: list[Any]) -> list[Any]:
        seen: set[str] = set()
        result: list[Any] = []
        for value in values:
            key = json_dumps(value) if isinstance(value, dict) else str(value)
            if key not in seen:
                seen.add(key)
                result.append(value)
        return result

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
        recent_openings = self._recent_chapter_openings(work_id, chapter_number)
        recent_endings = self._recent_chapter_endings(work_id, chapter_number)
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
            "recent_chapter_openings": recent_openings,
            "recent_chapter_endings": recent_endings,
            "opening_variation_policy": self._opening_variation_policy(recent_openings),
            "ending_variation_policy": self._ending_variation_policy(recent_endings),
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
                "quality_gate": "程序会在保存前检查章节标题泄漏、短摘要、字数偏差、空泛章尾、章尾重复、模板句、历史违和词和开篇接力棒。",
            },
        }
        context["chapter_word_target"] = chapter_word_target_from_style((bundle.get("work") or {}).get("style", ""))
        context["chapter_execution_card"] = self._chapter_execution_card(context)
        context["history_specialist"] = historical_context_for_bundle(context)
        return self.normalize_output_names(work_id, context)

    @staticmethod
    def _chapter_execution_card(context: dict[str, Any]) -> dict[str, Any]:
        chapter = context.get("chapter") if isinstance(context.get("chapter"), dict) else {}
        detail = chapter.get("outline_detail") if isinstance(chapter.get("outline_detail"), dict) else {}
        contract = context.get("chapter_transition_contract") if isinstance(context.get("chapter_transition_contract"), dict) else {}
        return {
            "priority": "最高优先级：正文第一屏必须先执行本卡，再展开其他内容。",
            "last_visible_beat": contract.get("last_visible_beat") or contract.get("previous_ending_hook") or "",
            "first_screen_task": contract.get("required_next_beat") or contract.get("required_first_paragraph") or detail.get("opening_trigger") or "",
            "must_include_anchors": [
                item
                for item in [
                    contract.get("must_use_concrete_anchor"),
                    detail.get("previous_anchor"),
                    detail.get("continuity_debt"),
                ]
                if str(item or "").strip()
            ][:3],
            "forbidden_opening": contract.get("forbidden_opening") or detail.get("forbidden_opening") or "",
            "chapter_goal": detail.get("chapter_goal") or chapter.get("outline") or "",
            "chapter_payoff": detail.get("reader_answer_out") or detail.get("chapter_payoff") or "",
            "dash_budget": "正式稿破折号 0 到 2 处；章首前 300 字不用破折号，除非对白或突发动作被打断。",
            "final_gate": "没有接住上一章最后画面、破折号超标、字数明显不足或章首模板化时，只能保存为问题稿，不能入记忆。",
        }

    def _recent_chapter_openings(self, work_id: int, chapter_number: int, limit: int = 5) -> list[dict[str, Any]]:
        rows = list(reversed(self.repo.get_recent_chapter_texts(work_id, chapter_number, limit=limit)))
        openings: list[dict[str, Any]] = []
        for row in rows:
            text = str(row.get("final_text") or row.get("draft") or "")
            opening = first_paragraph(text)
            if not opening:
                continue
            flags = opening_pattern_flags(opening)
            rhetorical_flags = rhetorical_pattern_flags(opening, opening=True)
            signature = opening_signature(opening)
            openings.append(
                {
                    "chapter_number": row.get("chapter_number"),
                    "title": row.get("title", ""),
                    "opening": opening,
                    "pattern": opening_pattern_label(opening),
                    "pattern_flags": flags,
                    "rhetorical_flags": rhetorical_flags,
                    "opening_mode": detect_opening_mode(opening),
                    "opening_signature": signature,
                    "opening_engine": signature.get("opening_engine"),
                    "surface_anchors": signature.get("surface_anchors"),
                    "primary_surface_anchor": signature.get("primary_surface_anchor"),
                    "subject_type": signature.get("subject_type"),
                    "syntax_shape": signature.get("syntax_shape"),
                }
            )
        return openings

    def _recent_chapter_endings(self, work_id: int, chapter_number: int, limit: int = 5) -> list[dict[str, Any]]:
        rows = list(reversed(self.repo.get_recent_chapter_texts(work_id, chapter_number, limit=limit)))
        endings: list[dict[str, Any]] = []
        for row in rows:
            text = str(row.get("final_text") or row.get("draft") or "")
            tail = last_screen(text)
            if not tail:
                continue
            signature = ending_signature(tail)
            endings.append(
                {
                    "chapter_number": row.get("chapter_number"),
                    "title": row.get("title", ""),
                    "ending": tail,
                    "anchor_type": signature.get("anchor_type"),
                    "concrete_anchors": signature.get("concrete_anchors") or [],
                    "rhetorical_flags": signature.get("rhetorical_flags") or [],
                    "dash_count": signature.get("dash_count") or 0,
                    "contrast_count": signature.get("contrast_count") or 0,
                    "abstract_forecast": bool(signature.get("abstract_forecast")),
                }
            )
        return endings

    @staticmethod
    def _opening_variation_policy(openings: list[dict[str, Any]]) -> dict[str, Any]:
        recent = openings[-3:]
        flag_sets = [set(item.get("pattern_flags") or []) for item in recent if item.get("pattern_flags")]
        repeated_flags = sorted(set.intersection(*flag_sets)) if len(flag_sets) >= 2 else []
        rhetorical_sets = [
            set(item.get("rhetorical_flags") or [])
            for item in recent
            if item.get("rhetorical_flags")
        ]
        repeated_rhetorical_flags = sorted(set.intersection(*rhetorical_sets)) if len(rhetorical_sets) >= 2 else []
        recent_rhetorical_flags = sorted(
            {
                str(flag)
                for item in recent
                for flag in (item.get("rhetorical_flags") or [])
                if str(flag).strip()
            }
        )
        modes = [str(item.get("opening_mode") or "").strip() for item in recent if item.get("opening_mode")]
        repeated_mode = modes[-1] if len(modes) >= 2 and modes[-1] == modes[-2] else ""
        signature_recent = [item for item in openings[-5:] if isinstance(item.get("opening_signature"), dict)]
        surface_anchors = [
            str((item.get("opening_signature") or {}).get("primary_surface_anchor") or "")
            for item in signature_recent
            if str((item.get("opening_signature") or {}).get("primary_surface_anchor") or "")
        ]
        repeated_surface_anchors = sorted(
            {
                anchor
                for anchor in surface_anchors
                if anchor not in {"其他", "问题/威胁/证据", "对白"} and surface_anchors.count(anchor) >= 2
            }
        )
        engines = [
            str((item.get("opening_signature") or {}).get("opening_engine") or "")
            for item in signature_recent[-3:]
            if str((item.get("opening_signature") or {}).get("opening_engine") or "")
        ]
        repeated_engine = engines[-1] if len(engines) >= 2 and engines[-1] == engines[-2] else ""
        shapes = [
            str((item.get("opening_signature") or {}).get("syntax_shape") or "")
            for item in signature_recent[-4:]
            if str((item.get("opening_signature") or {}).get("syntax_shape") or "")
        ]
        repeated_syntax_shapes = sorted(
            {
                shape
                for shape in shapes
                if shape not in {"其他"} and shapes.count(shape) >= 2
            }
        )
        subjects = [
            str((item.get("opening_signature") or {}).get("subject_type") or "")
            for item in signature_recent[-4:]
            if str((item.get("opening_signature") or {}).get("subject_type") or "")
        ]
        repeated_subject = subjects[-1] if len(subjects) >= 3 and subjects[-1] == subjects[-2] == subjects[-3] else ""
        if repeated_surface_anchors:
            instruction = (
                "最近章节章首表层锚点重复："
                + "、".join(repeated_surface_anchors)
                + "。本章不要继续让同类声音、时间、天气光线、门窗出入、文书消息、物件触感或普通动作承担第一屏发动机；"
                "若必须出现，只能作为背景，第一屏要改由新证据、对白逼问、威胁抵达、关系冲突、选择逼近或现场异常发动。"
            )
        elif repeated_engine:
            instruction = (
                f"最近章节章首剧情发动方式连续接近“{repeated_engine}”。本章必须换一种发动方式，"
                "不要只替换词语；优先从证据、对白、威胁、关系压力、缺席、选择或对手动作切入。"
            )
        elif repeated_syntax_shapes:
            instruction = (
                "最近章节章首句式形状重复："
                + "、".join(repeated_syntax_shapes)
                + "。本章第一句必须换句法和第一眼落点，避免同款时间起句、声音起句、物件触感起句、人物动作起句或破折号解释。"
            )
        elif repeated_subject:
            instruction = (
                f"最近章节章首第一眼连续落在“{repeated_subject}”。本章优先换成物件、对白、缺席者、对手动作、群体反应或现场异常。"
            )
        elif repeated_rhetorical_flags:
            instruction = (
                "最近章节章首已经连续出现"
                + "、".join(repeated_rhetorical_flags)
                + "。本章第一段禁止再用“不是…是/而是/却…”或破折号补充说明制造转折；"
                "必须承接上一章事实锚点，用动作、对白、物件变化、证据异常、威胁抵达或关系逼问直接开场。"
            )
        elif repeated_flags:
            instruction = (
                "最近章节章首已经连续出现"
                + "、".join(repeated_flags)
                + "开头。本章第一句禁止再用时辰、地名、天气、晨雾、钟鼓、日光、夜色等静态信息起笔；"
                "必须从上一章留下的人物动作、对白、证据、威胁、物件变化或冲突后果直接切入。"
            )
        elif repeated_mode:
            instruction = (
                f"最近章节章首开头方式连续接近“{repeated_mode}”。本章必须换成不同 opening_mode，"
                "例如物件、对白、异常、后果、反应、命令、缺席、冲突、时间压力或环境异常中的另一种，并让开头触发新事件。"
            )
        elif recent_rhetorical_flags:
            instruction = (
                "最近章节章首出现过"
                + "、".join(recent_rhetorical_flags)
                + "。本章第一段避免复用这些修辞手势；"
                "优先承接上一章事实锚点，用动作、对白、物件变化、证据异常、威胁抵达或关系逼问开场。"
            )
        else:
            instruction = (
                "章首可用物件、对白、异常、后果、反应、命令、缺席、冲突、时间压力、环境异常或人物动作；"
                "不要固定成主角名字加普通动作，也不要为了古风氛围先写时辰、地点、天气或环境陈列。"
            )
        return {
            "recent_opening_count": len(openings),
            "repeated_opening_flags": repeated_flags,
            "recent_rhetorical_flags": recent_rhetorical_flags,
            "repeated_rhetorical_flags": repeated_rhetorical_flags,
            "recent_opening_modes": modes,
            "repeated_opening_mode": repeated_mode,
            "recent_surface_anchors": surface_anchors,
            "repeated_surface_anchors": repeated_surface_anchors,
            "recent_opening_engines": engines,
            "repeated_opening_engine": repeated_engine,
            "recent_syntax_shapes": shapes,
            "repeated_syntax_shapes": repeated_syntax_shapes,
            "recent_subject_types": subjects,
            "repeated_subject_type": repeated_subject,
            "instruction": instruction,
        }

    @staticmethod
    def _ending_variation_policy(endings: list[dict[str, Any]]) -> dict[str, Any]:
        recent = endings[-3:]
        types = [str(item.get("anchor_type") or "").strip() for item in recent if item.get("anchor_type")]
        repeated_type = types[-1] if len(types) >= 2 and types[-1] == types[-2] else ""
        recent_flags = sorted(
            {
                str(flag)
                for item in recent
                for flag in (item.get("rhetorical_flags") or [])
                if str(flag).strip()
            }
        )
        repeated_dash = sum(1 for item in recent if int(item.get("dash_count") or 0) > 0) >= 2
        repeated_contrast = sum(1 for item in recent if int(item.get("contrast_count") or 0) > 0) >= 2
        anchors = [
            str(anchor)
            for item in recent
            for anchor in (item.get("concrete_anchors") or [])
            if str(anchor).strip()
        ]
        repeated_anchors = sorted({anchor for anchor in anchors if anchors.count(anchor) >= 2})
        if repeated_contrast or repeated_dash:
            instruction = (
                "最近章尾出现对照判断句式或破折号解释式收束。本章章尾必须避开同类句式，"
                "用具体动作、对白后果、物件状态、证据变化或威胁抵达留下下一章可承接的外部锚点。"
            )
        elif repeated_type:
            instruction = (
                f"最近章尾落点连续接近“{repeated_type}”。本章章尾要换收束方式，"
                "不要继续用同类物件/文书/鼓声/日光做悬念，改用不同的人物动作、关系压力、现场变化或新证据。"
            )
        elif repeated_anchors:
            instruction = (
                "最近章尾反复使用这些锚点："
                + "、".join(repeated_anchors[:5])
                + "。本章章尾请换一个可被下一章第一段承接的外部锚点。"
            )
        else:
            instruction = (
                "章尾必须交付本章回报，并留下下一章第一段可直接接住的外部锚点；"
                "优先用行动未完成、证据状态变化、关系逼问、命令抵达、脚步/敲门等具体事件收束，避免抽象预告。"
            )
        return {
            "recent_ending_count": len(endings),
            "recent_anchor_types": types,
            "repeated_anchor_type": repeated_type,
            "recent_rhetorical_flags": recent_flags,
            "repeated_dash_ending": repeated_dash,
            "repeated_contrast_ending": repeated_contrast,
            "repeated_concrete_anchors": repeated_anchors[:8],
            "instruction": instruction,
        }

    def _chapter_transition_contract(self, previous_chapter: dict[str, Any] | None) -> dict[str, Any]:
        if not previous_chapter:
            return {}
        handoff = self._handoff_dict(previous_chapter.get("handoff"))
        required_opening = (
            handoff.get("next_first_paragraph_task")
            or handoff.get("next_opening_must_continue")
            or handoff.get("next_opening_action")
            or handoff.get("next_continuity_debt")
            or previous_chapter.get("ending_hook")
            or ""
        )
        last_visible_beat = (
            handoff.get("last_visible_anchor")
            or handoff.get("last_external_action")
            or handoff.get("active_object")
            or previous_chapter.get("ending_hook", "")
        )
        required_next_beat = (
            handoff.get("next_opening_action")
            or handoff.get("next_first_paragraph_task")
            or handoff.get("next_opening_must_continue")
            or handoff.get("next_continuity_debt")
            or previous_chapter.get("ending_hook", "")
        )
        forbidden_opening = (
            handoff.get("forbidden_next_opening")
            or handoff.get("forbidden_opening")
            or handoff.get("forbidden_jump")
            or "禁止跳过上一章结尾，禁止先写天气、时间跳转、回忆或背景说明。"
        )
        previous_bridge_text = " ".join(
            str(value or "")
            for value in [
                previous_chapter.get("tail", ""),
                previous_chapter.get("ending_hook", ""),
                previous_chapter.get("handoff", ""),
            ]
        )
        rhetorical_flags = rhetorical_pattern_flags(previous_bridge_text, opening=False)
        style_guard = (
            "必须承接上一章的人、物、动作、对白、证据、威胁或后果；"
            "如果上一章接力棒含“不是…是/而是/却…”或破折号结构，只承接事实锚点，禁止复制句式。"
        )
        scene_continuity_guard = (
            "默认同场景或同事件连续承接。第一句要像上一章最后可见画面之后的下一拍；"
            "除非任务单明确允许换视角/换阶段，否则禁止用“主角名+普通动作”、时间地点、天气、回忆或解释重新开场。"
        )
        return {
            "previous_chapter_number": previous_chapter.get("chapter_number"),
            "previous_title": previous_chapter.get("title", ""),
            "previous_tail": previous_chapter.get("tail", ""),
            "previous_ending_hook": previous_chapter.get("ending_hook", ""),
            "handoff": handoff,
            "required_first_paragraph": required_opening,
            "last_visible_beat": last_visible_beat,
            "required_next_beat": required_next_beat,
            "forbidden_opening": forbidden_opening,
            "style_guard": style_guard,
            "scene_continuity_guard": scene_continuity_guard,
            "allowed_shift": False,
            "shift_reason": "",
            "previous_rhetorical_flags": rhetorical_flags,
            "must_use_concrete_anchor": (
                handoff.get("active_object")
                or handoff.get("last_visible_anchor")
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
