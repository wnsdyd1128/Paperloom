"""SQLite 연결과 스키마 마이그레이션 (IMPL §4.2).

스키마 버전은 `PRAGMA user_version`으로 관리한다. 각 마이그레이션은 한 트랜잭션으로 적용하며,
코드보다 새 버전의 DB는 열지 않는다.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

# papers ↔ source_versions는 서로를 참조하므로 외래 키 검사를 commit 시점으로 미룬다.
_SCHEMA_V1 = """
CREATE TABLE papers (
    paper_id           TEXT PRIMARY KEY,
    owner_id           TEXT NOT NULL,
    title              TEXT NOT NULL,
    authors_json       TEXT NOT NULL DEFAULT '[]',
    year               INTEGER,
    doi                TEXT,
    current_version_id TEXT NOT NULL
        REFERENCES source_versions (version_id) DEFERRABLE INITIALLY DEFERRED,
    created_at         TEXT NOT NULL
);
CREATE TABLE source_versions (
    version_id  TEXT PRIMARY KEY,
    paper_id    TEXT NOT NULL REFERENCES papers (paper_id) DEFERRABLE INITIALLY DEFERRED,
    sha256      TEXT NOT NULL UNIQUE,
    size_bytes  INTEGER NOT NULL,
    page_count  INTEGER NOT NULL,
    storage_ref TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
"""

# W04: 원문 위치(Anchor)와 주석. Anchor는 만든 뒤 바꾸지 않는다(IMPL §6.3의 재앵커는 새 Anchor + 주석 revision).
_SCHEMA_V2 = """
CREATE TABLE anchors (
    anchor_id      TEXT PRIMARY KEY,
    version_id     TEXT NOT NULL REFERENCES source_versions (version_id),
    page_index     INTEGER NOT NULL,
    quads_json     TEXT NOT NULL,
    quote          TEXT NOT NULL,
    display_quote  TEXT,
    prefix         TEXT NOT NULL,
    suffix         TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
CREATE INDEX anchors_by_version ON anchors (version_id, page_index);
CREATE TABLE annotations (
    annotation_id TEXT PRIMARY KEY,
    owner_id      TEXT NOT NULL,
    anchor_id     TEXT NOT NULL REFERENCES anchors (anchor_id),
    comment       TEXT NOT NULL,
    revision      INTEGER NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX annotations_by_anchor ON annotations (anchor_id);
"""

# W04a: 영역 Anchor. 기존 Anchor는 텍스트 선택이다.
_SCHEMA_V3 = """
ALTER TABLE anchors ADD COLUMN kind TEXT NOT NULL DEFAULT 'text';
"""

# W05: 본문 추출(ParseRun·Page·TextBlock)과 키워드 검색(FTS5). 추출 결과는 원문 버전과 분리된 파생물이다.
# parse_runs는 작업 대기열도 겸한다: lease_owner·lease_expires_at(UNIX 초)로 재시작 뒤 중복 실행을 막는다.
# text_blocks는 버전마다 마지막으로 끝난 추출의 문단만 둔다. FTS 색인은 트리거로 맞춘다(외부 content).
# 검색 색인의 rowid가 VACUUM으로 바뀌지 않도록 text_blocks에는 INTEGER PRIMARY KEY를 둔다. papers 색인은
# papers의 rowid에 기대지 않도록 내용을 함께 저장한다.
_SCHEMA_V4 = """
ALTER TABLE source_versions ADD COLUMN status_reason TEXT;
CREATE TABLE parse_runs (
    parse_run_id     TEXT PRIMARY KEY,
    version_id       TEXT NOT NULL REFERENCES source_versions (version_id),
    parser_name      TEXT NOT NULL,
    parser_version   TEXT NOT NULL,
    config_hash      TEXT NOT NULL,
    status           TEXT NOT NULL,
    attempts         INTEGER NOT NULL DEFAULT 0,
    lease_owner      TEXT,
    lease_expires_at REAL,
    error_code       TEXT,
    created_at       TEXT NOT NULL,
    started_at       TEXT,
    finished_at      TEXT
);
CREATE INDEX parse_runs_by_status ON parse_runs (status, created_at);
CREATE INDEX parse_runs_by_version ON parse_runs (version_id);
CREATE TABLE pages (
    version_id    TEXT NOT NULL REFERENCES source_versions (version_id),
    page_index    INTEGER NOT NULL,
    parse_run_id  TEXT NOT NULL REFERENCES parse_runs (parse_run_id),
    page_label    TEXT,
    view_box_json TEXT NOT NULL,
    rotation      INTEGER NOT NULL,
    text_status   TEXT NOT NULL,
    flags_json    TEXT NOT NULL,
    quality_json  TEXT NOT NULL,
    PRIMARY KEY (version_id, page_index)
);
CREATE TABLE text_blocks (
    id                 INTEGER PRIMARY KEY,
    block_id           TEXT NOT NULL UNIQUE,
    parse_run_id       TEXT NOT NULL REFERENCES parse_runs (parse_run_id),
    version_id         TEXT NOT NULL REFERENCES source_versions (version_id),
    page_index         INTEGER NOT NULL,
    reading_order      INTEGER NOT NULL,
    text               TEXT NOT NULL,
    regions_json       TEXT NOT NULL,
    quality_flags_json TEXT NOT NULL
);
CREATE INDEX text_blocks_by_page ON text_blocks (version_id, page_index, reading_order);
CREATE VIRTUAL TABLE text_blocks_fts USING fts5(
    text, content='text_blocks', content_rowid='id', tokenize='porter unicode61 remove_diacritics 2'
);
CREATE TRIGGER text_blocks_fts_insert AFTER INSERT ON text_blocks BEGIN
    INSERT INTO text_blocks_fts (rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER text_blocks_fts_delete AFTER DELETE ON text_blocks BEGIN
    INSERT INTO text_blocks_fts (text_blocks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE VIRTUAL TABLE papers_fts USING fts5(
    paper_id UNINDEXED, title, authors, tokenize='porter unicode61 remove_diacritics 2'
);
CREATE TRIGGER papers_fts_insert AFTER INSERT ON papers BEGIN
    INSERT INTO papers_fts (paper_id, title, authors) VALUES (new.paper_id, new.title, new.authors_json);
END;
CREATE TRIGGER papers_fts_update AFTER UPDATE OF title, authors_json ON papers BEGIN
    UPDATE papers_fts SET title = new.title, authors = new.authors_json WHERE paper_id = old.paper_id;
END;
CREATE TRIGGER papers_fts_delete AFTER DELETE ON papers BEGIN
    DELETE FROM papers_fts WHERE paper_id = old.paper_id;
END;
INSERT INTO papers_fts (paper_id, title, authors) SELECT paper_id, title, authors_json FROM papers;
"""

# W06: 문맥 묶음(ContextPacket)과 재전송 방지 키. packet의 내용(content_json)은 만든 뒤 바꾸지 않고, 전달 상태만 바뀐다.
# idempotency_keys는 응답을 저장해 같은 키·같은 요청에 같은 응답을 돌려준다(status_code가 NULL이면 처리 중).
_SCHEMA_V5 = """
CREATE TABLE context_packets (
    packet_id      TEXT PRIMARY KEY,
    owner_id       TEXT NOT NULL,
    content_json   TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    status         TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    confirmed_at   TEXT,
    handed_off_at  TEXT,
    handoff_method TEXT,
    cancelled_at   TEXT
);
CREATE TABLE idempotency_keys (
    scope          TEXT NOT NULL,
    key            TEXT NOT NULL,
    request_sha256 TEXT NOT NULL,
    status_code    INTEGER,
    response_json  TEXT,
    created_at     REAL NOT NULL,
    PRIMARY KEY (scope, key)
);
"""

# W07: AI 호스트 연결(MCP 주체)과 공유 허락(ShareGrant, IMPL §9.2). 연결 토큰은 해시만 저장한다.
# 2026-10-05 MCP·공유를 빼 더 쓰지 않는다(예전 답변의 연결 이름을 읽으려고 표는 둔다).
# 만료는 비교하기 쉽게 UNIX 초(REAL)로 둔다. 철회는 지우지 않고 시각을 남긴다.
_SCHEMA_V6 = """
CREATE TABLE host_connections (
    connection_id TEXT PRIMARY KEY,
    owner_id      TEXT NOT NULL,
    name          TEXT NOT NULL,
    token_sha256  TEXT NOT NULL UNIQUE,
    created_at    TEXT NOT NULL,
    last_used_at  TEXT,
    revoked_at    TEXT
);
CREATE TABLE share_grants (
    grant_id      TEXT PRIMARY KEY,
    owner_id      TEXT NOT NULL,
    connection_id TEXT NOT NULL REFERENCES host_connections (connection_id),
    resource_type TEXT NOT NULL,
    resource_id   TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    expires_at    REAL NOT NULL,
    revoked_at    TEXT,
    last_read_at  TEXT
);
CREATE INDEX share_grants_by_resource ON share_grants (resource_type, resource_id);
CREATE INDEX share_grants_by_connection ON share_grants (connection_id);
"""

# 호스트가 저장한 답변(AnswerArtifact, IMPL §11.1). packet에 딸리고 검토 전(unreviewed)으로 들어온다.
# 인용 번호(citations_json)는 저장할 때 packet 근거와 맞춰 둔다(packet은 바뀌지 않는다). 버리면 지우지 않고 시각을 남긴다.
_SCHEMA_V7 = """
CREATE TABLE answers (
    answer_id      TEXT PRIMARY KEY,
    owner_id       TEXT NOT NULL,
    packet_id      TEXT NOT NULL REFERENCES context_packets (packet_id),
    connection_id  TEXT REFERENCES host_connections (connection_id),
    origin         TEXT NOT NULL,
    markdown       TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    citations_json TEXT NOT NULL,
    review_status  TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    discarded_at   TEXT
);
CREATE INDEX answers_by_packet ON answers (packet_id);
"""

# Reader의 Claude Code 대화(ADR 0003): 답변마다 그 차례의 질문(prompt)과 이어 묻기에 쓰는 대화 ID(chat_session).
# 호스트(MCP)가 저장한 답변은 둘 다 비어 있다.
_SCHEMA_V8 = """
ALTER TABLE answers ADD COLUMN prompt TEXT;
ALTER TABLE answers ADD COLUMN chat_session TEXT;
"""

# 선택 설명·질문 대화(docs/UI_PLAN.md A4): 원문 위 창으로 이어지는 Claude Code 대화 하나. 대화 ID(chat_session)는 답변에
# 있는 것이다. placement는 원문 위(inline)·사이드바(sidebar). 지우면 시각을 남기고 그 대화의 답변을 버린다.
_SCHEMA_V9 = """
CREATE TABLE chat_threads (
    chat_session TEXT PRIMARY KEY,
    owner_id     TEXT NOT NULL,
    paper_id     TEXT NOT NULL REFERENCES papers (paper_id),
    anchor_id    TEXT NOT NULL REFERENCES anchors (anchor_id),
    kind         TEXT NOT NULL,
    title        TEXT NOT NULL,
    placement    TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    deleted_at   TEXT
);
CREATE INDEX chat_threads_by_paper ON chat_threads (paper_id);
"""

# 사이드바 "Claude와 대화"의 대화 이름(2026-10-02 사용자 요청). 이름을 바꾼 대화만 남는다. 원문 위에서 옮겨 온 대화는
# chat_threads의 제목을 바꾸므로 여기에 없다. 대화를 지우면 이름도 지운다.
_SCHEMA_V10 = """
CREATE TABLE chat_titles (
    chat_session TEXT PRIMARY KEY,
    owner_id     TEXT NOT NULL,
    paper_id     TEXT NOT NULL REFERENCES papers (paper_id),
    title        TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX chat_titles_by_paper ON chat_titles (paper_id);
"""

# 2026-10-02 사용자 요청: 차례 끝의 컨텍스트 길이(브리지가 Claude Code 결과의 토큰 수로 준다, 모르면 NULL)와
# 갈래(--fork-session)가 갈라져 나온 대화. 갈래는 만들 때 이름을 받으므로 chat_titles에 남는다.
_SCHEMA_V11 = """
ALTER TABLE answers ADD COLUMN context_tokens INTEGER;
ALTER TABLE answers ADD COLUMN context_window INTEGER;
ALTER TABLE chat_titles ADD COLUMN parent_session TEXT;
"""

# 답마다 갈래(2026-10-02 사용자 요청): 차례 끝 Claude Code 메시지 ID(--resume-session-at에 쓴다, 그 전 답은 NULL)와
# 갈래가 갈라진 답.
_SCHEMA_V12 = """
ALTER TABLE answers ADD COLUMN cc_message_id TEXT;
ALTER TABLE chat_titles ADD COLUMN fork_answer_id TEXT;
"""

# U5 하이라이트 3색 (UI_PLAN §5 U5): 색 없음(NULL) 또는 c1–c3. 메모 없는 텍스트 주석은 예전 하이라이트(H)이거나
# 메모를 비운 주석이므로 첫 색으로 둔다.
_SCHEMA_V13 = """
ALTER TABLE annotations ADD COLUMN color TEXT;
UPDATE annotations SET color = 'c1'
WHERE comment = '' AND anchor_id IN (SELECT anchor_id FROM anchors WHERE kind = 'text');
"""

# U6 Library·설정 (UI_PLAN §5 U6): 태그(이름은 대소문자를 가리지 않는다), 마지막 열람, 이 PC의 사용자 설정 한 벌(JSON).
_SCHEMA_V14 = """
ALTER TABLE papers ADD COLUMN last_opened_at TEXT;
CREATE TABLE tags (
    tag_id     TEXT PRIMARY KEY,
    owner_id   TEXT NOT NULL,
    name       TEXT NOT NULL COLLATE NOCASE,
    created_at TEXT NOT NULL,
    UNIQUE (owner_id, name)
);
CREATE TABLE paper_tags (
    paper_id TEXT NOT NULL REFERENCES papers (paper_id),
    tag_id   TEXT NOT NULL REFERENCES tags (tag_id),
    PRIMARY KEY (paper_id, tag_id)
);
CREATE INDEX paper_tags_by_tag ON paper_tags (tag_id);
CREATE TABLE preferences (
    owner_id   TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# U7 쪽 번역 (UI_PLAN §5 U7): 쪽·언어마다 문단(원문 글과 문장별 번역, 읽는 차례). 다시 추출해도 글이 같으면 쓴다.
_SCHEMA_V15 = """
CREATE TABLE page_translations (
    version_id  TEXT NOT NULL REFERENCES source_versions (version_id),
    page_index  INTEGER NOT NULL,
    language    TEXT NOT NULL,
    model       TEXT,
    blocks_json TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (version_id, page_index, language)
);
"""

# U7 뒤 사용자 요청 (2026-10-03): 문단의 굵게·기울임 구간과 글꼴 크기(레이아웃 유지 번역이 원문을 따른다).
# 추출기 LAYOUT_VERSION 2와 함께 다시 추출하면 채워진다. 그 전 문단은 빈 구간·NULL이다.
_SCHEMA_V16 = """
ALTER TABLE text_blocks ADD COLUMN styles_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE text_blocks ADD COLUMN font_size REAL;
"""

# 답변 화면(U6)은 대화마다 첫 답을 찾는다. 대화 ID로 찾는 색인이 없으면 대화마다 answers 전체를 훑어 답이 쌓이면 느려졌다
# (2026-10-05: 답 3,900개에서 3.5초 → 0.03초, E2E 데이터 폴더에서 드러남).
_SCHEMA_V17 = """
CREATE INDEX answers_by_session ON answers (chat_session, created_at);
"""

MIGRATIONS = [
    _SCHEMA_V1, _SCHEMA_V2, _SCHEMA_V3, _SCHEMA_V4, _SCHEMA_V5, _SCHEMA_V6, _SCHEMA_V7, _SCHEMA_V8, _SCHEMA_V9, _SCHEMA_V10, _SCHEMA_V11,
    _SCHEMA_V12, _SCHEMA_V13, _SCHEMA_V14, _SCHEMA_V15, _SCHEMA_V16, _SCHEMA_V17,
]


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def migrate(db_path: Path) -> None:
    with closing(connect(db_path)) as connection:
        current = connection.execute("PRAGMA user_version").fetchone()[0]
        if current > len(MIGRATIONS):
            raise RuntimeError(f"DB 스키마 v{current}가 이 버전이 아는 v{len(MIGRATIONS)}보다 새롭습니다: {db_path}")
        for number, script in enumerate(MIGRATIONS[current:], start=current + 1):
            connection.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
