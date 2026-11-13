"""주석을 넣은 PDF 내려받기 REST (2026-11-13 사용자 요청)."""

from typing import Annotated

from fastapi import APIRouter, Query, Response

from paperloom.api.docs import file_response
from paperloom.api.errors import NOT_FOUND_MESSAGE, ApiError
from paperloom.pdf_export.marks import PARTS, Part
from paperloom.pdf_export.service import PdfExportService
from paperloom.pdf_export.writer import ExportFailed


def build_router(service: PdfExportService) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["판본"])

    @router.get(
        "/versions/{version_id}/annotated-pdf",
        summary="주석을 넣은 PDF",
        response_class=Response,
        responses=file_response("application/pdf", "원본 PDF 뒤에 고른 표시를 PDF 표준 주석으로 덧붙인 파일", "NOT_FOUND", "EXPORT_FAILED", "RESOURCE_LIMIT"),
    )
    def annotated_pdf(
        version_id: str,
        include: Annotated[
            list[Part] | None,
            Query(description="넣을 것(여러 번 쓴다). highlights: 하이라이트, notes: 주석의 메모, explanations: 설명, questions: AI 질문. 없으면 모두"),
        ] = None,
    ) -> Response:
        """원문 쪽은 그대로 두고 하이라이트는 색칠(/Highlight), 메모·설명·질문은 그 위치의 메모 아이콘(/Text)으로 넣는다.
        Reader 사이드바의 Claude 대화와 번역은 넣지 않는다."""
        try:
            pdf = service.annotated_pdf(version_id, PARTS if include is None else include)
        except ExportFailed as failed:
            if failed.code == "RESOURCE_LIMIT":
                raise ApiError(503, "RESOURCE_LIMIT", "주석을 넣은 PDF를 시간 안에 만들지 못했습니다.", retryable=True) from None
            raise ApiError(500, "EXPORT_FAILED", "주석을 넣은 PDF를 만들지 못했습니다.") from None
        if pdf is None:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
        return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="paperloom-{version_id[:8]}.pdf"'})

    return router
