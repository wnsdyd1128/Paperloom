"""PDF 등록 흐름과 버전·쪽 조회 (IMPL §4.2, §5.1).

순서: 헤더 검사 → 격리 프로세스에서 PDF 검사 → 중복 확인 → 원본을 원자적으로 이동 → DB commit(본문 추출 작업 포함).
DB commit이 끝나야 Library에 보인다. 실패하면 이번 업로드의 임시 파일·사본만 지운다.
"""

import json
import logging
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from paperloom.documents import repository, text_repository
from paperloom.documents.extract import ExtractFailed, extract_pages
from paperloom.documents.headings import headings
from paperloom.documents.inspect import PdfRejected, clean_text, inspect_pdf
from paperloom.documents.models import (
    HeadingList,
    HeadingOut,
    PageList,
    PageOut,
    PageTextOut,
    PaperMetadataIn,
    PaperOut,
    PaperTagsIn,
    TagRenameIn,
    TextBlockOut,
    VersionOut,
)
from paperloom.documents.parsing import ParseService
from paperloom.documents.titles import looks_like_filename, title_from_blocks
from paperloom.infrastructure.clock import utc_now
from paperloom.infrastructure.database.sqlite import connect
from paperloom.infrastructure.files.source_store import ReceivedFile, SourceStore

READY_TO_READ = "READY_TO_READ"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class UploadLimits:
    """초기 제품 제한 제안 (IMPL §5.1). ChatGPT·Claude의 업로드 한도와 무관하다."""

    max_bytes: int = 100 * 1024 * 1024
    max_pages: int = 300
    inspect_timeout_seconds: float = 30


class UploadRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DuplicateSource(Exception):
    def __init__(self, paper_id: str) -> None:
        super().__init__(paper_id)
        self.paper_id = paper_id


class TextNotReady(Exception):
    """버전의 본문 추출이 아직 끝나지 않았다."""


class PaperBusy(Exception):
    """본문을 추출하는 중이라 지울 수 없다(worker가 그 논문에 쓰는 중이다)."""


class DocumentService:
    def __init__(self, store: SourceStore, db_path: Path, limits: UploadLimits, parsing: ParseService) -> None:
        self.store = store
        self.limits = limits
        self._db_path = db_path
        self._parsing = parsing

    def register(self, received: ReceivedFile, filename: str) -> PaperOut:
        try:
            return self._register(received, filename)
        finally:
            received.path.unlink(missing_ok=True)  # 원본 위치로 옮겨졌다면 이미 없다

    def _register(self, received: ReceivedFile, filename: str) -> PaperOut:
        if b"%PDF-" not in received.head:
            raise UploadRejected("NOT_PDF")
        try:
            info = inspect_pdf(received.path, self.limits.inspect_timeout_seconds)
        except PdfRejected as rejected:
            raise UploadRejected(rejected.code) from None
        if info.page_count == 0:
            raise UploadRejected("MALFORMED_PDF")
        if info.page_count > self.limits.max_pages:
            raise UploadRejected("RESOURCE_LIMIT")
        # 메타데이터 제목이 없거나 파일 이름 같으면 첫 쪽에서 찾는다(2026-10-05). 못 찾으면 파일 이름이다.
        metadata_title = info.title if info.title and not looks_like_filename(info.title) else None
        title = metadata_title or self._first_page_title(received.path) or info.title or title_from_filename(filename)

        with closing(connect(self._db_path)) as connection:
            existing = repository.find_paper_id_by_sha256(connection, received.sha256)
            if existing:
                raise DuplicateSource(existing)
            paper_id, version_id = str(uuid.uuid4()), str(uuid.uuid4())
            storage_ref = self.store.commit(received, version_id)
            try:
                with connection:
                    repository.insert_paper(
                        connection,
                        paper_id=paper_id,
                        version_id=version_id,
                        title=title,
                        sha256=received.sha256,
                        size_bytes=received.size_bytes,
                        page_count=info.page_count,
                        storage_ref=storage_ref,
                        status=READY_TO_READ,
                        created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    )
                    self._parsing.enqueue(connection, version_id)
            except sqlite3.IntegrityError:
                self.store.remove_committed(storage_ref)
                # 같은 바이트의 동시 업로드가 먼저 등록된 경우 (sha256 UNIQUE). 그 밖의 위반은 그대로 올린다.
                existing = repository.find_paper_id_by_sha256(connection, received.sha256)
                if existing is None:
                    raise
                raise DuplicateSource(existing) from None
            except BaseException:
                self.store.remove_committed(storage_ref)
                raise
            paper = repository.get_paper(connection, paper_id)
        assert paper is not None
        self._parsing.notify()
        return paper

    def _first_page_title(self, path: Path) -> str | None:
        """첫 쪽에서 찾은 제목(documents.titles). 첫 쪽을 읽지 못하면 None이다(등록은 그대로 하고 파일 이름을 쓴다)."""
        try:
            [page] = extract_pages(path, 0, 1, self.limits.inspect_timeout_seconds)
        except (ExtractFailed, OSError, ValueError):
            return None
        return title_from_blocks(page["blocks"])

    def list_papers(self) -> list[PaperOut]:
        with closing(connect(self._db_path)) as connection:
            return repository.list_papers(connection)

    def get_paper(self, paper_id: str) -> PaperOut | None:
        with closing(connect(self._db_path)) as connection:
            return repository.get_paper(connection, paper_id)

    def update_metadata(self, paper_id: str, metadata: PaperMetadataIn) -> PaperOut | None:
        """사용자가 고친 제목·저자·연도·DOI (D5). 논문이 없으면 None."""
        with closing(connect(self._db_path)) as connection, connection:
            fields = metadata.model_dump()
            if not repository.update_metadata(connection, paper_id, **fields):
                return None
            return repository.get_paper(connection, paper_id)

    def set_tags(self, paper_id: str, request: PaperTagsIn) -> PaperOut | None:
        """논문의 태그를 바꾼다 (U6). 논문이 없으면 None."""
        with closing(connect(self._db_path)) as connection, connection:
            if repository.get_paper(connection, paper_id) is None:
                return None
            repository.set_tags(connection, paper_id, request.tags, utc_now())
            return repository.get_paper(connection, paper_id)

    def rename_tag(self, name: str, request: TagRenameIn) -> bool:
        """서재 태그 메뉴의 이름 바꾸기 (2026-10-04). 태그가 없으면 False."""
        with closing(connect(self._db_path)) as connection, connection:
            return repository.rename_tag(connection, name, request.name)

    def delete_tag(self, name: str) -> bool:
        """서재 태그 메뉴의 지우기 (2026-10-04). 태그가 없으면 False."""
        with closing(connect(self._db_path)) as connection, connection:
            return repository.delete_tag(connection, name)

    def delete_paper(self, paper_id: str) -> bool:
        """논문과 그 기록을 모두 지운다(되돌릴 수 없다, 2026-10-05 서재 지우기). 없으면 False, 본문 추출 중이면 PaperBusy.
        DB를 한 트랜잭션으로 지운 뒤 원본 PDF를 지운다. 파일을 지우지 못하면(다른 곳에서 열려 있는 등) 기록만 남긴다."""
        with closing(connect(self._db_path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")  # worker가 대기 중인 작업을 가져가지 못하게 쓰기 잠금부터 잡는다
            if repository.extracting(connection, paper_id):
                raise PaperBusy()
            storage_refs = repository.delete_paper(connection, paper_id)
        if storage_refs is None:
            return False
        for storage_ref in storage_refs:
            try:
                self.store.delete(storage_ref)
            except OSError:
                log.warning("지운 논문의 원본 파일을 지우지 못했습니다: %s", storage_ref, exc_info=True)
        return True

    def mark_opened(self, paper_id: str) -> bool:
        """Reader로 연 때를 남긴다 (U6 서재의 마지막 열람). 논문이 없으면 False."""
        with closing(connect(self._db_path)) as connection, connection:
            return repository.mark_opened(connection, paper_id, utc_now())

    def headings(self, version_id: str) -> HeadingList | None:
        """본문 제목으로 만든 목차 (D6). 버전이 없으면 None, 추출 전이면 TextNotReady."""
        with closing(connect(self._db_path)) as connection:
            pages = text_repository.list_pages(connection, version_id)
            if repository.get_version(connection, version_id) is None:
                return None
            if not pages:
                raise TextNotReady()
            blocks = text_repository.blocks_on_pages(connection, version_id, [page["page_index"] for page in pages])
        by_page: dict[int, list[sqlite3.Row]] = {page["page_index"]: [] for page in pages}
        for block in blocks:
            by_page[block["page_index"]].append(block)
        regions = {block["block_id"]: json.loads(block["regions_json"]) for block in blocks}
        found = headings(
            [
                {"page_index": index, "blocks": [{"text": block["text"], "regions": regions[block["block_id"]]} for block in rows]}
                for index, rows in by_page.items()
            ]
        )
        items = []
        for item in found:
            block_id = by_page[item["page_index"]][item["order"]]["block_id"]
            items.append(
                HeadingOut(title=item["title"], page_index=item["page_index"], level=item["level"], block_id=block_id, box=regions[block_id][0])
            )
        return HeadingList(version_id=version_id, headings=items)

    def get_version(self, version_id: str) -> VersionOut | None:
        with closing(connect(self._db_path)) as connection:
            return repository.get_version(connection, version_id)

    def pages(self, version_id: str) -> PageList | None:
        """버전의 쪽별 추출 상태. 버전이 없으면 None."""
        with closing(connect(self._db_path)) as connection:
            version = repository.get_version(connection, version_id)
            if version is None:
                return None
            rows = text_repository.list_pages(connection, version_id)
        return PageList(version_id=version_id, status=version.status, pages=[_page(row) for row in rows])

    def page_text(self, version_id: str, page_index: int) -> PageTextOut | None:
        """쪽의 추출 상태와 문단(읽는 순서). 버전·쪽이 없거나 아직 추출 전이면 None."""
        with closing(connect(self._db_path)) as connection:
            row = text_repository.get_page(connection, version_id, page_index)
            if row is None:
                return None
            blocks = text_repository.page_blocks(connection, version_id, page_index)
        return PageTextOut(
            **_page(row).model_dump(),
            version_id=version_id,
            blocks=[
                TextBlockOut(
                    block_id=block["block_id"],
                    reading_order=block["reading_order"],
                    text=block["text"],
                    regions=json.loads(block["regions_json"]),
                    quality_flags=json.loads(block["quality_flags_json"]),
                    styles=json.loads(block["styles_json"]),
                    font_size=block["font_size"],
                )
                for block in blocks
            ],
        )

    def source_path(self, version_id: str) -> Path | None:
        with closing(connect(self._db_path)) as connection:
            storage_ref = repository.get_storage_ref(connection, version_id)
        return self.store.path_for(storage_ref) if storage_ref else None


def _page(row: sqlite3.Row) -> PageOut:
    return PageOut(
        page_index=row["page_index"],
        page_label=row["page_label"],
        text_status=row["text_status"],
        flags=json.loads(row["flags_json"]),
        quality=json.loads(row["quality_json"]),
    )


def title_from_filename(filename: str) -> str:
    """경로 성분을 버리고 파일 이름만 제목 후보로 쓴다. 저장 경로에는 쓰지 않는다."""
    name = PurePosixPath(filename.replace("\\", "/")).name
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    return clean_text(name) or "제목 없음"
