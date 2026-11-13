"""API 문서 (/docs, /openapi.json): 태그, 오류 응답, Swagger 화면.

FastAPI 기본 화면은 CDN에서 파일을 받아, 문서를 열 때마다 외부로 요청이 나가고 오프라인에서는 빈 화면이 된다.
그래서 웹 빌드에 넣은 파일을 쓰고(apps/web/vite.config.ts), 같은 이유로 /redoc은 끈다.
"""

from typing import Any, Literal

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

DESCRIPTION = """\
Paperloom 웹이 쓰는 로컬 REST API다. 인증이 없으므로 이 PC(loopback) 안에서만 연다.

- **Try it out은 실제 서재를 바꾼다.** 지우기는 되돌릴 수 없다.
- **모델:** 이 API는 모델을 부르지 않는다. 대화·번역은 Claude Code 브리지가 맡고, 결과만 이 API로 저장한다.
- **쪽 번호:** `page_index`는 0부터 센다.
- **오류:** 모든 오류는 `ErrorBody` 형식이다. 프로그램은 `code`로 구분하고, `retryable`이 참이면 같은 요청을 다시 보내도 된다.
- **재전송 방지:** `Idempotency-Key`를 보내면 같은 키·같은 본문의 재전송에 처음 응답을 돌려준다.
"""

TAGS = [
    {"name": "서재", "description": "논문 등록·목록·지우기, 논문 정보, 태그"},
    {"name": "판본", "description": "논문의 PDF 판본: 원본, 주석을 넣은 PDF, 쪽별 본문, 목차, 본문 다시 추출"},
    {"name": "위치", "description": "원문 위치(Anchor)와 영역 이미지, 쪽의 그림 후보"},
    {"name": "주석", "description": "위치에 붙인 메모. 고치거나 지울 때 revision을 확인한다"},
    {"name": "문맥", "description": "모델에게 줄 문맥(Context Packet) 만들기와 내보내기"},
    {"name": "답변", "description": "Claude Code 대화 답변의 목록·저장·버리기"},
    {"name": "대화", "description": "선택 설명·질문 대화와 대화 이름·갈래"},
    {"name": "번역", "description": "쪽 번역. 저장은 Claude Code 브리지가 번역을 검사한 뒤 부른다"},
    {"name": "Wiki로 내보내기", "description": "LLM Wiki가 읽을 Evidence Bundle을 outbox에 쓴다. LLM Wiki는 이 API를 부르지 않고 파일만 읽는다"},
    {"name": "아티팩트", "description": "대화 답에서 Claude가 만든 아티팩트(답 Markdown의 `artifact` 울타리 코드 블록)의 논문별 목록과, 아티팩트를 이 PC에서 여는 링크. 아티팩트는 답과 함께 저장된다. 링크의 페이지 `/artifacts/<id>`는 새 탭에서 여는 화면이라 이 문서에 없다"},
    {"name": "검색", "description": "논문 제목 검색"},
    {"name": "설정", "description": "사용자 설정"},
    {"name": "상태", "description": "서버 상태"},
]

IDEMPOTENCY_KEY = "재전송 방지 키. 공백 없는 ASCII 1–200자"

# 코드 → (상태, 뜻). `@` 뒤는 같은 코드가 다른 상태로도 쓰일 때 구분하는 표시이고 문서에는 보이지 않는다.
_ERRORS = {
    "ARTIFACT_WRITE_FAILED": (500, "아티팩트 파일을 쓰지 못했다. 남은 파일은 없다"),
    "BUNDLE_TOO_LARGE": (413, "내보낼 내용이 한도(파일 64개·합계 32 MiB·파일당 8 MiB)를 넘는다. `details`에 넘은 한도가 있다"),
    "BUNDLE_WRITE_FAILED": (500, "bundle을 쓰다 실패했다. 남은 파일은 없다"),
    "DUPLICATE_SOURCE": (409, "같은 내용의 PDF가 이미 있다. `details.paper_id`가 그 논문이다"),
    "EXPORT_FAILED": (500, "주석을 넣은 PDF를 만들지 못했다"),
    "IDEMPOTENCY_IN_PROGRESS": (409, "같은 키의 요청을 처리하고 있다"),
    "IDEMPOTENCY_KEY_REUSED": (422, "같은 키를 다른 요청에 썼다"),
    "INVALID_ANCHOR": (422, "위치의 좌표·쪽·종류가 맞지 않는다. `details.field`가 그 칸이다"),
    "INVALID_BUNDLE": (422, "내보낼 수 없는 선택이다. `details.errors`에 이유가 있다"),
    "INVALID_PACKET": (422, "문맥의 재료를 찾을 수 없다. `details.field`가 그 칸이다"),
    "INVALID_QUERY": (422, "검색어에 글자나 숫자가 없다"),
    "INVALID_REQUEST": (422, "요청 형식이 계약과 맞지 않는다. `details.errors`에 위치와 이유가 있다"),
    "INVALID_TRANSITION": (409, "지금 상태의 문맥에는 할 수 없다. `details.status`가 그 상태다"),
    "INVALID_TRANSLATION": (422, "원문 문장과 번역이 맞지 않는다. `details`에 그 문장이 있다"),
    "MALFORMED_PDF": (422, "PDF를 열 수 없다"),
    "NOT_FOUND": (404, "대상이 없다"),
    "NOT_PDF": (422, "PDF 파일이 아니다"),
    "NOT_TRANSLATED": (404, "이 쪽은 아직 번역하지 않았다"),
    "OUTBOX_UNAVAILABLE": (503, "outbox 폴더를 쓸 수 없다. 설정은 `/api/v1/health`의 `wiki_outbox`로 본다"),
    "PARSE_IN_PROGRESS": (409, "본문 추출이 이미 대기 중이거나 진행 중이다"),
    "PARSER_ERROR": (422, "PDF를 검사하다 오류가 났다"),
    "PASSWORD_REQUIRED": (422, "암호가 걸린 PDF다"),
    "RENDER_FAILED": (500, "영역 이미지를 그리지 못했다"),
    "RESOURCE_LIMIT": (503, "시간 안에 끝내지 못했다"),
    "RESOURCE_LIMIT@upload": (422, "PDF가 쪽수나 검사 시간 한도를 넘었다"),
    "REVISION_CONFLICT": (409, "그사이 바뀌었다. `details.current_revision`이 지금 값이다"),
    "TEXT_EXTRACTION_RUNNING": (409, "본문을 추출하는 중이라 지울 수 없다"),
    "TEXT_NOT_READY": (409, "본문 추출이 아직 끝나지 않았다"),
    "TOO_LARGE": (413, "파일이 업로드 한도를 넘는다"),
    "TOO_LARGE@artifact": (413, "페이지 문서가 한도(UTF-8로 8 MiB)를 넘는다. `details.max_bytes`가 한도다"),
    "UNKNOWN_SESSION": (409, "이 논문에 대해 저장된 대화가 아니다"),
    "UNSUPPORTED_MEDIA_TYPE": (415, "본문이 `application/pdf`가 아니다"),
}

IDEMPOTENT = ("IDEMPOTENCY_IN_PROGRESS", "IDEMPOTENCY_KEY_REUSED")


class ErrorBody(BaseModel):
    """모든 오류 응답의 형식 (api/errors.py)."""

    code: str = Field(description="오류 종류. 프로그램은 이 값으로 구분한다")
    message: str = Field(description="사람이 읽는 설명")
    request_id: str
    retryable: bool = Field(description="같은 요청을 다시 보내도 되는지")
    details: dict[str, Any] | None = Field(default=None, description="오류별 추가 정보. 없으면 이 칸이 빠진다")


class ModelStatus(BaseModel):
    name: str
    device: str | None = Field(description="연 뒤의 실제 장치(cuda·cpu). 아직 열지 않았으면 null")


class OutboxStatus(BaseModel):
    status: Literal["ready", "not_configured", "unwritable"]
    path: str | None


class Health(BaseModel):
    """서버 상태. 문서에만 쓰고, 응답은 bootstrap/app.py가 만든다."""

    status: Literal["ok", "degraded"]
    version: str
    mode: str
    cost_policy: str
    data_dir_writable: bool
    claude_code_url: str | None
    layout_model: ModelStatus | None
    ocr_model: ModelStatus | None
    wiki_outbox: OutboxStatus = Field(description="Wiki로 내보낼 폴더. 준비되지 않아도 내보내기만 막힌다")


def errors(*codes: str) -> dict[int | str, dict[str, Any]]:
    """라우트의 `responses=`에 넘길 오류 설명. 같은 상태의 코드는 한 응답에 모은다."""
    lines: dict[int, list[str]] = {}
    for code in codes:
        status, meaning = _ERRORS[code]
        lines.setdefault(status, []).append(f"- `{code.split('@')[0]}`: {meaning}")
    # 직접 422를 적으면 FastAPI가 형식 오류를 더하지 않으므로 함께 적는다
    if 422 in lines:
        lines[422].insert(0, f"- `INVALID_REQUEST`: {_ERRORS['INVALID_REQUEST'][1]}")
    return {status: {"model": ErrorBody, "description": "\n".join(found)} for status, found in lines.items()}


def file_response(media_type: str, description: str, *codes: str) -> dict[int | str, dict[str, Any]]:
    """JSON이 아닌 200 응답. 라우트에 `response_class=Response`도 줘야 JSON 형식이 함께 적히지 않는다."""
    body = {"description": description, "content": {media_type: {"schema": {"type": "string", "format": "binary"}}}}
    return {200: body, **errors(*codes)}


def install_openapi(app: FastAPI) -> None:
    """/openapi.json의 프레임워크 기본 문구를 실제 응답에 맞춘다."""
    generate = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = _match_real_responses(generate())
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]


def _match_real_responses(schema: dict[str, Any]) -> dict[str, Any]:
    # 형식 오류도 ErrorBody로 나간다(install_error_handler). FastAPI 기본 설명은 다른 형식을 적는다.
    invalid_request = {
        "description": f"- `INVALID_REQUEST`: {_ERRORS['INVALID_REQUEST'][1]}",
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorBody"}}},
    }
    for operations in schema["paths"].values():
        for operation in operations.values():
            responses = operation["responses"]
            for response in responses.values():
                if response["description"] == "Successful Response":
                    response["description"] = "성공"
            if responses.get("422", {}).get("description") == "Validation Error":
                responses["422"] = invalid_request
    schema["components"]["schemas"].pop("HTTPValidationError", None)
    schema["components"]["schemas"].pop("ValidationError", None)
    return schema


def install_swagger_ui(app: FastAPI) -> None:
    """/docs. 화면 파일이 웹 빌드에 있으므로 웹 빌드가 있을 때만, 정적 파일 mount보다 먼저 부른다."""

    @app.get("/docs", include_in_schema=False)
    def swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url="/openapi.json",
            title="Paperloom API",
            swagger_js_url="/swagger/swagger-ui-bundle.js",
            swagger_css_url="/swagger/swagger-ui.css",
            swagger_favicon_url="/favicon.svg",
        )
