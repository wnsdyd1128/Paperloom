"""본문 추출(parse_runs·pages·text_blocks) SQL. 호출자가 트랜잭션 경계를 정한다.

parse_runs의 상태: QUEUED → RUNNING → DONE(쪽·문단 저장) | FAILED(끝내지 못함). 다른 worker가 가져간 작업을
덮어쓰지 않도록 상태를 바꾸는 문장은 모두 기대하는 상태·lease_owner를 조건으로 건다.
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass

from paperloom.documents.repository import LOCAL_OWNER_ID


@dataclass(frozen=True)
class ParseRun:
    parse_run_id: str
    version_id: str
    status: str
    attempts: int
    lease_expires_at: float | None


_RUN_COLUMNS = "parse_run_id, version_id, status, attempts, lease_expires_at"


def insert_run(
    connection: sqlite3.Connection, version_id: str, parser_name: str, parser_version: str, config_hash: str, created_at: str
) -> str:
    run_id = str(uuid.uuid4())
    connection.execute(
        "INSERT INTO parse_runs (parse_run_id, version_id, parser_name, parser_version, config_hash, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, 'QUEUED', ?)",
        (run_id, version_id, parser_name, parser_version, config_hash, created_at),
    )
    return run_id


def active_run(connection: sqlite3.Connection, version_id: str) -> ParseRun | None:
    row = connection.execute(
        f"SELECT {_RUN_COLUMNS} FROM parse_runs WHERE version_id = ? AND status IN ('QUEUED', 'RUNNING')", (version_id,)
    ).fetchone()
    return ParseRun(**dict(row)) if row else None


def next_claimable(connection: sqlite3.Connection, now: float) -> ParseRun | None:
    """대기 중이거나 lease가 끝난(worker가 멈춘) 작업 중 가장 오래된 것."""
    row = connection.execute(
        f"SELECT {_RUN_COLUMNS} FROM parse_runs"
        " WHERE status = 'QUEUED' OR (status = 'RUNNING' AND lease_expires_at < ?)"
        " ORDER BY created_at, parse_run_id LIMIT 1",
        (now,),
    ).fetchone()
    return ParseRun(**dict(row)) if row else None


def claim(connection: sqlite3.Connection, run: ParseRun, owner: str, lease_until: float, started_at: str) -> bool:
    """run을 본 그 상태 그대로일 때만 가져간다."""
    cursor = connection.execute(
        "UPDATE parse_runs SET status = 'RUNNING', attempts = attempts + 1, lease_owner = ?, lease_expires_at = ?,"
        " started_at = ? WHERE parse_run_id = ? AND status = ? AND lease_expires_at IS ?",
        (owner, lease_until, started_at, run.parse_run_id, run.status, run.lease_expires_at),
    )
    return cursor.rowcount == 1


def extend_lease(connection: sqlite3.Connection, run_id: str, owner: str, lease_until: float) -> bool:
    cursor = connection.execute(
        "UPDATE parse_runs SET lease_expires_at = ? WHERE parse_run_id = ? AND status = 'RUNNING' AND lease_owner = ?",
        (lease_until, run_id, owner),
    )
    return cursor.rowcount == 1


def finish_run(
    connection: sqlite3.Connection, run_id: str, owner: str, status: str, finished_at: str, error_code: str | None = None
) -> bool:
    """lease를 가진 worker가 run을 DONE 또는 FAILED로 끝낸다."""
    cursor = connection.execute(
        "UPDATE parse_runs SET status = ?, error_code = ?, finished_at = ?, lease_owner = NULL, lease_expires_at = NULL"
        " WHERE parse_run_id = ? AND status = 'RUNNING' AND lease_owner = ?",
        (status, error_code, finished_at, run_id, owner),
    )
    return cursor.rowcount == 1


def give_up(connection: sqlite3.Connection, run: ParseRun, finished_at: str, error_code: str) -> bool:
    """시도 횟수를 다 쓴 run을 본 그 상태 그대로일 때만 FAILED로 끝낸다."""
    cursor = connection.execute(
        "UPDATE parse_runs SET status = 'FAILED', error_code = ?, finished_at = ?, lease_owner = NULL,"
        " lease_expires_at = NULL WHERE parse_run_id = ? AND status = ? AND lease_expires_at IS ?",
        (error_code, finished_at, run.parse_run_id, run.status, run.lease_expires_at),
    )
    return cursor.rowcount == 1


def release(connection: sqlite3.Connection, run_id: str, owner: str) -> bool:
    """잠깐의 I/O 오류 뒤 다시 시도하도록 대기열로 되돌린다."""
    cursor = connection.execute(
        "UPDATE parse_runs SET status = 'QUEUED', lease_owner = NULL, lease_expires_at = NULL"
        " WHERE parse_run_id = ? AND status = 'RUNNING' AND lease_owner = ?",
        (run_id, owner),
    )
    return cursor.rowcount == 1


def release_abandoned(connection: sqlite3.Connection, owner: str) -> int:
    """다른(이전) 프로세스가 실행 중이던 run을 대기열로 되돌린다. 시도 횟수는 그대로 둔다."""
    cursor = connection.execute(
        "UPDATE parse_runs SET status = 'QUEUED', lease_owner = NULL, lease_expires_at = NULL"
        " WHERE status = 'RUNNING' AND lease_owner IS NOT ?",
        (owner,),
    )
    return cursor.rowcount


def versions_without_run(connection: sqlite3.Connection, parser_version: str, config_hash: str) -> list[str]:
    """지금 추출기로 만든(또는 만들고 있는) run이 없는 버전. 추출기가 바뀌면 다시 추출한다."""
    rows = connection.execute(
        "SELECT v.version_id FROM source_versions AS v WHERE NOT EXISTS ("
        " SELECT 1 FROM parse_runs AS r WHERE r.version_id = v.version_id"
        " AND (r.status IN ('QUEUED', 'RUNNING') OR (r.parser_version = ? AND r.config_hash = ?))"
        ") ORDER BY v.created_at, v.version_id",
        (parser_version, config_hash),
    ).fetchall()
    return [row["version_id"] for row in rows]


def set_version_status(connection: sqlite3.Connection, version_id: str, status: str, reason: str | None = None) -> None:
    connection.execute("UPDATE source_versions SET status = ?, status_reason = ? WHERE version_id = ?", (status, reason, version_id))


def replace_extraction(connection: sqlite3.Connection, version_id: str, run_id: str, pages: list[dict]) -> None:
    """버전의 쪽·문단을 이번 추출 결과로 바꾼다. 검색 색인은 트리거가 맞춘다. 같은 쪽에 글이 같은 문단은 앞 추출의 block ID를
    그대로 쓴다(같은 글이 여럿이면 읽는 차례로 짝짓는다). 2026-10-04: 추출기를 고칠 때마다 모든 ID가 바뀌어 예전 대화·packet의
    문단 근거 링크가 그 문단을 찾지 못하고 쪽만 열었다. 글이 바뀐 문단은 새 ID다."""
    previous: dict[tuple[int, str], list[str]] = {}
    for row in connection.execute(
        "SELECT block_id, page_index, text FROM text_blocks WHERE version_id = ? ORDER BY page_index, reading_order", (version_id,)
    ):
        previous.setdefault((row["page_index"], row["text"]), []).append(row["block_id"])

    def block_id(page_index: int, text: str) -> str:
        kept = previous.get((page_index, text))
        return kept.pop(0) if kept else str(uuid.uuid4())

    clear_extraction(connection, version_id)
    connection.executemany(
        "INSERT INTO pages (version_id, page_index, parse_run_id, page_label, view_box_json, rotation, text_status,"
        " flags_json, quality_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                version_id,
                page["page_index"],
                run_id,
                page.get("page_label"),
                json.dumps(page.get("view_box")),
                page.get("rotation", 0),
                page["text_status"],
                json.dumps(page["flags"]),
                json.dumps(page["quality"]),
            )
            for page in pages
        ],
    )
    connection.executemany(
        "INSERT INTO text_blocks (block_id, parse_run_id, version_id, page_index, reading_order, text, regions_json,"
        " quality_flags_json, styles_json, font_size) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                block_id(page["page_index"], block["text"]),
                run_id,
                version_id,
                page["page_index"],
                order,
                block["text"],
                json.dumps(block["regions"]),
                json.dumps(block["quality_flags"]),
                json.dumps(block.get("styles", [])),
                block.get("font_size"),
            )
            for page in pages
            for order, block in enumerate(page["blocks"])
        ],
    )


def clear_extraction(connection: sqlite3.Connection, version_id: str) -> None:
    connection.execute("DELETE FROM text_blocks WHERE version_id = ?", (version_id,))
    connection.execute("DELETE FROM pages WHERE version_id = ?", (version_id,))


_OWNED_PAGES = (
    "SELECT g.* FROM pages AS g JOIN source_versions AS v ON v.version_id = g.version_id"
    " JOIN papers AS p ON p.paper_id = v.paper_id WHERE g.version_id = ? AND p.owner_id = ?"
)


def list_pages(connection: sqlite3.Connection, version_id: str) -> list[sqlite3.Row]:
    return connection.execute(_OWNED_PAGES + " ORDER BY g.page_index", (version_id, LOCAL_OWNER_ID)).fetchall()


def get_page(connection: sqlite3.Connection, version_id: str, page_index: int) -> sqlite3.Row | None:
    return connection.execute(_OWNED_PAGES + " AND g.page_index = ?", (version_id, LOCAL_OWNER_ID, page_index)).fetchone()


def page_blocks(connection: sqlite3.Connection, version_id: str, page_index: int) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT block_id, reading_order, text, regions_json, quality_flags_json, styles_json, font_size FROM text_blocks"
        " WHERE version_id = ? AND page_index = ? ORDER BY reading_order",
        (version_id, page_index),
    ).fetchall()


def blocks_on_pages(connection: sqlite3.Connection, version_id: str, pages: list[int]) -> list[sqlite3.Row]:
    """여러 쪽의 문단을 (쪽, 읽는 순서) 순으로. 문맥(W06)의 앞뒤 문단 찾기에 쓴다."""
    marks = ", ".join("?" for _ in pages)
    return connection.execute(
        "SELECT block_id, page_index, reading_order, text, regions_json, quality_flags_json FROM text_blocks"
        f" WHERE version_id = ? AND page_index IN ({marks}) ORDER BY page_index, reading_order",
        (version_id, *pages),
    ).fetchall()
