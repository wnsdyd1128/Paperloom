"""REST 오류 봉투 (IMPL §8): `code`, `message`, `request_id`, `retryable`, 필요할 때 `details`.

라우트가 없는 경로 등 프레임워크가 내는 HTTP 오류와 요청 본문 검증 오류(422)도 같은 형식으로 바꾼다.
"""

import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

NOT_FOUND_MESSAGE = "요청한 자료가 없거나 접근할 수 없습니다."


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details


def install_error_handler(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, error: ApiError) -> JSONResponse:
        return _envelope(error.status, error.code, error.message, error.retryable, error.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        # 보낸 값(input)은 되돌려 주지 않는다. 위치와 이유만 알린다.
        problems = [{"loc": list(e["loc"]), "type": e["type"], "message": e["msg"]} for e in error.errors()]
        return _envelope(422, "INVALID_REQUEST", "요청 형식이 계약과 맞지 않습니다.", details={"errors": problems})

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_: Request, error: StarletteHTTPException) -> JSONResponse:
        if error.status_code == 404:
            return _envelope(404, "NOT_FOUND", NOT_FOUND_MESSAGE)
        return _envelope(error.status_code, f"HTTP_{error.status_code}", str(error.detail), headers=error.headers)


def _envelope(
    status: int,
    code: str,
    message: str,
    retryable: bool = False,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message, "request_id": uuid.uuid4().hex, "retryable": retryable}
    if details:
        body["details"] = details
    return JSONResponse(body, status_code=status, headers=headers)
