from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.database.repository import Repository
from app.services.ai_client import AIClient
from app.utils.config import load_config
from app.workflow import NovelWorkflow


def now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


class WebState:
    def __init__(self) -> None:
        self.repo = Repository()
        self.workflow = NovelWorkflow(repo=self.repo, client=AIClient())
        self.custom_export_dirs: dict[int, Path] = {}
        self._tasks: dict[str, dict[str, Any]] = {}
        self._task_lock = threading.Lock()

    def reload_config(self) -> None:
        self.workflow = NovelWorkflow(repo=self.repo, client=AIClient(load_config()))

    def start_task(self, task_id: str, *, kind: str = "", title: str = "") -> None:
        if not task_id:
            return
        with self._task_lock:
            self._tasks[task_id] = {
                "id": task_id,
                "kind": kind,
                "title": title,
                "status": "running",
                "started_at": now_text(),
                "finished_at": "",
                "error": "",
            }

    def cancel_task(self, task_id: str) -> None:
        if not task_id:
            return
        with self._task_lock:
            task = self._tasks.setdefault(
                task_id,
                {
                    "id": task_id,
                    "kind": "",
                    "title": "",
                    "started_at": now_text(),
                    "finished_at": "",
                    "error": "",
                },
            )
            if task.get("status") not in {"done", "failed", "cancelled"}:
                task["status"] = "cancelling"

    def task_cancelled(self, task_id: str) -> bool:
        if not task_id:
            return False
        with self._task_lock:
            return self._tasks.get(task_id, {}).get("status") in {"cancelling", "cancelled"}

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

    def task_status(self, task_id: str) -> dict[str, Any]:
        if not task_id:
            return {}
        with self._task_lock:
            return dict(self._tasks.get(task_id, {}))


STATE = WebState()
