"""evidence_bundles SQL. 호출자가 트랜잭션 경계를 정한다."""

import json
import sqlite3

from paperloom.documents.repository import LOCAL_OWNER_ID


def insert_bundle(
    connection: sqlite3.Connection,
    *,
    bundle_id: str,
    status: str,
    error_code: str | None,
    schema_version: str | None,
    manifest_sha256: str | None,
    file_count: int,
    size_bytes: int,
    papers: list[dict],
    counts: dict,
    files: list[dict],
    created_at: str,
) -> None:
    connection.execute(
        "INSERT INTO evidence_bundles (bundle_id, owner_id, status, error_code, schema_version, manifest_sha256, file_count,"
        " size_bytes, papers_json, counts_json, files_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            bundle_id, LOCAL_OWNER_ID, status, error_code, schema_version, manifest_sha256, file_count, size_bytes,
            json.dumps(papers, ensure_ascii=False), json.dumps(counts), json.dumps(files), created_at,
        ),
    )


def get_bundle(connection: sqlite3.Connection, bundle_id: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM evidence_bundles WHERE bundle_id = ? AND owner_id = ?", (bundle_id, LOCAL_OWNER_ID)
    ).fetchone()


def list_bundles(connection: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    """최근 것부터"""
    return connection.execute(
        "SELECT * FROM evidence_bundles WHERE owner_id = ? ORDER BY created_at DESC, bundle_id LIMIT ?", (LOCAL_OWNER_ID, limit)
    ).fetchall()
