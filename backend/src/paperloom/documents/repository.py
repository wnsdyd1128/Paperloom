"""papers·source_versions SQL. 호출자가 트랜잭션 경계를 정한다."""

import json
import sqlite3
import uuid

from paperloom.documents.models import PaperOut, SourceVersionOut, VersionOut

# 단일 사용자 로컬 모드의 소유자. 인증 주체 연결은 W07에서 한다.
LOCAL_OWNER_ID = "local"

_SELECT_PAPER = """
SELECT p.paper_id, p.title, p.authors_json, p.year, p.doi, p.created_at, p.last_opened_at,
       (SELECT json_group_array(name) FROM (
           SELECT t.name FROM paper_tags AS pt JOIN tags AS t ON t.tag_id = pt.tag_id
           WHERE pt.paper_id = p.paper_id ORDER BY t.name)) AS tags_json,
       (SELECT COUNT(*) FROM annotations AS n JOIN anchors AS a ON a.anchor_id = n.anchor_id
           JOIN source_versions AS sv ON sv.version_id = a.version_id
           WHERE sv.paper_id = p.paper_id AND n.owner_id = p.owner_id) AS annotation_count,
       (SELECT COUNT(DISTINCT r.chat_session) FROM answers AS r JOIN context_packets AS k ON k.packet_id = r.packet_id
           WHERE r.owner_id = p.owner_id AND r.discarded_at IS NULL AND r.chat_session IS NOT NULL
             AND EXISTS (SELECT 1 FROM json_each(k.content_json, '$.sources') AS s
                         WHERE json_extract(s.value, '$.paper_id') = p.paper_id)) AS conversation_count,
       v.version_id, v.sha256, v.size_bytes, v.page_count, v.status, v.status_reason,
       v.created_at AS version_created_at
FROM papers AS p JOIN source_versions AS v ON v.version_id = p.current_version_id
"""


def insert_paper(
    connection: sqlite3.Connection,
    *,
    paper_id: str,
    version_id: str,
    title: str,
    sha256: str,
    size_bytes: int,
    page_count: int,
    storage_ref: str,
    status: str,
    created_at: str,
) -> None:
    connection.execute(
        "INSERT INTO papers (paper_id, owner_id, title, current_version_id, created_at) VALUES (?, ?, ?, ?, ?)",
        (paper_id, LOCAL_OWNER_ID, title, version_id, created_at),
    )
    connection.execute(
        "INSERT INTO source_versions (version_id, paper_id, sha256, size_bytes, page_count, storage_ref, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (version_id, paper_id, sha256, size_bytes, page_count, storage_ref, status, created_at),
    )


def find_paper_id_by_sha256(connection: sqlite3.Connection, sha256: str) -> str | None:
    row = connection.execute("SELECT paper_id FROM source_versions WHERE sha256 = ?", (sha256,)).fetchone()
    return row["paper_id"] if row else None


def list_papers(connection: sqlite3.Connection) -> list[PaperOut]:
    # 최근에 연 것 먼저, 연 적이 없으면 등록한 때로 (U6 서재)
    rows = connection.execute(_SELECT_PAPER + " ORDER BY COALESCE(p.last_opened_at, p.created_at) DESC, p.paper_id").fetchall()
    return [_to_paper(row) for row in rows]


def get_paper(connection: sqlite3.Connection, paper_id: str) -> PaperOut | None:
    row = connection.execute(_SELECT_PAPER + " WHERE p.paper_id = ?", (paper_id,)).fetchone()
    return _to_paper(row) if row else None


def get_version(connection: sqlite3.Connection, version_id: str) -> VersionOut | None:
    row = connection.execute(
        "SELECT v.version_id, v.paper_id, v.sha256, v.size_bytes, v.page_count, v.status, v.status_reason, v.created_at"
        " FROM source_versions AS v JOIN papers AS p ON p.paper_id = v.paper_id"
        " WHERE v.version_id = ? AND p.owner_id = ?",
        (version_id, LOCAL_OWNER_ID),
    ).fetchone()
    return VersionOut(**dict(row)) if row else None


def get_storage_ref(connection: sqlite3.Connection, version_id: str) -> str | None:
    row = connection.execute("SELECT storage_ref FROM source_versions WHERE version_id = ?", (version_id,)).fetchone()
    return row["storage_ref"] if row else None


def update_metadata(
    connection: sqlite3.Connection, paper_id: str, *, title: str, authors: list[str], year: int | None, doi: str | None
) -> bool:
    """사용자가 고친 논문 정보. 지운 DOI는 빈 글로 두어 본문 추출이 다시 채우지 않는다(fill_doi). 논문이 없으면 False."""
    cursor = connection.execute(
        "UPDATE papers SET title = ?, authors_json = ?, year = ?, doi = ? WHERE paper_id = ? AND owner_id = ?",
        (title, json.dumps(authors, ensure_ascii=False), year, doi or "", paper_id, LOCAL_OWNER_ID),
    )
    return cursor.rowcount == 1


def set_tags(connection: sqlite3.Connection, paper_id: str, names: list[str], now: str) -> None:
    """논문의 태그를 names로 바꾼다. 대소문자만 다른 이름은 이미 있는 태그(그 이름)를 쓰고, 아무 논문에도 없는 태그는 지운다."""
    connection.execute("DELETE FROM paper_tags WHERE paper_id = ?", (paper_id,))
    for name in names:
        row = connection.execute("SELECT tag_id FROM tags WHERE owner_id = ? AND name = ?", (LOCAL_OWNER_ID, name)).fetchone()
        tag_id = row["tag_id"] if row else str(uuid.uuid4())
        if row is None:
            connection.execute(
                "INSERT INTO tags (tag_id, owner_id, name, created_at) VALUES (?, ?, ?, ?)", (tag_id, LOCAL_OWNER_ID, name, now)
            )
        connection.execute("INSERT OR IGNORE INTO paper_tags (paper_id, tag_id) VALUES (?, ?)", (paper_id, tag_id))
    connection.execute("DELETE FROM tags WHERE owner_id = ? AND tag_id NOT IN (SELECT tag_id FROM paper_tags)", (LOCAL_OWNER_ID,))


def rename_tag(connection: sqlite3.Connection, name: str, new_name: str) -> bool:
    """태그 이름을 바꾼다(그 태그가 붙은 모든 논문). 대소문자만 다르면 이름만 바꾸고, 이미 있는 다른 태그 이름이면 그 태그로
    합친다(그 태그의 이름을 쓴다). 태그가 없으면 False."""
    row = connection.execute("SELECT tag_id FROM tags WHERE owner_id = ? AND name = ?", (LOCAL_OWNER_ID, name)).fetchone()
    if row is None:
        return False
    target = connection.execute(
        "SELECT tag_id FROM tags WHERE owner_id = ? AND name = ? AND tag_id != ?", (LOCAL_OWNER_ID, new_name, row["tag_id"])
    ).fetchone()
    if target is None:
        connection.execute("UPDATE tags SET name = ? WHERE tag_id = ?", (new_name, row["tag_id"]))
        return True
    connection.execute(
        "INSERT OR IGNORE INTO paper_tags (paper_id, tag_id) SELECT paper_id, ? FROM paper_tags WHERE tag_id = ?", (target["tag_id"], row["tag_id"])
    )
    connection.execute("DELETE FROM paper_tags WHERE tag_id = ?", (row["tag_id"],))
    connection.execute("DELETE FROM tags WHERE tag_id = ?", (row["tag_id"],))
    return True


def delete_tag(connection: sqlite3.Connection, name: str) -> bool:
    """태그를 모든 논문에서 떼고 지운다(논문은 그대로). 태그가 없으면 False."""
    row = connection.execute("SELECT tag_id FROM tags WHERE owner_id = ? AND name = ?", (LOCAL_OWNER_ID, name)).fetchone()
    if row is None:
        return False
    connection.execute("DELETE FROM paper_tags WHERE tag_id = ?", (row["tag_id"],))
    connection.execute("DELETE FROM tags WHERE tag_id = ?", (row["tag_id"],))
    return True


def mark_opened(connection: sqlite3.Connection, paper_id: str, now: str) -> bool:
    """Reader로 연 때를 남긴다. 논문이 없으면 False."""
    cursor = connection.execute(
        "UPDATE papers SET last_opened_at = ? WHERE paper_id = ? AND owner_id = ?", (now, paper_id, LOCAL_OWNER_ID)
    )
    return cursor.rowcount == 1


def fill_doi(connection: sqlite3.Connection, paper_id: str, doi: str) -> None:
    """본문 추출이 찾은 DOI. 아직 DOI를 모르는(NULL) 논문만 채운다: 사용자가 고치거나 지운 값은 그대로 둔다."""
    connection.execute("UPDATE papers SET doi = ? WHERE paper_id = ? AND doi IS NULL", (doi, paper_id))


def titles_with_markup(connection: sqlite3.Connection) -> list[tuple[str, str]]:
    """태그 모양(<…>)이 든 제목의 (paper_id, 제목). 메타데이터 제목을 그대로 저장한 예전 논문."""
    rows = connection.execute("SELECT paper_id, title FROM papers WHERE title LIKE '%<%>%'").fetchall()
    return [(row["paper_id"], row["title"]) for row in rows]


def fix_title(connection: sqlite3.Connection, paper_id: str, title: str) -> None:
    connection.execute("UPDATE papers SET title = ? WHERE paper_id = ?", (title, paper_id))


def papers_without_doi(connection: sqlite3.Connection) -> list[tuple[str, str]]:
    """DOI를 모르는 논문의 (paper_id, 지금 버전 ID)"""
    rows = connection.execute("SELECT paper_id, current_version_id FROM papers WHERE doi IS NULL").fetchall()
    return [(row["paper_id"], row["current_version_id"]) for row in rows]


def _to_paper(row: sqlite3.Row) -> PaperOut:
    return PaperOut(
        paper_id=row["paper_id"],
        title=row["title"],
        authors=json.loads(row["authors_json"]),
        year=row["year"],
        doi=row["doi"] or None,  # 빈 글은 사용자가 지운 DOI다
        created_at=row["created_at"],
        tags=json.loads(row["tags_json"]),
        last_opened_at=row["last_opened_at"],
        annotation_count=row["annotation_count"],
        conversation_count=row["conversation_count"],
        current_version=SourceVersionOut(
            version_id=row["version_id"],
            sha256=row["sha256"],
            size_bytes=row["size_bytes"],
            page_count=row["page_count"],
            status=row["status"],
            status_reason=row["status_reason"],
            created_at=row["version_created_at"],
        ),
    )
