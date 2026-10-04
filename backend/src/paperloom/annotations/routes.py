"""주석 REST (IMPL §8): 만들기, 버전별 목록, revision을 확인하는 수정·삭제."""

from typing import Annotated

from fastapi import APIRouter, Header, Query, Response

from paperloom.annotations.models import AnnotationIn, AnnotationList, AnnotationOut, AnnotationPatch
from paperloom.annotations.service import AnnotationService, NotFound, RevisionConflict
from paperloom.api.errors import NOT_FOUND_MESSAGE, ApiError
from paperloom.api.idempotency import IdempotencyStore


def build_router(service: AnnotationService, keys: IdempotencyStore) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post("/annotations", status_code=201, response_model=AnnotationOut)
    def create_annotation(request: AnnotationIn, idempotency_key: Annotated[str | None, Header()] = None) -> Response:
        def create() -> AnnotationOut:
            try:
                return service.create(request)
            except NotFound:
                raise _not_found() from None

        return keys.respond("POST /api/v1/annotations", idempotency_key, request, create)

    @router.get("/versions/{version_id}/annotations")
    def list_annotations(version_id: str) -> AnnotationList:
        try:
            return AnnotationList(annotations=service.list_for_version(version_id))
        except NotFound:
            raise _not_found() from None

    @router.patch("/annotations/{annotation_id}")
    def update_annotation(annotation_id: str, patch: AnnotationPatch) -> AnnotationOut:
        try:
            return service.update(annotation_id, patch)
        except NotFound:
            raise _not_found() from None
        except RevisionConflict as conflict:
            raise _conflict(conflict) from None

    @router.delete("/annotations/{annotation_id}", status_code=204)
    def delete_annotation(annotation_id: str, revision: Annotated[int, Query(ge=1)]) -> Response:
        try:
            service.delete(annotation_id, revision)
        except NotFound:
            raise _not_found() from None
        except RevisionConflict as conflict:
            raise _conflict(conflict) from None
        return Response(status_code=204)

    return router


def _not_found() -> ApiError:
    return ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)


def _conflict(conflict: RevisionConflict) -> ApiError:
    return ApiError(
        409,
        "REVISION_CONFLICT",
        "주석이 그사이 바뀌었습니다. 최신 내용을 다시 불러온 뒤 시도하세요.",
        details={"current_revision": conflict.current_revision},
    )
