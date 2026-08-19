from __future__ import annotations

import threading
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from app.database.repository import Repository
from app.services.ai_client import AIClient
from app.utils.config import load_config
from app.workflow import NovelWorkflow


def now_text() -> str:
    return datetime.now().isoformat(timespec="microseconds")


class WebState:
    MAX_CONCURRENT_TASKS = 3

    def __init__(self) -> None:
        self.repo = Repository()
        self.workflow = NovelWorkflow(repo=self.repo, client=AIClient())
        self.api_token = secrets.token_urlsafe(32)
        self.custom_export_dirs: dict[int, Path] = {}
        self._tasks: dict[str, dict[str, Any]] = {}
        self._task_cleanups: dict[str, Any] = {}
        self._chapter_owners: dict[tuple[int, int], str] = {}
        self._task_lock = threading.Lock()
        self._recover_interrupted_tasks()

    def reload_config(self) -> None:
        self.workflow = NovelWorkflow(repo=self.repo, client=AIClient(load_config()))

    def start_task(
        self,
        task_id: str,
        *,
        kind: str = "",
        title: str = "",
        work_id: int | None = None,
        chapter_id: int | None = None,
    ) -> None:
        if not task_id:
            return
        with self._task_lock:
            active_tasks = [
                task
                for task in self._tasks.values()
                if task.get("status") in {"running", "cancelling"}
            ]
            for active in active_tasks:
                if active.get("id") == task_id:
                    active_title = str(active.get("title") or active.get("kind") or "AI 任务")
                    raise ValueError(f"{active_title}已经在运行，请勿重复提交。")
                if not self._tasks_conflict(active, work_id=work_id, chapter_id=chapter_id):
                    continue
                active_title = str(active.get("title") or active.get("kind") or "AI 任务")
                raise ValueError(f"资源正在执行其他任务：{active_title}。请等待完成或先停止该任务。")
            if len(active_tasks) >= self.MAX_CONCURRENT_TASKS:
                raise ValueError(f"并行任务已达到上限（{self.MAX_CONCURRENT_TASKS} 个），请等待一个任务结束后再试。")
            self._claim_chapter_locked(task_id, work_id, chapter_id)
            self._tasks[task_id] = {
                "id": task_id,
                "kind": kind,
                "title": title,
                "status": "running",
                "started_at": now_text(),
                "finished_at": "",
                "error": "",
                "work_id": work_id,
                "chapter_id": chapter_id,
            }

    def claim_chapter(self, owner_id: str, work_id: int, chapter_id: int) -> None:
        with self._task_lock:
            self._claim_chapter_locked(owner_id, work_id, chapter_id)

    def release_chapter(self, owner_id: str, work_id: int, chapter_id: int) -> None:
        with self._task_lock:
            key = (int(work_id), int(chapter_id))
            if self._chapter_owners.get(key) == owner_id:
                self._chapter_owners.pop(key, None)

    def claim_chapters(self, owner_id: str, work_id: int, chapter_ids: list[int]) -> None:
        keys = [(int(work_id), int(chapter_id)) for chapter_id in set(chapter_ids)]
        with self._task_lock:
            if any(self._chapter_owners.get(key) not in {None, owner_id} for key in keys):
                raise ValueError("要删除的章节中仍有生成或保存操作，请等待完成后重试。")
            for key in keys:
                self._chapter_owners[key] = owner_id

    def release_chapters(self, owner_id: str, work_id: int, chapter_ids: list[int]) -> None:
        keys = [(int(work_id), int(chapter_id)) for chapter_id in set(chapter_ids)]
        with self._task_lock:
            for key in keys:
                if self._chapter_owners.get(key) == owner_id:
                    self._chapter_owners.pop(key, None)

    def register_task_cleanup(self, task_id: str, cleanup: Any) -> None:
        if not task_id or cleanup is None:
            return
        run_immediately = False
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None or task.get("status") not in {"running", "cancelling"}:
                run_immediately = True
            elif task.get("status") == "cancelling":
                run_immediately = True
            else:
                self._task_cleanups[task_id] = cleanup
        if run_immediately:
            try:
                cleanup()
            except Exception:  # noqa: BLE001
                return

    def cancel_task(self, task_id: str) -> bool:
        if not task_id:
            return False
        cleanup = None
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            if task.get("status") not in {"done", "failed", "cancelled"}:
                task["status"] = "cancelling"
                cleanup = self._task_cleanups.get(task_id)
        if cleanup is not None:
            try:
                cleanup()
            except Exception:  # noqa: BLE001
                return True
        return True

    def task_cancelled(self, task_id: str) -> bool:
        if not task_id:
            return False
        with self._task_lock:
            return self._tasks.get(task_id, {}).get("status") in {"cancelling", "cancelled"}

    def update_task_stage(self, task_id: str, stage: str, detail: str = "") -> None:
        if not task_id:
            return
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None or task.get("status") not in {"running", "cancelling"}:
                return
            task["stage"] = str(stage or "")
            task["detail"] = str(detail or "")

    def finish_task(self, task_id: str, *, status: str = "done", error: str = "") -> None:
        if not task_id:
            return
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            if task.get("status") == "cancelling" and status == "done":
                status = "cancelled"
            task["status"] = status
            task["finished_at"] = now_text()
            task["error"] = error
            self._task_cleanups.pop(task_id, None)
            self._release_task_chapter_locked(task_id, task)

    def task_status(self, task_id: str) -> dict[str, Any]:
        if not task_id:
            return {}
        with self._task_lock:
            return dict(self._tasks.get(task_id, {}))

    def active_task(self) -> dict[str, Any]:
        with self._task_lock:
            task = next(
                (item for item in self._tasks.values() if item.get("status") in {"running", "cancelling"}),
                None,
            )
            return dict(task or {})

    def active_tasks(self) -> list[dict[str, Any]]:
        with self._task_lock:
            return [
                dict(task)
                for task in sorted(
                    self._tasks.values(),
                    key=lambda item: str(item.get("started_at") or ""),
                )
                if task.get("status") in {"running", "cancelling"}
            ]

    def assert_work_mutable(self, work_id: int, action: str = "修改作品") -> None:
        with self._task_lock:
            for active in self._tasks.values():
                if active.get("status") not in {"running", "cancelling"}:
                    continue
                if not self._tasks_conflict(active, work_id=work_id, chapter_id=None):
                    continue
                title = str(active.get("title") or active.get("kind") or "AI 任务")
                raise ValueError(f"{title}仍在运行，暂时不能{action}。请等待任务结束或先停止任务。")

    def assert_no_active_task(self, action: str) -> None:
        with self._task_lock:
            active = next(
                (item for item in self._tasks.values() if item.get("status") in {"running", "cancelling"}),
                None,
            )
            if active is None:
                return
            title = str(active.get("title") or active.get("kind") or "AI 任务")
            raise ValueError(f"{title}仍在运行，暂时不能{action}。请等待任务结束或先停止任务。")

    @staticmethod
    def _tasks_conflict(task: dict[str, Any], *, work_id: int | None, chapter_id: int | None) -> bool:
        other_work_id = task.get("work_id")
        if work_id is None or other_work_id is None:
            # Configuration diagnostics do not occupy a work resource. Two
            # configuration diagnostics still serialize through their own task id.
            return work_id is None and other_work_id is None
        if int(other_work_id) != int(work_id):
            return False
        other_chapter_id = task.get("chapter_id")
        # A work-wide task (outline, settings, delete) conflicts with every
        # operation in that work. Chapter tasks only conflict on the same chapter.
        if chapter_id is None or other_chapter_id is None:
            return True
        return int(other_chapter_id) == int(chapter_id)

    def _claim_chapter_locked(self, owner_id: str, work_id: int | None, chapter_id: int | None) -> None:
        if work_id is None or chapter_id is None:
            return
        key = (int(work_id), int(chapter_id))
        current = self._chapter_owners.get(key)
        if current and current != owner_id:
            raise ValueError("该章节正在执行其他生成或保存操作，请等待完成后重试。")
        self._chapter_owners[key] = owner_id

    def _release_task_chapter_locked(self, task_id: str, task: dict[str, Any]) -> None:
        work_id = task.get("work_id")
        chapter_id = task.get("chapter_id")
        if work_id is None or chapter_id is None:
            return
        key = (int(work_id), int(chapter_id))
        if self._chapter_owners.get(key) == task_id:
            self._chapter_owners.pop(key, None)

    def _recover_interrupted_tasks(self) -> None:
        try:
            for work in self.repo.list_works():
                self.repo.interrupt_unfinished_task_runs(int(work["id"]))
        except Exception:  # noqa: BLE001
            return


STATE = WebState()
