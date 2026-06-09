from __future__ import annotations

from typing import Any


class WorkRepository:
    def __init__(self, repo: Any):
        self.repo = repo

    def list(self) -> list[dict[str, Any]]:
        return self.repo.list_works()

    def get(self, work_id: int) -> dict[str, Any]:
        return self.repo.get_work(work_id)

    def bundle(self, work_id: int) -> dict[str, Any]:
        return self.repo.get_work_bundle(work_id)

    def create_empty(self, inputs: dict[str, Any]) -> int:
        return self.repo.create_empty_work(inputs)

    def delete(self, work_id: int) -> None:
        self.repo.delete_work(work_id)


class ChapterRepository:
    def __init__(self, repo: Any):
        self.repo = repo

    def list(self, work_id: int) -> list[dict[str, Any]]:
        return self.repo.list_chapters(work_id)

    def get(self, work_id: int, chapter_number: int) -> dict[str, Any]:
        return self.repo.get_chapter(work_id, chapter_number)

    def save_draft(self, work_id: int, chapter_id: int, draft: str) -> None:
        self.repo.save_draft(work_id, chapter_id, draft)

    def save_final(self, work_id: int, chapter_id: int, final_text: str, *, title: str | None = None) -> None:
        self.repo.save_final(work_id, chapter_id, final_text, title=title)

    def delete(self, work_id: int, chapter_number: int, *, delete_related: bool = True) -> bool:
        return self.repo.delete_chapter(work_id, chapter_number, delete_related=delete_related)


class LibraryRepository:
    def __init__(self, repo: Any):
        self.repo = repo

    def list_characters(self, work_id: int) -> list[dict[str, Any]]:
        return self.repo.list_characters(work_id)

    def list_plot_threads(self, work_id: int, status: str | None = None) -> list[dict[str, Any]]:
        return self.repo.list_plot_threads(work_id, status=status)

    def list_timeline(self, work_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        return self.repo.list_timeline(work_id, limit=limit)

    def list_notes(self, work_id: int, chapter_number: int | None = None) -> list[dict[str, Any]]:
        return self.repo.list_chapter_notes(work_id, chapter_number=chapter_number)


class RunLogRepository:
    def __init__(self, repo: Any):
        self.repo = repo

    def log_agent_run(
        self,
        *,
        work_id: int | None,
        chapter_id: int | None,
        agent_name: str,
        model: str,
        prompt_name: str,
        input_preview: str,
        output: str,
        status: str = "ok",
        error: str = "",
        input_chars: int = 0,
        output_chars: int = 0,
        estimated_input_tokens: int = 0,
        estimated_output_tokens: int = 0,
        estimated_total_tokens: int = 0,
        elapsed_seconds: float = 0,
    ) -> int:
        return self.repo.log_agent_run(
            work_id=work_id,
            chapter_id=chapter_id,
            agent_name=agent_name,
            model=model,
            prompt_name=prompt_name,
            input_preview=input_preview,
            output=output,
            status=status,
            error=error,
            input_chars=input_chars,
            output_chars=output_chars,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            estimated_total_tokens=estimated_total_tokens,
            elapsed_seconds=elapsed_seconds,
        )

    def list(self, work_id: int, limit: int = 100) -> list[dict[str, Any]]:
        return self.repo.list_agent_runs(work_id, limit=limit)
