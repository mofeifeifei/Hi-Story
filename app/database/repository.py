from __future__ import annotations

from app.database.facets import ChapterRepository, LibraryRepository, RunLogRepository, WorkRepository
from app.database.repository_legacy import Repository as LegacyRepository


class Repository(LegacyRepository):
    """Compatibility facade for the existing single-file repository API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.works = WorkRepository(self)
        self.chapters = ChapterRepository(self)
        self.library = LibraryRepository(self)
        self.runs = RunLogRepository(self)
