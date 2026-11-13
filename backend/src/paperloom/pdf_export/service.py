"""주석을 넣은 PDF 만들기 (2026-11-13 사용자 요청). 모델·외부 서비스를 부르지 않고, DB는 읽기만 한다."""

from collections.abc import Collection
from contextlib import closing
from pathlib import Path

from paperloom.annotations import repository as annotations
from paperloom.documents import repository as documents
from paperloom.infrastructure.database.sqlite import connect
from paperloom.infrastructure.files.source_store import SourceStore
from paperloom.pdf_export import repository
from paperloom.pdf_export.marks import Part, Thread, Turn, marks_for
from paperloom.pdf_export.writer import write_annotated
from paperloom.reading.repository import anchor_from_row


class PdfExportService:
    def __init__(self, db_path: Path, store: SourceStore, timeout_seconds: float = 60) -> None:
        self._db_path = db_path
        self._store = store
        self._timeout_seconds = timeout_seconds

    def annotated_pdf(self, version_id: str, parts: Collection[Part]) -> bytes | None:
        """원본 PDF에 고른 부분의 표시를 붙인 PDF. 판본이 없으면 None. 실패하면 writer.ExportFailed."""
        with closing(connect(self._db_path)) as connection:
            storage_ref = documents.get_storage_ref(connection, version_id)
            if storage_ref is None:
                return None
            notes = annotations.list_for_version(connection, version_id)
            threads = [
                Thread(
                    row["thread_kind"],
                    anchor_from_row(row),
                    [Turn(turn["prompt"], turn["markdown"]) for turn in repository.list_turns(connection, row["chat_session"])],
                )
                for row in repository.list_threads(connection, version_id)
            ]
        return write_annotated(self._store.path_for(storage_ref), marks_for(notes, threads, parts), self._timeout_seconds)
