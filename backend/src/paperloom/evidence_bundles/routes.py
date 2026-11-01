"""Wiki로 내보내기 REST (03-api-spec §3): 미리보기, 생성(재전송 방지 키 필수), 기록 목록·상세. 모델을 호출하지 않는다.

부르는 쪽은 Paperloom 웹뿐이다. LLM Wiki는 이 API를 부르지 않고 outbox의 파일만 읽는다.
"""

from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, Response

from paperloom.api.docs import IDEMPOTENCY_KEY, IDEMPOTENT, errors
from paperloom.api.errors import NOT_FOUND_MESSAGE, ApiError
from paperloom.api.idempotency import IdempotencyStore
from paperloom.evidence_bundles.models import DEFAULT_LIST, MAX_LIST, BundleDetail, BundleList, BundleOut, BundlePreview, BundleRequest
from paperloom.evidence_bundles.selection import BundleRefused
from paperloom.evidence_bundles.service import EvidenceBundleService

# 코드 → (상태, 문구, 다시 시도할 수 있는지)
_REFUSALS = {
    "NOT_FOUND": (404, NOT_FOUND_MESSAGE, False),
    "TEXT_NOT_READY": (409, "고른 쪽의 본문을 아직 추출하지 않았습니다.", True),
    "BUNDLE_TOO_LARGE": (413, "내보낼 내용이 한도(파일 64개·합계 32 MiB·파일당 8 MiB)를 넘습니다.", False),
    "INVALID_BUNDLE": (422, "내보낼 수 없는 선택입니다.", False),
    "OUTBOX_UNAVAILABLE": (503, "Wiki로 보낼 폴더를 쓸 수 없습니다.", True),
    "BUNDLE_WRITE_FAILED": (500, "bundle을 쓰다 실패했습니다. 남은 파일은 없습니다.", True),
}


def build_router(service: EvidenceBundleService, keys: IdempotencyStore) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["Wiki로 내보내기"])

    @router.post("/evidence-bundles/preview", summary="내보내기 미리보기", responses=errors("NOT_FOUND", "INVALID_BUNDLE", "OUTBOX_UNAVAILABLE"))
    def preview_bundle(body: BundleRequest, request: Request) -> BundlePreview:
        try:
            return service.preview(body, str(request.base_url))
        except BundleRefused as refused:
            raise _api_error(refused) from None

    @router.post(
        "/evidence-bundles",
        status_code=201,
        response_model=BundleOut,
        summary="bundle 만들기",
        responses={
            200: {"model": BundleOut, "description": "같은 키·같은 본문의 재전송"},
            **errors("NOT_FOUND", "TEXT_NOT_READY", "BUNDLE_TOO_LARGE", "INVALID_BUNDLE", "BUNDLE_WRITE_FAILED", "OUTBOX_UNAVAILABLE", *IDEMPOTENT),
        },
    )
    def create_bundle(body: BundleRequest, request: Request, idempotency_key: Annotated[str, Header(description=IDEMPOTENCY_KEY)]) -> Response:
        """새로 쓰면 201, 같은 키·같은 본문을 다시 보내면 처음 응답을 200으로 준다."""

        def create() -> BundleOut:
            try:
                return service.create(body, str(request.base_url))
            except BundleRefused as refused:
                raise _api_error(refused) from None

        return keys.respond("POST /api/v1/evidence-bundles", idempotency_key, body, create, replay_status=200)

    @router.get("/evidence-bundles", summary="내보낸 기록")
    def list_bundles(limit: Annotated[int, Query(ge=1, le=MAX_LIST)] = DEFAULT_LIST) -> BundleList:
        return BundleList(bundles=service.list(limit))

    @router.get("/evidence-bundles/{bundle_id}", summary="내보낸 기록 상세", responses=errors("NOT_FOUND"))
    def get_bundle(bundle_id: str) -> BundleDetail:
        bundle = service.get(bundle_id)
        if bundle is None:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE, details={"field": "bundle_id"})
        return bundle

    return router


def _api_error(refused: BundleRefused) -> ApiError:
    status, message, retryable = _REFUSALS[refused.code]
    return ApiError(status, refused.code, message, retryable=retryable, details=refused.details)
