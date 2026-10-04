"""저장 시각 표기. documents의 created_at과 같은 형식(ISO 8601 UTC, `Z` 접미사)이다."""

from datetime import UTC, datetime


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
