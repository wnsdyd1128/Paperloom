"""주석을 넣은 PDF 만들기 (2026-11-13 사용자 요청). 모델·외부 서비스를 부르지 않고, DB는 읽기만 한다.

바탕은 원본 PDF이거나, 레이아웃 유지 번역본(2026-11-15 사용자 요청)이다. 번역본은 저장된 쪽 번역만 쓰고 번역을 실행하지 않는다.
"""

import json
from collections.abc import Collection
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from paperloom.annotations import repository as annotations
from paperloom.documents import repository as documents
from paperloom.documents import text_repository
from paperloom.infrastructure.database.sqlite import connect
from paperloom.infrastructure.files.source_store import SourceStore
from paperloom.pdf_export import repository
from paperloom.pdf_export.marks import Part, Thread, Turn, marks_for
from paperloom.pdf_export.translated import TranslatedBlock, TranslatedPage, highlight_targets, sentence_groups
from paperloom.pdf_export.typeset import whole_mark
from paperloom.pdf_export.writer import write_annotated
from paperloom.reading.models import AnchorOut
from paperloom.reading.repository import anchor_from_row
from paperloom.translation.models import Language
from paperloom.translation.service import TextNotReady, TranslationService


@dataclass(frozen=True)
class TranslatedBase:
    """번역본 바탕: 번역 언어와 번역 글꼴 배율(웹 레이아웃 유지 번역의 글꼴 단추, 원문 글자 크기 기준)."""

    language: Language
    scale: float = 1.0


class PdfExportService:
    def __init__(self, db_path: Path, store: SourceStore, timeout_seconds: float = 60) -> None:
        self._db_path = db_path
        self._store = store
        self._timeout_seconds = timeout_seconds
        self._translations = TranslationService(db_path)

    def annotated_pdf(self, version_id: str, parts: Collection[Part], base: TranslatedBase | None = None) -> bytes | None:
        """고른 부분의 표시를 붙인 PDF. base가 있으면 번역한 쪽을 번역문으로 덮는다. 판본이 없으면 None.
        실패하면 writer.ExportFailed."""
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
            pages = self._translated_pages(connection, version_id, base.language) if base else []
        translated = {page.page_index: page for page in pages}

        def targets_for(anchor: AnchorOut) -> tuple[tuple[str, int], ...]:
            page = translated.get(anchor.page_index)
            if page is None or anchor.kind != "text":
                return ()
            return highlight_targets(anchor.quote, anchor.prefix, anchor.suffix, page.blocks)

        marks = marks_for(notes, threads, parts, targets_for)
        return write_annotated(self._store.path_for(storage_ref), marks, self._timeout_seconds, pages, base.scale if base else 1.0)

    def _translated_pages(self, connection, version_id: str, language: Language) -> list[TranslatedPage]:
        """지금 문단과 맞는 번역이 저장된 쪽들. 다시 추출해 글이 바뀐 쪽과 추출 중인 판본은 번역하지 않은 것으로 본다."""
        pages = []
        for page_index in self._translations.pages(version_id, language).pages:
            try:
                translation = self._translations.get(version_id, page_index, language)
            except TextNotReady:
                return []
            if translation is None:
                continue
            rows = {row["block_id"]: row for row in text_repository.page_blocks(connection, version_id, page_index)}
            blocks = []
            for item in translation.blocks:
                row = rows[item.block_id]
                blocks.append(
                    TranslatedBlock(
                        item.block_id,
                        row["text"],
                        json.loads(row["regions_json"]),
                        row["font_size"],
                        whole_mark(row["text"], json.loads(row["styles_json"] or "[]")),
                        sentence_groups(item.sentences),
                    )
                )
            pages.append(TranslatedPage(page_index, blocks))
        return pages
