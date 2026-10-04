from contextlib import closing

import pytest

from paperloom.infrastructure.database.sqlite import MIGRATIONS, connect, migrate


def test_migrate_is_idempotent_and_records_schema_version(tmp_path):
    db_path = tmp_path / "paperloom.sqlite3"

    migrate(db_path)
    migrate(db_path)

    with closing(connect(db_path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {
        "papers", "source_versions", "anchors", "annotations", "parse_runs", "pages", "text_blocks", "context_packets",
        "idempotency_keys", "host_connections", "share_grants", "answers", "chat_threads",
    } <= tables


def test_migrate_v6_adds_answers_and_chat_columns_and_keeps_shared_packets(tmp_path):
    # W07 시점(v6) DB의 packet·연결·공유가 v7(답변, ADR 0002) 뒤에도 그대로다.
    db_path = tmp_path / "paperloom.sqlite3"
    with closing(connect(db_path)) as connection:
        for number, script in enumerate(MIGRATIONS[:6], start=1):
            connection.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
        with connection:
            connection.execute("INSERT INTO context_packets (packet_id, owner_id, content_json, content_sha256, status, created_at)"
                               " VALUES ('k1', 'local', '{}', 'h', 'HANDED_OFF', 'now')")
            connection.execute("INSERT INTO host_connections VALUES ('c1', 'local', 'Claude Desktop', 't', 'now', NULL, NULL)")
            connection.execute("INSERT INTO share_grants VALUES ('g1', 'local', 'c1', 'packet', 'k1', 'now', 1.0, NULL, NULL)")

    migrate(db_path)

    with closing(connect(db_path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS) == 16
        assert connection.execute("SELECT status FROM context_packets").fetchone()[0] == "HANDED_OFF"
        assert connection.execute("SELECT resource_id FROM share_grants").fetchone()[0] == "k1"
        assert connection.execute("SELECT COUNT(*) FROM answers").fetchone()[0] == 0
        columns = {row[1] for row in connection.execute("PRAGMA table_info(answers)")}
        assert connection.execute("SELECT COUNT(*) FROM chat_threads").fetchone()[0] == 0  # v9: 선택 설명·질문 대화
        assert connection.execute("SELECT COUNT(*) FROM chat_titles").fetchone()[0] == 0  # v10: 사이드바 대화 이름
    assert {"prompt", "chat_session"} <= columns  # v8: Claude Code 대화 (ADR 0003)
    assert {"context_tokens", "context_window"} <= columns  # v11: 차례 끝의 컨텍스트 길이
    assert "cc_message_id" in columns  # v12: 답마다 갈래


def test_migrate_v13_colors_highlights_saved_without_a_memo(tmp_path):
    """U5: 메모 없는 텍스트 주석(예전 하이라이트 H, 메모를 비운 주석)은 첫 색(c1) 하이라이트가 된다.
    메모가 있는 주석과 영역 주석은 색이 없다."""
    db_path = tmp_path / "paperloom.sqlite3"
    with closing(connect(db_path)) as connection:
        for number, script in enumerate(MIGRATIONS[:12], start=1):
            connection.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
        connection.execute("PRAGMA foreign_keys = OFF")  # 논문·버전 없이 주석만 넣는다
        with connection:
            for anchor_id, kind in (("text", "text"), ("noted", "text"), ("region", "figure")):
                connection.execute(
                    "INSERT INTO anchors (anchor_id, version_id, page_index, quads_json, quote, display_quote, prefix, suffix,"
                    " schema_version, created_at, kind) VALUES (?, 'v', 0, '[]', '', NULL, '', '', 'anchor.v1', 'now', ?)",
                    (anchor_id, kind),
                )
            for annotation_id, anchor_id, comment in (("h", "text", ""), ("n", "noted", "메모"), ("r", "region", "")):
                connection.execute(
                    "INSERT INTO annotations VALUES (?, 'local', ?, ?, 1, 'now', 'now')", (annotation_id, anchor_id, comment)
                )

    migrate(db_path)

    with closing(connect(db_path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
        colors = dict(connection.execute("SELECT annotation_id, color FROM annotations").fetchall())
    assert colors == {"h": "c1", "n": None, "r": None}


def test_migrate_upgrades_v1_database_in_place(tmp_path):
    # W02 시점(v1) DB에 등록된 논문이 v2 마이그레이션 뒤에도 남는다.
    db_path = tmp_path / "paperloom.sqlite3"
    with closing(connect(db_path)) as connection:
        connection.executescript(f"BEGIN;\n{MIGRATIONS[0]}\nPRAGMA user_version = 1;\nCOMMIT;")
        with connection:
            connection.execute("INSERT INTO papers VALUES ('p1', 'local', 'T', '[]', NULL, NULL, 'v1', 'now')")
            connection.execute("INSERT INTO source_versions VALUES ('v1', 'p1', 'h', 1, 1, 'sources/v1.pdf', 'READY_TO_READ', 'now')")

    migrate(db_path)

    with closing(connect(db_path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
        assert connection.execute("SELECT paper_id FROM papers").fetchall()[0][0] == "p1"
        assert connection.execute("SELECT COUNT(*) FROM anchors").fetchone()[0] == 0


def test_migrate_v3_adds_extraction_tables_and_indexes_existing_titles(tmp_path):
    # W04a 시점(v3) DB의 논문 제목이 검색 색인에 들어가고, 버전은 추출 전 상태 그대로다(추출은 서버 시작 때 넣는다).
    db_path = tmp_path / "paperloom.sqlite3"
    with closing(connect(db_path)) as connection:
        for number, script in enumerate(MIGRATIONS[:3], start=1):
            connection.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
        with connection:
            connection.execute("INSERT INTO papers VALUES ('p1', 'local', 'Cache Partitioning', '[]', NULL, NULL, 'v1', 'now')")
            connection.execute("INSERT INTO source_versions VALUES ('v1', 'p1', 'h', 1, 1, 'sources/v1.pdf', 'READY_TO_READ', 'now')")

    migrate(db_path)

    with closing(connect(db_path)) as connection:
        assert connection.execute("SELECT status, status_reason FROM source_versions").fetchone()[:] == ("READY_TO_READ", None)
        assert connection.execute("SELECT paper_id FROM papers_fts WHERE papers_fts MATCH 'partitioning'").fetchall()[0][0] == "p1"
        with connection:
            connection.execute("UPDATE papers SET title = 'Renamed Paper' WHERE paper_id = 'p1'")
        assert connection.execute("SELECT COUNT(*) FROM papers_fts WHERE papers_fts MATCH 'partitioning'").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM papers_fts WHERE papers_fts MATCH 'renamed'").fetchone()[0] == 1


def test_migrate_refuses_newer_schema(tmp_path):
    db_path = tmp_path / "paperloom.sqlite3"
    with closing(connect(db_path)) as connection:
        connection.execute(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")

    with pytest.raises(RuntimeError, match="새롭습니다"):
        migrate(db_path)


def test_migrate_v16_adds_block_styles_and_font_size(tmp_path):
    """U7 뒤: 문단의 굵게·기울임 구간과 글꼴 크기"""
    db_path = tmp_path / "paperloom.sqlite3"
    migrate(db_path)
    with closing(connect(db_path)) as connection:
        columns = {row[1]: row for row in connection.execute("PRAGMA table_info(text_blocks)")}
    assert columns["styles_json"][4] == "'[]'" and columns["font_size"][2] == "REAL"


def test_migrate_v15_adds_page_translations(tmp_path):
    """U7: 쪽·언어마다 번역(page_translations)"""
    db_path = tmp_path / "paperloom.sqlite3"
    migrate(db_path)
    with closing(connect(db_path)) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(page_translations)")]
    assert columns == ["version_id", "page_index", "language", "model", "blocks_json", "created_at"]


def test_migrate_v14_adds_tags_opened_time_and_settings(tmp_path):
    """U6: 태그(tags·paper_tags), 마지막 열람(papers.last_opened_at), 설정(preferences)."""
    db_path = tmp_path / "paperloom.sqlite3"
    migrate(db_path)
    with closing(connect(db_path)) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        columns = {row[1] for row in connection.execute("PRAGMA table_info(papers)")}
    assert {"tags", "paper_tags", "preferences"} <= tables
    assert "last_opened_at" in columns
