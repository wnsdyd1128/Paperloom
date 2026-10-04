"""재전송해도 한 번만 처리하는 POST (IMPL §8). 클라이언트가 `Idempotency-Key` 헤더를 보낸다.

- 같은 범위(scope)·같은 키·같은 요청 본문이면 처음 응답(상태 코드와 본문)을 그대로 돌려준다.
- 같은 키에 다른 본문이면 `422 IDEMPOTENCY_KEY_REUSED`다.
- 처음 요청이 아직 처리 중이면 `409 IDEMPOTENCY_IN_PROGRESS`(retryable)다. 처리 중 표시가 STALE_SECONDS보다
  오래되면 그 프로세스가 멈춘 것으로 보고 다시 처리한다(그 사이 저장이 끝났다면 한 번 더 만들어질 수 있다).
- 처리가 오류로 끝나면 키를 지워 같은 키로 다시 시도할 수 있게 한다.
- 키는 RETENTION_SECONDS 동안 보관한다. 키가 없으면 그냥 처리한다.
"""

import hashlib
import json
import re
import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from paperloom.api.errors import ApiError
from paperloom.infrastructure.database.sqlite import connect

_KEY = re.compile(r"[\x21-\x7e]{1,200}")
RETENTION_SECONDS = 24 * 3600
STALE_SECONDS = 60


class IdempotencyStore:
    def __init__(self, db_path: Path, clock: Callable[[], float] = time.time) -> None:
        self._db_path = db_path
        self._clock = clock

    def respond(
        self, scope: str, key: str | None, request: BaseModel, create: Callable[[], BaseModel], status_code: int = 201
    ) -> JSONResponse:
        """create()의 결과를 status_code로 돌려준다. 키가 있으면 한 번만 만든다."""
        if key is None:
            return JSONResponse(jsonable_encoder(create()), status_code)
        if not _KEY.fullmatch(key):
            raise ApiError(422, "INVALID_REQUEST", "Idempotency-Key는 공백 없는 ASCII 1–200자여야 합니다.")
        digest = hashlib.sha256(json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
        stored = self._reserve(scope, key, digest)
        if stored is not None:
            return JSONResponse(json.loads(stored[1]), stored[0])
        try:
            body = jsonable_encoder(create())
        except BaseException:
            self._forget(scope, key)
            raise
        with closing(connect(self._db_path)) as connection, connection:
            connection.execute(
                "UPDATE idempotency_keys SET status_code = ?, response_json = ? WHERE scope = ? AND key = ?",
                (status_code, json.dumps(body), scope, key),
            )
        return JSONResponse(body, status_code)

    def _reserve(self, scope: str, key: str, digest: str) -> tuple[int, str] | None:
        """처음이면 처리 중으로 표시하고 None, 끝난 요청이면 (상태 코드, 응답)."""
        now = self._clock()
        with closing(connect(self._db_path)) as connection, connection:
            connection.execute("DELETE FROM idempotency_keys WHERE created_at < ?", (now - RETENTION_SECONDS,))
            row = connection.execute(
                "SELECT request_sha256, status_code, response_json, created_at FROM idempotency_keys WHERE scope = ? AND key = ?",
                (scope, key),
            ).fetchone()
            if row is None:
                try:
                    connection.execute(
                        "INSERT INTO idempotency_keys (scope, key, request_sha256, created_at) VALUES (?, ?, ?, ?)",
                        (scope, key, digest, now),
                    )
                except sqlite3.IntegrityError:  # 같은 키의 요청이 방금 먼저 들어왔다
                    raise _in_progress() from None
                return None
            if row["request_sha256"] != digest:
                raise ApiError(422, "IDEMPOTENCY_KEY_REUSED", "같은 Idempotency-Key를 다른 요청에 썼습니다.")
            if row["status_code"] is not None:
                return row["status_code"], row["response_json"]
            if row["created_at"] >= now - STALE_SECONDS:
                raise _in_progress()
            connection.execute("UPDATE idempotency_keys SET created_at = ? WHERE scope = ? AND key = ?", (now, scope, key))
            return None

    def _forget(self, scope: str, key: str) -> None:
        with closing(connect(self._db_path)) as connection, connection:
            connection.execute("DELETE FROM idempotency_keys WHERE scope = ? AND key = ?", (scope, key))


def _in_progress() -> ApiError:
    return ApiError(409, "IDEMPOTENCY_IN_PROGRESS", "같은 요청을 처리하고 있습니다. 잠시 뒤 다시 보내세요.", retryable=True)
