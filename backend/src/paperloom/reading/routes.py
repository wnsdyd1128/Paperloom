"""원문 위치 REST (IMPL §8): 만들기, 조회, 영역 종류 바꾸기, 영역 이미지, 쪽의 그림 후보·영역 이미지, 번호 붙은 그림."""

import math
from typing import Annotated

from fastapi import APIRouter, Header, Query, Response

from paperloom.api.docs import IDEMPOTENCY_KEY, IDEMPOTENT, errors, file_response
from paperloom.api.errors import NOT_FOUND_MESSAGE, ApiError
from paperloom.api.idempotency import IdempotencyStore
from paperloom.reading.figures import FiguresFailed
from paperloom.reading.geometry import quad_shape_problem
from paperloom.reading.models import AnchorIn, AnchorKindPatch, AnchorList, AnchorOut, FigureList, FigureOut, NumberedFigureList, NumberedFigureOut
from paperloom.reading.region_image import RenderFailed
from paperloom.reading.service import AnchorService, InvalidAnchor, VersionNotFound

_IMAGE_DOCS = file_response("image/png", "영역 PNG", "NOT_FOUND", "RENDER_FAILED", "RESOURCE_LIMIT")


def build_router(service: AnchorService, keys: IdempotencyStore) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["위치"])

    @router.post("/anchors", status_code=201, response_model=AnchorOut, summary="위치 만들기", responses=errors("NOT_FOUND", "INVALID_ANCHOR", *IDEMPOTENT))
    def create_anchor(request: AnchorIn, idempotency_key: Annotated[str | None, Header(description=IDEMPOTENCY_KEY)] = None) -> Response:
        def create() -> AnchorOut:
            try:
                return service.create(request)
            except VersionNotFound:
                raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE) from None
            except InvalidAnchor as invalid:
                raise ApiError(422, "INVALID_ANCHOR", invalid.message, details=invalid.details) from None

        return keys.respond("POST /api/v1/anchors", idempotency_key, request, create)

    @router.get("/anchors/{anchor_id}", summary="위치 조회", responses=errors("NOT_FOUND"))
    def get_anchor(anchor_id: str) -> AnchorOut:
        anchor = service.get(anchor_id)
        if anchor is None:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
        return anchor

    @router.get("/versions/{version_id}/anchors", summary="판본의 위치 목록", responses=errors("NOT_FOUND"))
    def list_anchors(version_id: str) -> AnchorList:
        """버전의 모든 위치, 읽는 순서로 (Wiki로 내보내기에서 고른다). 주석은 /versions/{id}/annotations에 있다."""
        anchors = service.list_for_version(version_id)
        if anchors is None:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
        return AnchorList(anchors=anchors)

    @router.patch("/anchors/{anchor_id}", summary="영역 종류 바꾸기", responses=errors("NOT_FOUND", "INVALID_ANCHOR"))
    def change_kind(anchor_id: str, patch: AnchorKindPatch) -> AnchorOut:
        try:
            anchor = service.change_kind(anchor_id, patch.kind)
        except InvalidAnchor as invalid:
            raise ApiError(422, "INVALID_ANCHOR", invalid.message, details=invalid.details) from None
        if anchor is None:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
        return anchor

    @router.get("/anchors/{anchor_id}/image", summary="위치의 영역 이미지", response_class=Response, responses=_IMAGE_DOCS)
    def region_image(anchor_id: str, scale: Annotated[float, Query(ge=0.5, le=4)] = 2) -> Response:
        return _png_response(lambda: service.image(anchor_id, scale))

    @router.get("/versions/{version_id}/pages/{page_index}/image", summary="쪽의 영역 이미지", response_class=Response, responses=_IMAGE_DOCS)
    def page_region_image(
        version_id: str,
        page_index: int,
        box: Annotated[str, Query(description="정본 좌표 u0,v0,u1,v1 (쉼표로 구분)")],
        scale: Annotated[float, Query(ge=0.5, le=4)] = 2,
    ) -> Response:
        region = _parse_box(box)
        return _png_response(lambda: service.page_image(version_id, page_index, region, scale))

    @router.get("/versions/{version_id}/pages/{page_index}/figures", summary="쪽의 그림 후보", responses=errors("NOT_FOUND", "RESOURCE_LIMIT"))
    def page_figures(version_id: str, page_index: int) -> FigureList:
        try:
            figures = service.figures(version_id, page_index)
        except FiguresFailed:
            raise ApiError(503, "RESOURCE_LIMIT", "쪽의 그림을 시간 안에 찾지 못했습니다.", retryable=True) from None
        if figures is None:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
        return FigureList(figures=[FigureOut(box=list(figure.box), source=figure.source) for figure in figures])

    @router.get("/versions/{version_id}/figures", summary="판본의 번호 붙은 그림", responses=errors("NOT_FOUND"))
    def numbered_figures(version_id: str) -> NumberedFigureList:
        """캡션("Figure 3: …", "Fig. 2.", "그림 1." …)으로 찾은 그림, 문서 차례로. 본문 추출 전이면 빈 목록이다.
        대화 브리지가 Claude에게 알리고, 아티팩트가 그림 번호(paperloom-figure:3)로 원본 그림을 넣을 때 쓴다."""
        figures = service.numbered_figures(version_id)
        if figures is None:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
        return NumberedFigureList(
            version_id=version_id,
            figures=[NumberedFigureOut(label=figure.label, page_index=figure.page_index, caption=figure.caption) for figure in figures],
        )

    @router.get("/versions/{version_id}/figures/{label}/image", summary="번호 붙은 그림의 이미지", response_class=Response, responses=_IMAGE_DOCS)
    def numbered_figure_image(version_id: str, label: str, scale: Annotated[float, Query(ge=0.5, le=4)] = 2) -> Response:
        """캡션에 붙은 그림 영역(그림 후보와 축 이름 같은 그림의 글)의 PNG. 그 번호가 없거나 그림 영역을 찾지 못하면 404다."""
        try:
            return _png_response(lambda: service.numbered_figure_image(version_id, label, scale))
        except FiguresFailed:
            raise ApiError(503, "RESOURCE_LIMIT", "쪽의 그림을 시간 안에 찾지 못했습니다.", retryable=True) from None

    return router


def _parse_box(text: str) -> tuple[float, float, float, float]:
    """"u0,v0,u1,v1" → 상자. 네 개의 유한한 0~1 수이고 넓이가 있어야 한다."""
    try:
        values = [float(part) for part in text.split(",")]
    except ValueError:
        values = []
    if len(values) != 4 or not all(math.isfinite(value) and 0 <= value <= 1 for value in values):
        raise ApiError(422, "INVALID_REQUEST", "box는 0~1 사이의 수 네 개(u0,v0,u1,v1)여야 합니다.")
    u0, v0, u1, v1 = values
    if u0 >= u1 or v0 >= v1 or quad_shape_problem([u0, v0, u1, v0, u1, v1, u0, v1]):
        raise ApiError(422, "INVALID_REQUEST", "box는 넓이가 있는 사각형(u0 < u1, v0 < v1)이어야 합니다.")
    return u0, v0, u1, v1


def _png_response(render) -> Response:
    try:
        png = render()
    except RenderFailed as failed:
        if failed.code == "RESOURCE_LIMIT":
            raise ApiError(503, "RESOURCE_LIMIT", "영역 이미지를 시간 안에 그리지 못했습니다.", retryable=True) from None
        raise ApiError(500, "RENDER_FAILED", "영역 이미지를 그리지 못했습니다.") from None
    if png is None:
        raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
    # SourceVersion과 Anchor 위치는 바뀌지 않으므로 같은 주소의 이미지도 같다.
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})
