"""주석을 넣은 PDF 내려받기 REST (2026-11-13 사용자 요청). 바탕으로 레이아웃 유지 번역본도 고른다(2026-11-15 사용자 요청)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from paperloom.api.docs import file_response
from paperloom.api.errors import NOT_FOUND_MESSAGE, ApiError
from paperloom.pdf_export.marks import PARTS, Part
from paperloom.pdf_export.service import PdfExportService, TranslatedBase
from paperloom.pdf_export.writer import ExportFailed
from paperloom.translation.models import Language


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
        base: Annotated[
            Literal["original", "translated"],
            Query(description="바탕. original: 원본 PDF, translated: 레이아웃 유지 번역본(번역한 쪽만 번역문으로 덮고 나머지 쪽은 원문)"),
        ] = "original",
        language: Annotated[Language, Query(description="translated일 때 번역 언어")] = "ko",
        scale: Annotated[float, Query(ge=0.6, le=1.3, description="translated일 때 번역 글꼴 배율(원문 글자 크기 기준)")] = 1.0,
    ) -> Response:
        """원문 쪽은 그대로 두고 하이라이트는 색칠(/Highlight), 메모·설명·질문은 그 위치의 메모 아이콘(/Text)으로 넣는다.
        Reader 사이드바의 Claude 대화와 선택 메뉴의 번역은 넣지 않는다.

        translated면 저장된 쪽 번역이 있는 쪽의 원문 문단을 흰 상자로 덮고 그 자리에 번역문을 쓴다(웹의 레이아웃 유지 번역과
        같은 조판). 하이라이트는 걸친 원문 문장의 번역문에 칠한다. 번역을 실행하지는 않는다."""
        translated = TranslatedBase(language, scale) if base == "translated" else None
        try:
            pdf = service.annotated_pdf(version_id, PARTS if include is None else include, translated)
        except ExportFailed as failed:
            if failed.code == "RESOURCE_LIMIT":
                raise ApiError(503, "RESOURCE_LIMIT", "주석을 넣은 PDF를 시간 안에 만들지 못했습니다.", retryable=True) from None
            raise ApiError(500, "EXPORT_FAILED", "주석을 넣은 PDF를 만들지 못했습니다.") from None
        if pdf is None:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
        return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="paperloom-{version_id[:8]}.pdf"'})

    return router
