"""아티팩트 링크 (store.py): 웹이 만든 격리 문서를 파일로 쓰고, 그 페이지를 격리해서 준다. 모델을 부르지 않는다.

부르는 쪽은 Paperloom 웹뿐이다. 페이지(`/artifacts/<id>`)는 사용자가 새 탭에서 여는 화면이라 API 문서에 넣지 않는다.
"""

import logging

from fastapi import APIRouter, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from paperloom.api.docs import errors
from paperloom.api.errors import NOT_FOUND_MESSAGE, ApiError
from paperloom.artifacts.store import ArtifactStore

log = logging.getLogger("paperloom")

MAX_BYTES = 8 * 1024 * 1024

# 페이지는 sandbox(allow-scripts만)라 출처 없는 문서로 돈다: Paperloom과 같은 주소에서 열려도 API 응답·저장소·쿠키를 읽지 못하고
# 창을 띄우거나 양식을 보내지 못한다. 나머지는 웹의 격리 창과 같다(apps/web/src/features/artifacts/frameDocument.ts의
# FRAME_CSP): 바깥 주소에서 아무것도 불러오지 못한다. sandbox는 meta로 걸 수 없어 응답 머리로 건다.
PAGE_HEADERS = {
    "Content-Security-Policy": "; ".join(
        (
            "sandbox allow-scripts",
            "default-src 'none'",
            "script-src 'unsafe-inline'",
            "style-src 'unsafe-inline'",
            "img-src data: blob:",
            "font-src data:",
            "media-src data: blob:",
            "form-action 'none'",
            "base-uri 'none'",
        )
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


class ArtifactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    html: str = Field(min_length=1, description="페이지 문서 전체. 웹이 아티팩트로 만든 격리 문서다(UTF-8로 8 MiB까지)")


class ArtifactLink(BaseModel):
    artifact_id: str = Field(description="내용의 sha256 앞 32자. 같은 내용은 같은 id다")
    url: str = Field(description="이 서버에서 페이지를 여는 경로")
    path: str = Field(description="저장한 파일. 사용자 폴더는 ~로 쓰고, Docker면 설정 `artifacts.shown_dir` 기준이다")


def build_router(store: ArtifactStore) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/api/v1/artifacts",
        tags=["아티팩트"],
        status_code=201,
        summary="아티팩트 링크 만들기",
        responses={200: {"model": ArtifactLink, "description": "같은 내용의 파일이 이미 있다"}, **errors("TOO_LARGE@artifact", "ARTIFACT_WRITE_FAILED")},
    )
    def create_artifact(body: ArtifactRequest, response: Response) -> ArtifactLink:
        """새로 쓰면 201, 같은 내용이 이미 있으면 그 파일의 링크를 200으로 준다."""
        if len(body.html.encode("utf-8")) > MAX_BYTES:
            raise ApiError(413, "TOO_LARGE", "아티팩트가 한도(8 MiB)를 넘어 링크를 만들 수 없습니다.", details={"max_bytes": MAX_BYTES})
        try:
            artifact_id, created = store.save(body.html)
        except OSError:
            log.exception("아티팩트 파일을 쓰지 못했습니다.")
            raise ApiError(500, "ARTIFACT_WRITE_FAILED", "아티팩트 파일을 쓰지 못했습니다. 폴더 권한·디스크 공간을 확인하세요.", retryable=True) from None
        if not created:
            response.status_code = 200
        return ArtifactLink(artifact_id=artifact_id, url=f"/artifacts/{artifact_id}", path=store.shown_path(artifact_id))

    @router.get("/artifacts/{artifact_id}", include_in_schema=False)
    def artifact_page(artifact_id: str) -> FileResponse:
        path = store.file(artifact_id)
        if path is None:
            raise ApiError(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
        return FileResponse(path, media_type="text/html; charset=utf-8", headers=PAGE_HEADERS)

    return router
