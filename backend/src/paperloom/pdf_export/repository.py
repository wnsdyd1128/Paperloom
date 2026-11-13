"""PDF 내보내기가 읽는 SQL: 한 판본에서 시작한 설명·질문 대화와 그 차례들. 읽기만 한다."""

import sqlite3

from paperloom.documents.repository import LOCAL_OWNER_ID
from paperloom.reading.repository import ANCHOR_COLUMNS


def list_threads(connection: sqlite3.Connection, version_id: str) -> list[sqlite3.Row]:
    """지우지 않은 설명·질문 대화와 그 시작 위치(이 판본의 것). 번역 대화는 내보내지 않는다."""
    return connection.execute(
        "SELECT t.chat_session, t.kind AS thread_kind, "
        + ", ".join(f"n.{column}" for column in ANCHOR_COLUMNS)
        + " FROM chat_threads AS t JOIN anchors AS n ON n.anchor_id = t.anchor_id"
        " WHERE t.owner_id = ? AND t.deleted_at IS NULL AND t.kind IN ('explain', 'ask') AND n.version_id = ?"
        " ORDER BY t.created_at, t.chat_session",
        (LOCAL_OWNER_ID, version_id),
    ).fetchall()


def list_turns(connection: sqlite3.Connection, chat_session: str) -> list[sqlite3.Row]:
    """대화의 버리지 않은 차례(질문·답), 오래된 것부터."""
    return connection.execute(
        "SELECT prompt, markdown FROM answers WHERE owner_id = ? AND chat_session = ? AND discarded_at IS NULL"
        " ORDER BY created_at, answer_id",
        (LOCAL_OWNER_ID, chat_session),
    ).fetchall()
