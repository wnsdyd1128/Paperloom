"""context_packets SQL. 호출자가 트랜잭션 경계를 정한다."""

import sqlite3

from paperloom.documents.repository import LOCAL_OWNER_ID

_COLUMNS = "packet_id, content_json, content_sha256, status, created_at, handed_off_at, handoff_method, cancelled_at"


def insert_packet(connection: sqlite3.Connection, packet_id: str, content_json: str, content_sha256: str, created_at: str) -> None:
    connection.execute(
        "INSERT INTO context_packets (packet_id, owner_id, content_json, content_sha256, status, created_at)"
        " VALUES (?, ?, ?, ?, 'PREPARED', ?)",
        (packet_id, LOCAL_OWNER_ID, content_json, content_sha256, created_at),
    )


def get_packet(connection: sqlite3.Connection, packet_id: str) -> sqlite3.Row | None:
    return connection.execute(
        f"SELECT {_COLUMNS} FROM context_packets WHERE packet_id = ? AND owner_id = ?", (packet_id, LOCAL_OWNER_ID)
    ).fetchone()


def hand_off(connection: sqlite3.Connection, packet_id: str, method: str, now: str) -> bool:
    """전달했다: 사용자가 복사·내보내기를 했거나(clipboard·file) Reader 대화 탭이 Claude Code에 보냈다(claude_code).
    처음 전달한 때와 방법을 남긴다. 다시 전달해도 그대로 HANDED_OFF다(답변을 받은 IMPORTED는 그대로 둔다)."""
    cursor = connection.execute(
        "UPDATE context_packets SET status = CASE status WHEN 'IMPORTED' THEN 'IMPORTED' ELSE 'HANDED_OFF' END,"
        " confirmed_at = COALESCE(confirmed_at, ?), handed_off_at = COALESCE(handed_off_at, ?),"
        " handoff_method = COALESCE(handoff_method, ?)"
        " WHERE packet_id = ? AND owner_id = ? AND status IN ('PREPARED', 'USER_CONFIRMED', 'HANDED_OFF', 'IMPORTED')",
        (now, now, method, packet_id, LOCAL_OWNER_ID),
    )
    return cursor.rowcount == 1


def import_answer(connection: sqlite3.Connection, packet_id: str, now: str) -> None:
    """이 packet에 대한 답변을 받았다(Claude Code 대화의 답을 저장). 답변이 있으면 전달된 것이므로 전달 시각도 남긴다.
    USER_CONFIRMED·'mcp'는 2026-10-05에 뺀 MCP 공유가 남긴 예전 packet이다."""
    connection.execute(
        "UPDATE context_packets SET status = 'IMPORTED', confirmed_at = COALESCE(confirmed_at, ?),"
        " handed_off_at = COALESCE(handed_off_at, ?), handoff_method = COALESCE(handoff_method, 'mcp')"
        " WHERE packet_id = ? AND owner_id = ? AND status IN ('USER_CONFIRMED', 'HANDED_OFF', 'IMPORTED')",
        (now, now, packet_id, LOCAL_OWNER_ID),
    )


def cancel(connection: sqlite3.Connection, packet_id: str, now: str) -> bool:
    cursor = connection.execute(
        "UPDATE context_packets SET status = 'CANCELLED', cancelled_at = ? WHERE packet_id = ? AND owner_id = ? AND status = 'PREPARED'",
        (now, packet_id, LOCAL_OWNER_ID),
    )
    return cursor.rowcount == 1
