"""Wiki로 내보내기: 고른 판본·Anchor·메모·답변·제안·추출문을 Evidence Bundle로 outbox에 쓴다 (docs/integration/paperloom).

Paperloom 쪽 일은 bundle을 쓰는 데서 끝난다. LLM Wiki를 부르거나 알리지 않고, 모델을 부르지 않고, 원본 PDF를 넣지 않는다.
미리보기와 생성은 같은 내용을 계산한다(미리보기는 쓰지 않는다). 생성은 그때의 Anchor·메모로 다시 계산한다.
로그에는 ID·코드·크기만 남기고 인용·메모·답변 글은 남기지 않는다.
"""

import json
import logging
import uuid
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from paperloom import __version__
from paperloom.annotations import repository as annotations
from paperloom.answers.service import AnswerService
from paperloom.context.builder import IMAGE_SCALE, VersionText, anchor_section
from paperloom.context.service import version_text
from paperloom.documents import text_repository
from paperloom.evidence_bundles import repository
from paperloom.evidence_bundles.builder import (
    BUNDLE_SCHEMA,
    BUNDLE_SCHEMA_WITH_TEXTS,
    EXTRACTOR_NAME,
    MANIFEST,
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    NOT_EXTRACTED,
    AnchorEntry,
    BundleContent,
    ProposalEntry,
    SourceEntry,
    TextEntry,
    block_kind,
    build_files,
    file_kind,
    limit_excess,
    near_limit,
    sha256,
)
from paperloom.evidence_bundles.models import (
    BundleCounts,
    BundleDetail,
    BundleFilePreview,
    BundleFileRecord,
    BundleLimits,
    BundleListItem,
    BundleOut,
    BundlePaper,
    BundlePreview,
    BundleRequest,
    BundleWarning,
)
from paperloom.evidence_bundles.outbox import Outbox
from paperloom.evidence_bundles.selection import BundleRefused, SelectedPaper, Selection, select
from paperloom.infrastructure.clock import utc_now
from paperloom.infrastructure.database.sqlite import connect
from paperloom.reading.models import AnchorOut
from paperloom.reading.region_image import RenderFailed
from paperloom.reading.service import AnchorService

log = logging.getLogger("paperloom")


@dataclass(frozen=True)
class _Draft:
    files: dict[str, bytes]
    warnings: list[BundleWarning]
    unready: list[str]  # 고른 쪽이 모두 추출 전인 판본
    counts: BundleCounts
    schema_version: str


class EvidenceBundleService:
    def __init__(self, db_path: Path, anchors: AnchorService, answers: AnswerService, outbox: Outbox) -> None:
        self._db_path = db_path
        self._anchors = anchors
        self._answers = answers
        self._outbox = outbox

    def preview(self, request: BundleRequest, base_url: str) -> BundlePreview:
        """만들 bundle을 계산만 한다. 쓰지 않는다. 한도를 넘거나 추출 전이면 경고로 알린다(생성은 거부한다)."""
        self._require_outbox()
        selection = self._select(request)
        draft = self._draft(request, selection, base_url, str(uuid.uuid4()), utc_now())
        # 파일 목록은 manifest가 먼저 보이게 둔다(쓰는 차례는 맨 뒤다)
        paths = sorted(draft.files, key=lambda path: path != MANIFEST)
        return BundlePreview(
            file_count=len(draft.files),
            total_bytes=sum(map(len, draft.files.values())),
            files=[BundleFilePreview(path=path, kind=file_kind(path), size_bytes=len(draft.files[path])) for path in paths],
            auto_added_anchors=selection.auto_added,
            warnings=draft.warnings,
            limits=BundleLimits(max_files=MAX_FILES, max_file_bytes=MAX_FILE_BYTES, max_total_bytes=MAX_TOTAL_BYTES),
            schema_version=draft.schema_version,
        )

    def create(self, request: BundleRequest, base_url: str) -> BundleOut:
        """outbox에 bundle을 쓰고 기록을 남긴다. 입력 오류는 기록하지 않고, 쓰려다 실패한 것은 failed로 기록한다."""
        selection = self._select(request)
        bundle_id, created_at = str(uuid.uuid4()), utc_now()
        try:
            self._require_outbox()
            draft = self._draft(request, selection, base_url, bundle_id, created_at)
            if draft.unready:
                raise BundleRefused("TEXT_NOT_READY", {"version_ids": draft.unready})
            if excess := limit_excess(draft.files):
                raise BundleRefused("BUNDLE_TOO_LARGE", excess)
            self._write(bundle_id, draft.files)
        except BundleRefused as refused:
            self._record(bundle_id, selection, created_at, error_code=refused.code)
            log.warning("bundle %s를 내보내지 못했습니다: %s", bundle_id, refused.code)
            raise
        self._record(bundle_id, selection, created_at, draft=draft)
        log.info("bundle %s를 내보냈습니다: 파일 %d개, %d바이트", bundle_id, len(draft.files), sum(map(len, draft.files.values())))
        return self._out(self._row(bundle_id))

    def list(self, limit: int) -> list[BundleListItem]:
        with closing(connect(self._db_path)) as connection:
            rows = repository.list_bundles(connection, limit)
        return [
            BundleListItem(
                bundle_id=row["bundle_id"],
                status=row["status"],
                created_at=row["created_at"],
                file_count=row["file_count"],
                size_bytes=row["size_bytes"],
                papers=json.loads(row["papers_json"]),
                present_in_outbox=self._outbox.holds(row["bundle_id"]),
            )
            for row in rows
        ]

    def get(self, bundle_id: str) -> BundleDetail | None:
        row = self._row(bundle_id)
        if row is None:
            return None
        return BundleDetail(
            **self._out(row).model_dump(),
            files=[BundleFileRecord(**item) for item in json.loads(row["files_json"])],
            error_code=row["error_code"],
            present_in_outbox=self._outbox.holds(bundle_id),
        )

    def _select(self, request: BundleRequest) -> Selection:
        return select(request, self._db_path, self._anchors, self._answers)

    def _require_outbox(self) -> None:
        if self._outbox.status() != "ready":
            raise BundleRefused("OUTBOX_UNAVAILABLE")

    def _write(self, bundle_id: str, files: dict[str, bytes]) -> None:
        try:
            self._outbox.write(bundle_id, files)
        except OSError as error:
            log.warning("bundle %s를 쓰다 실패했습니다: %s", bundle_id, type(error).__name__)
            raise BundleRefused("BUNDLE_WRITE_FAILED") from error

    def _row(self, bundle_id: str):
        with closing(connect(self._db_path)) as connection:
            return repository.get_bundle(connection, bundle_id)

    @staticmethod
    def _out(row) -> BundleOut:
        return BundleOut(
            bundle_id=row["bundle_id"],
            directory=f"bundle_{row['bundle_id']}",
            status=row["status"],
            schema_version=row["schema_version"],
            manifest_sha256=row["manifest_sha256"],
            file_count=row["file_count"],
            size_bytes=row["size_bytes"],
            papers=json.loads(row["papers_json"]),
            counts=json.loads(row["counts_json"]),
            created_at=row["created_at"],
        )

    def _record(
        self, bundle_id: str, selection: Selection, created_at: str, *, draft: _Draft | None = None, error_code: str | None = None
    ) -> None:
        papers = [
            BundlePaper(paper_id=item.paper.paper_id, version_id=item.version.version_id, title=item.paper.title).model_dump()
            for item in selection.papers
        ]
        files = draft.files if draft else {}
        with closing(connect(self._db_path)) as connection, connection:
            repository.insert_bundle(
                connection,
                bundle_id=bundle_id,
                status="written" if draft else "failed",
                error_code=error_code,
                schema_version=draft.schema_version if draft else None,
                manifest_sha256=sha256(files[MANIFEST]) if draft else None,
                file_count=len(files),
                size_bytes=sum(map(len, files.values())),
                papers=papers,
                counts=(draft.counts if draft else BundleCounts(anchors=0, proposals=0, answers=0, assets=0, texts=0)).model_dump(),
                files=[{"path": path, "sha256": sha256(data), "size_bytes": len(data)} for path, data in files.items()],
                created_at=created_at,
            )

    def _draft(self, request: BundleRequest, selection: Selection, base_url: str, bundle_id: str, created_at: str) -> _Draft:
        """파일 내용과 경고를 계산한다. 한도를 넘을 것이 뻔하면 이미지를 그리지 않는다(자리만 두고 크기는 0이다)."""
        warnings: list[BundleWarning] = []
        unready: list[str] = []
        sources: list[SourceEntry] = []
        wanted = {item.version.version_id: _text_pages(item) for item in selection.papers}
        planned = 3 + 2 * len(request.proposals) + len(selection.answers) + sum(map(bool, wanted.values()))
        planned += sum(len(_regions(item)) for item in selection.papers if item.choice.include_region_images)
        with closing(connect(self._db_path)) as connection:
            for item in selection.papers:
                version_id = item.version.version_id
                text = version_text(connection, version_id, None)
                rows = {row["page_index"]: row for row in text_repository.list_pages(connection, version_id)}
                comments = _comments(connection, version_id) if item.choice.include_comments else {}
                images = self._images(item, render=planned <= MAX_FILES)
                ordered = sorted(item.anchors.values(), key=lambda anchor: (anchor.page_index, anchor.quads[0][1], anchor.quads[0][0]))
                anchors = [
                    AnchorEntry(
                        anchor=anchor,
                        page_label=rows[anchor.page_index]["page_label"] if anchor.page_index in rows else None,
                        section=anchor_section(anchor, text),
                        comment=comments.get(anchor.anchor_id),
                        image=images.get(anchor.anchor_id),
                    )
                    for anchor in ordered
                ]
                pages = wanted[version_id]
                entry = _text_entry(connection, text, rows, pages) if pages else None
                sources.append(SourceEntry(item.paper, item.version, anchors, entry))
                missing = [page for page in pages if page not in rows or "extract_failed" in json.loads(rows[page]["flags_json"])]
                if missing:
                    numbers = ", ".join(str(page + 1) for page in missing)
                    warnings.append(BundleWarning(code="pages_not_extracted", detail=f"{version_id}: {numbers}"))
                if pages and len(missing) == len(pages):
                    unready.append(version_id)
                warnings += _anchor_warnings(version_id, anchors)
        proposals = [
            ProposalEntry(str(uuid.uuid4()), proposal.version_id, proposal.title, proposal.content_markdown, proposal.anchor_ids)
            for proposal in request.proposals
        ]
        files = build_files(BundleContent(bundle_id, created_at, __version__, base_url, sources, proposals, selection.answers))
        warnings += _answer_warnings(selection)
        if excess := limit_excess(files):
            detail = f"파일 {excess['file_count']}개 · {excess['total_bytes']:,}바이트 · 가장 큰 파일 {excess['largest_path']}"
            warnings.append(BundleWarning(code="over_limit", detail=detail))
        elif near_limit(files):
            warnings.append(BundleWarning(code="near_limit", detail=f"파일 {len(files)}개 · {sum(map(len, files.values())):,}바이트"))
        return _Draft(
            files=files,
            warnings=warnings,
            unready=unready,
            counts=BundleCounts(
                anchors=sum(len(entry.anchors) for entry in sources),
                proposals=len(proposals),
                answers=len(selection.answers),
                assets=sum(path.startswith("assets/") for path in files),
                texts=sum(path.startswith("texts/") for path in files),
            ),
            schema_version=BUNDLE_SCHEMA_WITH_TEXTS if any(entry.text for entry in sources) else BUNDLE_SCHEMA,
        )

    def _images(self, item: SelectedPaper, *, render: bool) -> dict[str, bytes]:
        """영역 Anchor의 PNG. 그리지 못한 영역은 빼고 region_without_image로 알린다: 이미지 하나 때문에 내보내기를 막지 않는다."""
        if not item.choice.include_region_images:
            return {}
        images = {}
        for anchor in _regions(item):
            if not render:
                images[anchor.anchor_id] = b""
                continue
            try:
                if (image := self._anchors.image(anchor.anchor_id, IMAGE_SCALE)) is not None:
                    images[anchor.anchor_id] = image
            except RenderFailed:
                log.warning("Anchor %s의 영역 이미지를 그리지 못했습니다.", anchor.anchor_id)
        return images


def _regions(item: SelectedPaper) -> list[AnchorOut]:
    return [anchor for anchor in item.anchors.values() if anchor.kind != "text"]


def _text_pages(item: SelectedPaper) -> list[int]:
    """실을 쪽(0부터, 차례대로)"""
    text = item.choice.text
    if text.mode == "none":
        return []
    if text.mode == "all":
        return list(range(item.version.page_count))
    if text.mode == "anchor_pages":
        return sorted({anchor.page_index for anchor in item.anchors.values()})
    return sorted({page for pages in text.ranges for page in range(pages.start, pages.to + 1)})


def _comments(connection, version_id: str) -> dict[str, str]:
    """Anchor마다 주석 메모. 여러 개면 만든 차례로 빈 줄을 두고 잇는다. 색만 있는 주석은 빈 메모라 뺀다."""
    found: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for item in annotations.list_for_version(connection, version_id):
        if item.comment:
            found[item.anchor.anchor_id].append((item.created_at, item.comment))
    return {anchor_id: "\n\n".join(comment for _, comment in sorted(notes)) for anchor_id, notes in found.items()}


def _text_entry(connection, text: VersionText, rows: dict, pages: list[int]) -> TextEntry:
    blocks = defaultdict(list)
    for block in text.blocks:
        blocks[block.page_index].append(block)
    entries = []
    for page_index in pages:
        row = rows.get(page_index)
        entries.append(
            {
                "page_index": page_index,
                "page_label": row["page_label"] if row else None,
                "text_status": row["text_status"] if row else NOT_EXTRACTED,
                "flags": json.loads(row["flags_json"]) if row else [],
                "blocks": [
                    {
                        "block_id": block.block_id,
                        "order": order,
                        "kind": block_kind(block, text.headings),
                        "section": text.sections.get(block.block_id),
                        "text": block.text,
                        "display_text": None,  # 추출 문단에는 첨자 추정 표기가 없다(글 선택에만 있다)
                    }
                    for order, block in enumerate(blocks[page_index], start=1)
                ],
            }
        )
    # 판본의 쪽은 모두 같은 추출에서 나온다
    run = text_repository.get_run_details(connection, next(iter(rows.values()))["parse_run_id"]) if rows else None
    extractor = {
        "name": EXTRACTOR_NAME,
        "version": run["parser_version"] if run else None,
        "parse_run_id": run["parse_run_id"] if run else None,
        "finished_at": run["finished_at"] if run else None,
    }
    return TextEntry(extractor, entries)


def _anchor_warnings(version_id: str, anchors: list[AnchorEntry]) -> list[BundleWarning]:
    warnings = []
    without_image = sum(entry.anchor.kind != "text" and entry.image is None for entry in anchors)
    if without_image:
        warnings.append(BundleWarning(code="region_without_image", detail=f"{version_id}: {without_image}개"))
    empty = sum(entry.anchor.kind == "text" and not entry.anchor.quote for entry in anchors)
    if empty:
        warnings.append(BundleWarning(code="empty_quote", detail=f"{version_id}: {empty}개"))
    return warnings


def _answer_warnings(selection: Selection) -> list[BundleWarning]:
    included = {anchor_id for item in selection.papers for anchor_id in item.anchors}
    warnings = []
    for answer in selection.answers:
        unresolved = [citation.number for citation in answer.citations if citation.anchor_id not in included]
        unresolved += answer.unresolved_citations
        if unresolved:
            numbers = ", ".join(str(number) for number in dict.fromkeys(unresolved))
            warnings.append(BundleWarning(code="unresolved_answer_citation", detail=f"{answer.answer_id}: 근거 {numbers}"))
    return warnings
