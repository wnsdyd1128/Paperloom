"""chat_threads SQL. 호출자가 트랜잭션 경계를 정한다."""

import sqlite3

from paperloom.documents.repository import LOCAL_OWNER_ID
from paperloom.reading.repository import ANCHOR_COLUMNS

_THREADS = (
    # 대화와 위치 모두 kind·created_at이 있으므로 대화 쪽에 별칭을 붙인다.
    "SELECT t.chat_session, t.paper_id, t.kind AS thread_kind, t.title, t.placement, t.created_at AS thread_created_at, t.updated_at, "
    + ", ".join(f"n.{column}" for column in ANCHOR_COLUMNS)
    + ", (SELECT COUNT(*) FROM answers AS a WHERE a.chat_session = t.chat_session AND a.discarded_at IS NULL) AS answer_count"
    ", (SELECT MAX(a.created_at) FROM answers AS a WHERE a.chat_session = t.chat_session AND a.discarded_at IS NULL) AS last_answer_at"
    " FROM chat_threads AS t JOIN anchors AS n ON n.anchor_id = t.anchor_id"
    " WHERE t.owner_id = ? AND t.deleted_at IS NULL"
)


def insert_thread(
    connection: sqlite3.Connection, session: str, paper_id: str, anchor_id: str, kind: str, title: str, now: str
) -> None:
    connection.execute(
        "INSERT INTO chat_threads (chat_session, owner_id, paper_id, anchor_id, kind, title, placement, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, 'inline', ?, ?)",
        (session, LOCAL_OWNER_ID, paper_id, anchor_id, kind, title, now, now),
    )


def get_thread(connection: sqlite3.Connection, session: str) -> sqlite3.Row | None:
    return connection.execute(_THREADS + " AND t.chat_session = ?", (LOCAL_OWNER_ID, session)).fetchone()


def list_threads(connection: sqlite3.Connection, paper_id: str) -> list[sqlite3.Row]:
    """지우지 않았고 버리지 않은 답이 남은 대화, 최근에 만든 것부터. 답을 모두 버린 대화(사이드바 대화의 "버리기")는
    빈 대화라 목록에 두지 않는다(2026-10-02 사용자 확인)."""
    return connection.execute(
        _THREADS + " AND t.paper_id = ?"
        " AND EXISTS (SELECT 1 FROM answers AS a WHERE a.chat_session = t.chat_session AND a.discarded_at IS NULL)"
        " ORDER BY t.created_at DESC, t.chat_session",
        (LOCAL_OWNER_ID, paper_id),
    ).fetchall()


def set_placement(connection: sqlite3.Connection, session: str, placement: str, now: str) -> None:
    connection.execute(
        "UPDATE chat_threads SET placement = ?, updated_at = ? WHERE chat_session = ? AND owner_id = ? AND deleted_at IS NULL",
        (placement, now, session, LOCAL_OWNER_ID),
    )


def list_conversations(connection: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    """버리지 않은 답이 있는 Claude Code 대화, 마지막 답이 최근인 것부터 (U6 답변 화면). 첫 차례의 질문·문맥과
    원문 위 대화(지우지 않은 것)·바꾼 이름을 함께 준다. 출처 논문은 첫 차례 문맥의 첫 출처다."""
    return connection.execute(
        "SELECT g.chat_session, g.answer_count, g.last_answer_at, first.prompt AS first_prompt,"
        " json_extract(k.content_json, '$.sources[0].paper_id') AS paper_id,"
        " json_extract(k.content_json, '$.sources[0].version_id') AS version_id,"
        " p.title AS paper_title, c.title AS custom_title,"
        " t.kind AS thread_kind, t.title AS thread_title, t.placement, t.anchor_id, n.page_index"
        " FROM (SELECT chat_session, COUNT(*) AS answer_count, MAX(created_at) AS last_answer_at FROM answers"
        "       WHERE owner_id = ? AND discarded_at IS NULL AND chat_session IS NOT NULL AND origin = 'claude_code'"
        "       GROUP BY chat_session) AS g"
        " JOIN answers AS first ON first.answer_id = (SELECT a.answer_id FROM answers AS a WHERE a.chat_session = g.chat_session"
        "       AND a.discarded_at IS NULL ORDER BY a.created_at, a.answer_id LIMIT 1)"
        " JOIN context_packets AS k ON k.packet_id = first.packet_id"
        " JOIN papers AS p ON p.paper_id = json_extract(k.content_json, '$.sources[0].paper_id')"
        " LEFT JOIN chat_titles AS c ON c.chat_session = g.chat_session AND c.owner_id = ?"
        " LEFT JOIN chat_threads AS t ON t.chat_session = g.chat_session AND t.owner_id = ? AND t.deleted_at IS NULL"
        " LEFT JOIN anchors AS n ON n.anchor_id = t.anchor_id"
        " ORDER BY g.last_answer_at DESC, g.chat_session LIMIT ?",
        (LOCAL_OWNER_ID, LOCAL_OWNER_ID, LOCAL_OWNER_ID, limit),
    ).fetchall()


def list_titles(connection: sqlite3.Connection, paper_id: str) -> list[sqlite3.Row]:
    """그 논문 대화의 이름: 이름을 바꾼 사이드바 대화(chat_titles)와 원문 위에서 시작한 대화(chat_threads). 겹치지 않는다."""
    return connection.execute(
        "SELECT chat_session, title, parent_session, fork_answer_id FROM chat_titles WHERE owner_id = ? AND paper_id = ?"
        " UNION ALL SELECT chat_session, title, NULL, NULL FROM chat_threads WHERE owner_id = ? AND paper_id = ? AND deleted_at IS NULL",
        (LOCAL_OWNER_ID, paper_id, LOCAL_OWNER_ID, paper_id),
    ).fetchall()


def set_title(connection: sqlite3.Connection, session: str, paper_id: str, title: str, now: str) -> None:
    """원문 위에서 시작한 대화면 그 기록의 제목을, 아니면 chat_titles의 이름을 바꾼다."""
    moved = connection.execute(
        "UPDATE chat_threads SET title = ?, updated_at = ? WHERE chat_session = ? AND owner_id = ? AND deleted_at IS NULL",
        (title, now, session, LOCAL_OWNER_ID),
    ).rowcount
    if not moved:
        connection.execute(
            "INSERT INTO chat_titles (chat_session, owner_id, paper_id, title, updated_at) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT (chat_session) DO UPDATE SET title = excluded.title, updated_at = excluded.updated_at",
            (session, LOCAL_OWNER_ID, paper_id, title, now),
        )


def set_fork(
    connection: sqlite3.Connection, session: str, paper_id: str, parent: str, title: str, now: str, at: str | None = None
) -> None:
    """갈래가 갈라져 나온 대화와 그 이름, 답에서 갈라졌으면 그 답을 남긴다."""
    connection.execute(
        "INSERT INTO chat_titles (chat_session, owner_id, paper_id, title, updated_at, parent_session, fork_answer_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (chat_session) DO UPDATE SET title = excluded.title,"
        " updated_at = excluded.updated_at, parent_session = excluded.parent_session, fork_answer_id = excluded.fork_answer_id",
        (session, LOCAL_OWNER_ID, paper_id, title, now, parent, at),
    )


def delete_session(connection: sqlite3.Connection, session: str, now: str) -> None:
    """대화를 지운다: 답을 모두 버리고(대화 기록이 있으면 그것도 목록에서 뺀다) 이름을 지운다."""
    delete_thread(connection, session, now)
    connection.execute("DELETE FROM chat_titles WHERE chat_session = ? AND owner_id = ?", (session, LOCAL_OWNER_ID))


def delete_thread(connection: sqlite3.Connection, session: str, now: str) -> None:
    """대화를 목록에서 빼고 그 대화의 답변을 버린다(지우지 않고 시각을 남긴다)."""
    connection.execute(
        "UPDATE chat_threads SET deleted_at = ?, updated_at = ? WHERE chat_session = ? AND owner_id = ? AND deleted_at IS NULL",
        (now, now, session, LOCAL_OWNER_ID),
    )
    connection.execute(
        "UPDATE answers SET discarded_at = COALESCE(discarded_at, ?) WHERE chat_session = ? AND owner_id = ?",
        (now, session, LOCAL_OWNER_ID),
    )
