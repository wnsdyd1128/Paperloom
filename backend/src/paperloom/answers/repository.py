"""answers SQL. 호출자가 트랜잭션 경계를 정한다."""

import sqlite3
from collections.abc import Sequence

from paperloom.documents.repository import LOCAL_OWNER_ID

_ANSWERS = (
    "SELECT a.*, c.name AS connection_name, p.content_json,"
    " (SELECT COUNT(*) FROM answer_images AS i WHERE i.answer_id = a.answer_id) AS image_count FROM answers AS a"
    " JOIN context_packets AS p ON p.packet_id = a.packet_id"
    " LEFT JOIN host_connections AS c ON c.connection_id = a.connection_id"
)


def insert_answer(
    connection: sqlite3.Connection,
    answer_id: str,
    packet_id: str,
    connection_id: str | None,
    origin: str,
    prompt: str | None,
    chat_session: str | None,
    markdown: str,
    content_sha256: str,
    citations_json: str,
    created_at: str,
    context: tuple[int | None, int | None] = (None, None),
    message_id: str | None = None,
) -> None:
    connection.execute(
        "INSERT INTO answers (answer_id, owner_id, packet_id, connection_id, origin, prompt, chat_session, markdown,"
        " content_sha256, citations_json, review_status, created_at, context_tokens, context_window, cc_message_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unreviewed', ?, ?, ?, ?)",
        (
            answer_id, LOCAL_OWNER_ID, packet_id, connection_id, origin, prompt, chat_session, markdown, content_sha256, citations_json,
            created_at, *context, message_id,
        ),
    )


def insert_images(connection: sqlite3.Connection, answer_id: str, images: Sequence[tuple[str, bytes]]) -> None:
    """답의 질문에 붙인 (media_type, 이미지), 붙인 차례대로."""
    connection.executemany(
        "INSERT INTO answer_images (answer_id, position, media_type, data) VALUES (?, ?, ?, ?)",
        [(answer_id, position, media_type, data) for position, (media_type, data) in enumerate(images)],
    )


def get_image(connection: sqlite3.Connection, answer_id: str, position: int) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT i.media_type, i.data FROM answer_images AS i JOIN answers AS a ON a.answer_id = i.answer_id"
        " WHERE i.answer_id = ? AND i.position = ? AND a.owner_id = ?",
        (answer_id, position, LOCAL_OWNER_ID),
    ).fetchone()


def find_answer(connection: sqlite3.Connection, packet_id: str, content_sha256: str, prompt: str | None) -> sqlite3.Row | None:
    """같은 packet에 같은 질문·같은 내용으로 저장해 둔(버리지 않은) 답변."""
    return connection.execute(
        "SELECT answer_id FROM answers WHERE owner_id = ? AND packet_id = ? AND content_sha256 = ? AND prompt IS ?"
        " AND discarded_at IS NULL",
        (LOCAL_OWNER_ID, packet_id, content_sha256, prompt),
    ).fetchone()


def get_answer(connection: sqlite3.Connection, answer_id: str) -> sqlite3.Row | None:
    return connection.execute(_ANSWERS + " WHERE a.answer_id = ? AND a.owner_id = ?", (answer_id, LOCAL_OWNER_ID)).fetchone()


def list_answers(
    connection: sqlite3.Connection,
    limit: int,
    *,
    packet_id: str | None = None,
    paper_id: str | None = None,
    chat_session: str | None = None,
    origin: str | None = None,
) -> list[sqlite3.Row]:
    """버리지 않은 답변, 최근 것부터. paper_id는 packet의 출처 가운데 그 논문이 있는 것."""
    clauses, parameters = ["a.owner_id = ?", "a.discarded_at IS NULL"], [LOCAL_OWNER_ID]
    for clause, value in (("a.packet_id = ?", packet_id), ("a.chat_session = ?", chat_session), ("a.origin = ?", origin)):
        if value is not None:
            clauses.append(clause)
            parameters.append(value)
    if paper_id is not None:
        clauses.append("EXISTS (SELECT 1 FROM json_each(p.content_json, '$.sources') AS s WHERE json_extract(s.value, '$.paper_id') = ?)")
        parameters.append(paper_id)
    query = _ANSWERS + " WHERE " + " AND ".join(clauses) + " ORDER BY a.created_at DESC, a.answer_id LIMIT ?"
    return connection.execute(query, (*parameters, limit)).fetchall()


def discard_answer(connection: sqlite3.Connection, answer_id: str, now: str) -> None:
    connection.execute(
        "UPDATE answers SET discarded_at = COALESCE(discarded_at, ?) WHERE answer_id = ? AND owner_id = ?",
        (now, answer_id, LOCAL_OWNER_ID),
    )
