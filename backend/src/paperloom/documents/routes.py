"""Library REST (IMPL §8): 업로드·목록·조회·원본 PDF·쪽별 본문 추출."""

from urllib.parse import unquote

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response

from paperloom.api.errors import NOT_FOUND_MESSAGE, ApiError
from paperloom.documents.models import (
    HeadingList,
    PageList,
    PageTextOut,
    PaperList,
    PaperMetadataIn,
    PaperOut,
    PaperTagsIn,
    ParseRunOut,
    TagRenameIn,
    VersionOut,
)
from paperloom.documents.parsing import ParseInProgress, ParseService
from paperloom.documents.service import DocumentService, DuplicateSource, TextNotReady, UploadRejected
from paperloom.infrastructure.files.source_store import UploadTooLarge

_REJECTION_MESSAGES = {
    "NOT_PDF": "PDF 파일이 아닙니다.",
    "MALFORMED_PDF": "PDF를 열 수 없습니다. 파일이 손상되었을 수 있습니다.",
    "PASSWORD_REQUIRED": "암호가 걸린 PDF는 등록할 수 없습니다.",
    "RESOURCE_LIMIT": "PDF가 처리 한도(쪽수 또는 검사 시간)를 넘었습니다.",
    "PARSER_ERROR": "PDF 검사 중 오류가 발생했습니다.",
}


def build_router(service: DocumentService, parsing: ParseService) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post("/papers", status_code=201)
    async def upload_paper(request: Request) -> PaperOut:
        media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if media_type != "application/pdf":
            raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "본문은 application/pdf여야 합니다.")
        max_bytes = service.limits.max_bytes
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > max_bytes:
            raise _too_large(max_bytes)
        # 파일명은 제목 후보로만 쓴다. 비ASCII를 위해 클라이언트가 percent-encoding한다.
        filename = unquote(request.headers.get("x-paperloom-filename", ""))
        try:
            received = await service.store.receive(request.stream(), max_bytes)
        except UploadTooLarge:
            raise _too_large(max_bytes) from None
        try:
            return await run_in_threadpool(service.register, received, filename)
        except UploadRejected as rejected:
            raise ApiError(422, rejected.code, _REJECTION_MESSAGES[rejected.code]) from None
        except DuplicateSource as duplicate:
            raise ApiError(
                409,
                "DUPLICATE_SOURCE",
                "같은 내용의 PDF가 이미 등록되어 있습니다.",
                details={"paper_id": duplicate.paper_id},
            ) from None

    @router.get("/papers")
    def list_papers() -> PaperList:
        return PaperList(papers=service.list_papers())

    @router.get("/papers/{paper_id}")
    def get_paper(paper_id: str) -> PaperOut:
        paper = service.get_paper(paper_id)
        if paper is None:
            raise _not_found()
        return paper

    @router.put("/papers/{paper_id}/metadata")
    def update_metadata(paper_id: str, metadata: PaperMetadataIn) -> PaperOut:
        """논문 정보 창에서 고친 제목·저자·연도·DOI (U4, 사용자 결정 D5). 네 값을 모두 받아 바꾼다."""
        paper = service.update_metadata(paper_id, metadata)
        if paper is None:
            raise _not_found()
        return paper

    @router.put("/papers/{paper_id}/tags")
    def set_tags(paper_id: str, request: PaperTagsIn) -> PaperOut:
        """서재 표의 태그 (U6). 이 목록으로 바꾼다."""
        paper = service.set_tags(paper_id, request)
        if paper is None:
            raise _not_found()
        return paper

    # 태그 이름은 /를 담을 수 있다(path). 대소문자는 가리지 않는다
    @router.patch("/tags/{name:path}", status_code=204)
    def rename_tag(name: str, request: TagRenameIn) -> Response:
        """서재 태그 메뉴의 이름 바꾸기 (2026-10-04 사용자 요청). 그 태그가 붙은 모든 논문에서 바뀐다."""
        if not service.rename_tag(name, request):
            raise _not_found()
        return Response(status_code=204)

    @router.delete("/tags/{name:path}", status_code=204)
    def delete_tag(name: str) -> Response:
        """서재 태그 메뉴의 지우기 (2026-10-04 사용자 요청). 모든 논문에서 뗀다(논문은 그대로)."""
        if not service.delete_tag(name):
            raise _not_found()
        return Response(status_code=204)

    @router.post("/papers/{paper_id}/opened", status_code=204)
    def mark_opened(paper_id: str) -> Response:
        """Reader로 열었다 (U6 서재의 마지막 열람·차례)."""
        if not service.mark_opened(paper_id):
            raise _not_found()
        return Response(status_code=204)

    @router.get("/versions/{version_id}")
    def get_version(version_id: str) -> VersionOut:
        version = service.get_version(version_id)
        if version is None:
            raise _not_found()
        return version

    @router.get("/versions/{version_id}/pdf")
    def get_source_pdf(version_id: str) -> FileResponse:
        # 경로는 DB의 storage_ref로만 만든다. 요청 값은 조회 키로만 쓴다.
        path = service.source_path(version_id)
        if path is None:
            raise _not_found()
        return FileResponse(path, media_type="application/pdf")  # Range 요청 지원

    @router.get("/versions/{version_id}/pages")
    def list_pages(version_id: str) -> PageList:
        pages = service.pages(version_id)
        if pages is None:
            raise _not_found()
        return pages

    @router.get("/versions/{version_id}/pages/{page_index}")
    def get_page(version_id: str, page_index: int) -> PageTextOut:
        version = service.get_version(version_id)
        if version is None or not 0 <= page_index < version.page_count:
            raise _not_found()
        page = service.page_text(version_id, page_index)
        if page is None:
            raise ApiError(409, "TEXT_NOT_READY", "이 버전의 본문 추출이 아직 끝나지 않았습니다.", retryable=True)
        return page

    @router.get("/versions/{version_id}/headings")
    def get_headings(version_id: str) -> HeadingList:
        """본문 제목으로 만든 목차 (U4, 사용자 결정 D6). PDF 목차(outline)가 없을 때 목차 패널이 쓴다."""
        try:
            found = service.headings(version_id)
        except TextNotReady:
            raise ApiError(409, "TEXT_NOT_READY", "이 버전의 본문 추출이 아직 끝나지 않았습니다.", retryable=True) from None
        if found is None:
            raise _not_found()
        return found

    @router.post("/versions/{version_id}/parse-runs", status_code=202)
    def request_parse(version_id: str) -> ParseRunOut:
        """본문을 다시 추출한다(실패·일부 추출 뒤 사용자 재시도). 결과는 버전 상태로 확인한다."""
        try:
            run_id = parsing.request(version_id)
        except ParseInProgress:
            raise ApiError(409, "PARSE_IN_PROGRESS", "이 버전의 본문 추출이 이미 대기 중이거나 진행 중입니다.") from None
        if run_id is None:
            raise _not_found()
        return ParseRunOut(parse_run_id=run_id, version_id=version_id, status="QUEUED")

    return router


def _too_large(max_bytes: int) -> ApiError:
    return ApiError(413, "TOO_LARGE", f"파일이 너무 큽니다 (최대 {max_bytes // (1024 * 1024)} MiB).")


def _not_found() -> ApiError:
    return ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
