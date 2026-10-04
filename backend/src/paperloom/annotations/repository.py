"""annotations SQL. 호출자가 트랜잭션 경계를 정한다. 모든 조회·변경은 소유자 범위 안에서 한다."""

import sqlite3

from paperloom.annotations.models import AnnotationOut
from paperloom.documents.repository import LOCAL_OWNER_ID
from paperloom.reading.repository import ANCHOR_COLUMNS, anchor_from_row

_SELECT = (
    "SELECT n.annotation_id, n.comment, n.color, n.revision, n.created_at AS annotation_created_at, n.updated_at, "
    + ", ".join(f"a.{column}" for column in ANCHOR_COLUMNS)
    + " FROM annotations AS n JOIN anchors AS a ON a.anchor_id = n.anchor_id WHERE n.owner_id = ?"
)


def insert_annotation(
    connection: sqlite3.Connection, *, annotation_id: str, anchor_id: str, comment: str, color: str | None, now: str
) -> None:
    connection.execute(
        "INSERT INTO annotations (annotation_id, owner_id, anchor_id, comment, color, revision, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
        (annotation_id, LOCAL_OWNER_ID, anchor_id, comment, color, now, now),
    )


def get_annotation(connection: sqlite3.Connection, annotation_id: str) -> AnnotationOut | None:
    row = connection.execute(_SELECT + " AND n.annotation_id = ?", (LOCAL_OWNER_ID, annotation_id)).fetchone()
    return _to_annotation(row) if row else None


def list_for_version(connection: sqlite3.Connection, version_id: str) -> list[AnnotationOut]:
    rows = connection.execute(_SELECT + " AND a.version_id = ?", (LOCAL_OWNER_ID, version_id)).fetchall()
    annotations = [_to_annotation(row) for row in rows]
    # 읽는 순서: 쪽, 첫 줄의 위(v), 왼쪽(u)
    return sorted(annotations, key=lambda n: (n.anchor.page_index, n.anchor.quads[0][1], n.anchor.quads[0][0]))


def update_annotation(
    connection: sqlite3.Connection, *, annotation_id: str, expected_revision: int, changes: dict[str, str | None], now: str
) -> bool:
    """기대한 revision일 때만 changes(comment·color)를 바꾸고 revision을 올린다. 바꿨으면 True."""
    columns = [column for column in ("comment", "color") if column in changes]
    assignments = "".join(f"{column} = ?, " for column in columns)
    cursor = connection.execute(
        f"UPDATE annotations SET {assignments}revision = revision + 1, updated_at = ?"
        " WHERE annotation_id = ? AND owner_id = ? AND revision = ?",
        (*(changes[column] for column in columns), now, annotation_id, LOCAL_OWNER_ID, expected_revision),
    )
    return cursor.rowcount == 1


def delete_annotation(connection: sqlite3.Connection, *, annotation_id: str, expected_revision: int) -> bool:
    cursor = connection.execute(
        "DELETE FROM annotations WHERE annotation_id = ? AND owner_id = ? AND revision = ?",
        (annotation_id, LOCAL_OWNER_ID, expected_revision),
    )
    return cursor.rowcount == 1


def _to_annotation(row: sqlite3.Row) -> AnnotationOut:
    return AnnotationOut(
        annotation_id=row["annotation_id"],
        anchor=anchor_from_row(row),
        comment=row["comment"],
        color=row["color"],
        revision=row["revision"],
        created_at=row["annotation_created_at"],
        updated_at=row["updated_at"],
    )
