"""사용자 설정 읽기·바꾸기 (U6). 이 PC의 Core DB에 한 벌만 둔다(A2). 저장된 값이 지금 계약과 맞지 않으면(예전 판) 기본값이다."""

import json
from contextlib import closing
from pathlib import Path

from pydantic import ValidationError

from paperloom.documents.repository import LOCAL_OWNER_ID
from paperloom.infrastructure.clock import utc_now
from paperloom.infrastructure.database.sqlite import connect
from paperloom.preferences.models import DEFAULT_PREFERENCES, Preferences


class PreferenceService:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def get(self) -> Preferences:
        with closing(connect(self._db_path)) as connection:
            row = connection.execute("SELECT value_json FROM preferences WHERE owner_id = ?", (LOCAL_OWNER_ID,)).fetchone()
        if row is None:
            return DEFAULT_PREFERENCES
        try:
            return Preferences.model_validate(json.loads(row["value_json"]))
        except (ValidationError, ValueError):
            return DEFAULT_PREFERENCES

    def put(self, preferences: Preferences) -> Preferences:
        with closing(connect(self._db_path)) as connection, connection:
            connection.execute(
                "INSERT INTO preferences (owner_id, value_json, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT (owner_id) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at",
                (LOCAL_OWNER_ID, preferences.model_dump_json(), utc_now()),
            )
        return preferences
