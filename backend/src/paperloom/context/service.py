"""ContextPacket 만들기·조회·전달 상태·내보내기 (IMPL §7.2–7.3).

근거 텍스트는 서버가 저장한 Anchor(인용)와 추출 문단에서 가져온다. 클라이언트가 보낸 글을 근거로 쓰지 않는다.
모델·외부 서비스를 호출하지 않는다. packet은 사용자 소유 범위의 Anchor로만 만든다.
"""

import hashlib
import io
import json
import statistics
import uuid
import zipfile
from contextlib import closing
from pathlib import Path

from paperloom.context import repository
from paperloom.context.builder import MAX_IMAGES, PAGE_REACH, PAGE_TEXT_CHARS, Block, Choice, VersionText, build, page_texts
from paperloom.context.export import ImageMode, render_markdown
from paperloom.context.models import (
    DEFAULT_PAPER_TEXT_CHARS,
    ContextPacketIn,
    ContextPacketOut,
    Limits,
    PacketContent,
    PacketStatusPatch,
    Source,
)
from paperloom.documents import repository as documents
from paperloom.documents import text_repository
from paperloom.documents.headings import headings, section_paths
from paperloom.documents.references import REFERENCES_FLAG
from paperloom.infrastructure.clock import utc_now
from paperloom.infrastructure.database.sqlite import connect
from paperloom.reading.service import AnchorService
from paperloom.preferences.service import PreferenceService


class InvalidPacket(Exception):
    def __init__(self, message: str, details: dict) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class InvalidTransition(Exception):
    def __init__(self, status: str) -> None:
        super().__init__(status)
        self.status = status


class ContextService:
    def __init__(self, db_path: Path, anchors: AnchorService, preferences: PreferenceService | None = None) -> None:
        self._db_path = db_path
        self._anchors = anchors
        self._preferences = preferences  # 논문 본문 한도의 기본값 (U6 설정, D2)

    def _paper_text_chars(self) -> int:
        """요청에 한도가 없을 때: 저장된 설정, 설정이 없으면 기본 한도"""
        return self._preferences.get().paper_text_chars if self._preferences else DEFAULT_PAPER_TEXT_CHARS

    def create(self, request: ContextPacketIn) -> ContextPacketOut:
        """고른 위치의 근거를 먼저, 범위가 쪽·논문 본문·어느 쪽까지면 그 본문을 이어서 넣는다 (docs/UI_PLAN.md U3).
        어느 쪽까지(until_page)는 앞쪽부터 그 쪽까지와 그 뒤의 참고문헌 쪽이다. 한도에 걸리면 뒤쪽(참고문헌부터)이 빠진다.
        쪽 둘레(around_page)는 그 쪽과 앞뒤 한 쪽, 그리고 참고문헌 쪽이다(쪽 차례로)."""
        scope = request.resolved_scope
        choices = []
        for index, item in enumerate(request.anchors):
            anchor = self._anchors.get(item.anchor_id)  # 소유 범위 밖은 없는 것과 같다
            if anchor is None:
                raise InvalidPacket("원문 위치를 찾을 수 없습니다.", {"field": "anchors", "index": index})
            choices.append(Choice(anchor, item.include_context, item.include_image))
        scoped = request.version_id if scope != "selection" else None
        scope_page = request.page_index
        versions = list(dict.fromkeys([*(choice.anchor.version_id for choice in choices), *([scoped] if scoped else [])]))
        source_refs = {version_id: f"src_{number}" for number, version_id in enumerate(versions, start=1)}
        sources, texts = [], {}
        with closing(connect(self._db_path)) as connection:
            for version_id in versions:
                version = documents.get_version(connection, version_id)
                if version is None:  # 고른 위치의 버전은 있으므로 범위의 버전이다
                    raise InvalidPacket("논문 버전을 찾을 수 없습니다.", {"field": "version_id"})
                if version_id == scoped and scope in ("page", "around_page") and request.page_index >= version.page_count:
                    raise InvalidPacket("그 쪽이 논문에 없습니다.", {"field": "page_index"})
                paper = documents.get_paper(connection, version.paper_id)
                sources.append(
                    Source(
                        source_ref=source_refs[version_id],
                        paper_id=version.paper_id,
                        title=paper.title,
                        version_id=version_id,
                        sha256=version.sha256,
                    )
                )
                if version_id == scoped and scope == "until_page":
                    scope_page = min(request.page_index, version.page_count - 1)  # 넘으면 문서 끝까지
                anchor_pages = [c.anchor.page_index for c in choices if c.anchor.version_id == version_id]
                whole = version_id == scoped and scope in ("paper", "until_page", "around_page")  # 참고문헌 쪽도 읽는다
                pages = None if whole else anchor_pages + ([request.page_index] if version_id == scoped else [])
                texts[version_id] = _version_text(connection, version_id, pages)
        evidence, limits = build(choices, texts, source_refs) if choices else ([], None)
        if scoped:
            budget = PAGE_TEXT_CHARS if scope == "page" else (request.paper_text_chars or self._paper_text_chars())
            wanted = [request.page_index] if scope == "page" else None
            if scope == "until_page":
                text = texts[scoped]
                references = [page for page, (_, flags) in text.pages.items() if REFERENCES_FLAG in flags and page > scope_page]
                wanted = [*range(scope_page + 1), *sorted(references)]
            if scope == "around_page":
                text = texts[scoped]
                window = {page for page in (scope_page - 1, scope_page, scope_page + 1) if page in text.pages}
                references = {page for page, (_, flags) in text.pages.items() if REFERENCES_FLAG in flags}
                wanted = sorted(window | references)
            text_evidence, used, excluded = page_texts(texts[scoped], wanted, budget, source_refs[scoped], scoped, len(evidence) + 1)
            limits = _with_scope_text(limits, budget, used, text_evidence, excluded)
            evidence = [*evidence, *text_evidence]
        return self._store(request, evidence, limits, sources, scope_page)

    def _store(self, request: ContextPacketIn, evidence, limits, sources, scope_page: int | None) -> ContextPacketOut:
        content = PacketContent(
            intent=request.intent,
            question=request.question,
            evidence=evidence,
            sources=sources,
            limits=limits,
            scope=request.resolved_scope,
            scope_page=scope_page,
        )
        digest = content_sha256(content)
        packet_id, created_at = str(uuid.uuid4()), utc_now()
        with closing(connect(self._db_path)) as connection, connection:
            repository.insert_packet(connection, packet_id, content.model_dump_json(), digest, created_at)
        return ContextPacketOut(**content.model_dump(), packet_id=packet_id, created_at=created_at, content_sha256=digest, status="PREPARED")

    def get(self, packet_id: str) -> ContextPacketOut | None:
        with closing(connect(self._db_path)) as connection:
            row = repository.get_packet(connection, packet_id)
        if row is None:
            return None
        return ContextPacketOut(
            **json.loads(row["content_json"]),
            packet_id=row["packet_id"],
            created_at=row["created_at"],
            content_sha256=row["content_sha256"],
            status=row["status"],
            handed_off_at=row["handed_off_at"],
            handoff_method=row["handoff_method"],
            cancelled_at=row["cancelled_at"],
        )

    def update_status(self, packet_id: str, patch: PacketStatusPatch) -> ContextPacketOut | None:
        """없으면 None. 바꿀 수 없는 상태면 InvalidTransition."""
        with closing(connect(self._db_path)) as connection, connection:
            if patch.status == "HANDED_OFF":
                changed = repository.hand_off(connection, packet_id, patch.handoff_method, utc_now())
            else:
                changed = repository.cancel(connection, packet_id, utc_now())
        packet = self.get(packet_id)
        if packet is not None and not changed:
            raise InvalidTransition(packet.status)
        return packet

    def export_markdown(self, packet_id: str, base_url: str, images: ImageMode = "paste") -> str | None:
        """복사·.md 내보내기(images=attached는 Claude Code 대화 브리지용). 없으면 None, 취소한 packet이면 InvalidTransition."""
        packet = self._exportable(packet_id)
        return render_markdown(packet, base_url, images=images) if packet else None

    def export_zip(self, packet_id: str, base_url: str) -> bytes | None:
        """context.md와 영역 이미지(images/e번호.png). 없으면 None. 그리지 못하면 reading.region_image.RenderFailed."""
        packet = self._exportable(packet_id)
        if packet is None:
            return None
        files = {item.evidence_id: f"images/{item.evidence_id}.png" for item in packet.evidence if item.image}
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("context.md", render_markdown(packet, base_url, files))
            for item in packet.evidence:
                if item.image:
                    archive.writestr(files[item.evidence_id], self._anchors.image(item.anchor_id, item.image.scale) or b"")
        return buffer.getvalue()

    def _exportable(self, packet_id: str) -> ContextPacketOut | None:
        packet = self.get(packet_id)
        if packet is not None and packet.status == "CANCELLED":
            raise InvalidTransition(packet.status)
        return packet


def _with_scope_text(selection: Limits | None, budget: int, used: int, evidence: list, excluded: list) -> Limits:
    """고른 위치의 한도(없으면 0)에 범위 본문의 한도를 더한다. 잘림은 어느 쪽이든 있으면 있다."""
    return Limits(
        max_text_chars=(selection.max_text_chars if selection else 0) + budget,
        used_text_chars=(selection.used_text_chars if selection else 0) + used,
        max_images=MAX_IMAGES,
        used_images=selection.used_images if selection else 0,
        truncated=(selection.truncated if selection else False)
        or any(item.truncated for item in evidence)
        or any(item.reason == "text_budget" for item in excluded),
        excluded=[*(selection.excluded if selection else []), *excluded],
    )


def content_sha256(content: PacketContent) -> str:
    """내용 해시: 키를 정렬한 UTF-8 JSON(공백 없음)의 SHA-256. packet ID·만든 때·상태는 넣지 않는다."""
    canonical = json.dumps(content.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _version_text(connection, version_id: str, anchor_pages: list[int] | None) -> VersionText:
    """고른 쪽과 앞뒤 PAGE_REACH쪽의 문단. anchor_pages가 None이면 모든 쪽. 절(본문 제목 경로)은 모든 쪽에서 찾는다."""
    rows = text_repository.list_pages(connection, version_id)
    pages = {row["page_index"]: (row["text_status"], tuple(json.loads(row["flags_json"]))) for row in rows}
    sizes = {row["page_index"]: json.loads(row["view_box_json"]) or [0, 0, 1, 1] for row in rows}
    if anchor_pages is None:
        wanted = sorted(pages)
    else:
        wanted = sorted({page + offset for page in anchor_pages for offset in range(-PAGE_REACH, PAGE_REACH + 1)})
    every = text_repository.blocks_on_pages(connection, version_id, sorted(pages)) if pages else []
    sections, heading_ids = _sections(every)
    near = set(wanted)
    blocks = []
    for row in (row for row in every if row["page_index"] in near):
        regions = tuple(tuple(region) for region in json.loads(row["regions_json"]))
        x0, y0, x1, y1 = sizes.get(row["page_index"], [0, 0, 1, 1])
        # 줄 상자를 pt로 바꿔 짧은 변을 줄 높이로 쓴다(글줄이 돌아간 쪽에서는 가로 폭이 줄 높이다)
        line_height = statistics.median(min((r[2] - r[0]) * (x1 - x0), (r[3] - r[1]) * (y1 - y0)) for r in regions)
        blocks.append(
            Block(
                block_id=row["block_id"],
                page_index=row["page_index"],
                text=row["text"],
                regions=regions,
                quality_flags=tuple(json.loads(row["quality_flags_json"])),
                line_height=line_height,
            )
        )
    return VersionText(extracted=bool(rows), pages=pages, blocks=blocks, sections=sections, headings=heading_ids)


def _sections(rows) -> tuple[dict[str, str], frozenset[str]]:
    """문단(block_id)마다 그 문단이 든 절과 제목 문단들. 목차와 같은 본문 제목 휴리스틱이다(documents.headings)."""
    by_page: dict[int, list] = {}
    for row in rows:
        by_page.setdefault(row["page_index"], []).append(row)
    pages = [
        {"page_index": index, "blocks": [{"text": row["text"], "regions": json.loads(row["regions_json"])} for row in page_rows]}
        for index, page_rows in sorted(by_page.items())
    ]
    paths = section_paths(pages)
    sections = {by_page[page][order]["block_id"]: path for (page, order), path in paths.items()}
    heading_ids = frozenset(by_page[item["page_index"]][item["order"]]["block_id"] for item in headings(pages))
    return sections, heading_ids
