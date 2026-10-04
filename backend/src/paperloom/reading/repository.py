"""anchors SQL. 호출자가 트랜잭션 경계를 정한다."""

import json
import sqlite3

from paperloom.reading.models import AnchorOut

ANCHOR_COLUMNS = (
    "anchor_id",
    "version_id",
    "page_index",
    "quads_json",
    "quote",
    "display_quote",
    "prefix",
    "suffix",
    "schema_version",
    "created_at",
    "kind",
)
_COLUMN_LIST = ", ".join(ANCHOR_COLUMNS)


def insert_anchor(connection: sqlite3.Connection, anchor: AnchorOut) -> None:
    connection.execute(
        f"INSERT INTO anchors ({_COLUMN_LIST}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            anchor.anchor_id,
            anchor.version_id,
            anchor.page_index,
            json.dumps(anchor.quads),
            anchor.quote,
            anchor.display_quote,
            anchor.prefix,
            anchor.suffix,
            anchor.schema_version,
            anchor.created_at,
            anchor.kind,
        ),
    )


def update_kind(connection: sqlite3.Connection, anchor_id: str, kind: str) -> None:
    connection.execute("UPDATE anchors SET kind = ? WHERE anchor_id = ?", (kind, anchor_id))


def get_anchor(connection: sqlite3.Connection, anchor_id: str) -> AnchorOut | None:
    row = connection.execute(f"SELECT {_COLUMN_LIST} FROM anchors WHERE anchor_id = ?", (anchor_id,)).fetchone()
    return anchor_from_row(row) if row else None


def anchor_from_row(row: sqlite3.Row) -> AnchorOut:
    """anchors 열을 담은 행(다른 표와 JOIN한 행 포함)을 응답 모델로 바꾼다."""
    return AnchorOut(
        anchor_id=row["anchor_id"],
        version_id=row["version_id"],
        page_index=row["page_index"],
        quads=json.loads(row["quads_json"]),
        quote=row["quote"],
        display_quote=row["display_quote"],
        prefix=row["prefix"],
        suffix=row["suffix"],
        schema_version=row["schema_version"],
        created_at=row["created_at"],
        kind=row["kind"],
    )
