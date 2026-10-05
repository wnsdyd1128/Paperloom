"""서재에서 논문 지우기 (2026-10-05 사용자 요청 "서재에서 논문 삭제하는 건 없어?" → 바로 완전 삭제, 한 편씩).

지우면 원본 PDF와 그 논문의 모든 기록(추출한 본문·검색 색인·원문 위치·주석·문맥·답변·대화·대화 이름·쪽 번역·태그)이
사라지고, 다른 논문은 그대로다. 본문을 추출하는 중(RUNNING)이면 거절하고, 대기 중(QUEUED)이면 그 작업도 함께 지운다.
"""

import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings
from paperloom.documents.block_kinds import NOT_BODY
from paperloom.documents.sentences import sentence_spans

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "pdf-layout"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def app(data_dir):
    return create_app(Settings(app=AppSettings(mode="test", data_dir=data_dir)))


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def upload(client: TestClient, name: str) -> dict:
    response = client.post(
        "/api/v1/papers",
        content=(FIXTURE_DIR / name).read_bytes(),
        headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote(name)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def drain(app) -> None:
    while app.state.parsing.run_next():
        pass


def answered(client: TestClient, anchor_id: str) -> str:
    """브리지가 한 차례를 끝낸 것처럼 packet을 보내고 답을 저장한 대화 ID"""
    packet_id = client.post("/api/v1/context-packets", json={"intent": "explain", "question": "q", "anchors": [{"anchor_id": anchor_id}]}).json()["packet_id"]
    client.patch(f"/api/v1/context-packets/{packet_id}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"})
    session = str(uuid.uuid4())
    assert client.post(f"/api/v1/context-packets/{packet_id}/answers", json={"markdown": "답 [근거 1]", "prompt": "q", "session_id": session}).status_code == 201
    return session


def fill(client: TestClient, paper: dict, tags: list[str]) -> None:
    """사용자가 논문 하나에 남길 수 있는 기록을 모두 만든다."""
    paper_id, version_id = paper["paper_id"], paper["current_version"]["version_id"]
    blocks = client.get(f"/api/v1/versions/{version_id}/pages/0").json()["blocks"]
    u0, v0, u1, v1 = blocks[0]["regions"][0]
    anchor_id = client.post("/api/v1/anchors", json={
        "schema_version": "anchor.v1", "kind": "figure", "version_id": version_id, "page_index": 0,
        "quads": [[u0, v0, u1, v0, u1, v1, u0, v1]], "quote": "", "display_quote": None, "prefix": "", "suffix": "",
    }).json()["anchor_id"]
    assert client.post("/api/v1/annotations", json={"anchor_id": anchor_id, "comment": "메모"}).status_code == 201
    inline = answered(client, anchor_id)
    thread = {"session_id": inline, "paper_id": paper_id, "anchor_id": anchor_id, "kind": "explain", "title": "설명"}
    assert client.post("/api/v1/chat-threads", json=thread).status_code == 201
    sidebar = answered(client, anchor_id)
    assert client.put(f"/api/v1/chat-sessions/{sidebar}/title", json={"paper_id": paper_id, "title": "이름"}).status_code == 200
    translation = {"model": "sonnet", "blocks": [  # 번역할 문단만(쪽 번호 같은 본문 밖 문단은 번역하지 않는다)
        {"block_id": block["block_id"], "sentences": [f"번역 {index}" for index in range(len(sentence_spans(block["text"])))]}
        for block in blocks if sentence_spans(block["text"]) and NOT_BODY.isdisjoint(block["quality_flags"])
    ]}
    assert client.put(f"/api/v1/versions/{version_id}/pages/0/translations/ko", json=translation).status_code == 200
    assert client.put(f"/api/v1/papers/{paper_id}/tags", json={"tags": tags}).status_code == 200


def ids(data_dir: Path, paper_id: str) -> dict[str, list]:
    """그 논문에 딸린 기록의 ID (지우기 전에 모아 두고 지운 뒤 같은 ID로 센다)"""
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection:
        def column(sql: str, *args) -> list:
            return [row[0] for row in connection.execute(sql, args)]

        versions = column("SELECT version_id FROM source_versions WHERE paper_id = ?", paper_id)
        marks = ",".join("?" * len(versions))
        anchors = column(f"SELECT anchor_id FROM anchors WHERE version_id IN ({marks})", *versions)
        packets = column(
            "SELECT packet_id FROM context_packets AS p WHERE EXISTS (SELECT 1 FROM json_each(p.content_json, '$.sources') AS s"
            " WHERE json_extract(s.value, '$.paper_id') = ?)", paper_id,
        )
        return {"versions": versions, "anchors": anchors, "packets": packets, "blocks": column(f"SELECT id FROM text_blocks WHERE version_id IN ({marks})", *versions)}


def counts(data_dir: Path, paper_id: str, owned: dict[str, list]) -> dict[str, int]:
    """표마다 그 논문의 행 수"""
    queries = {
        "papers": ("SELECT count(*) FROM papers WHERE paper_id = ?", [paper_id]),
        "papers_fts": ("SELECT count(*) FROM papers_fts WHERE paper_id = ?", [paper_id]),
        "paper_tags": ("SELECT count(*) FROM paper_tags WHERE paper_id = ?", [paper_id]),
        "chat_threads": ("SELECT count(*) FROM chat_threads WHERE paper_id = ?", [paper_id]),
        "chat_titles": ("SELECT count(*) FROM chat_titles WHERE paper_id = ?", [paper_id]),
    }
    for table, column, key in [
        ("source_versions", "version_id", "versions"), ("parse_runs", "version_id", "versions"), ("pages", "version_id", "versions"),
        ("text_blocks", "version_id", "versions"), ("page_translations", "version_id", "versions"), ("anchors", "version_id", "versions"),
        ("annotations", "anchor_id", "anchors"), ("context_packets", "packet_id", "packets"), ("answers", "packet_id", "packets"),
    ]:
        queries[table] = (f"SELECT count(*) FROM {table} WHERE {column} IN ({','.join('?' * len(owned[key]))})", owned[key])
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection:
        return {table: connection.execute(sql, args).fetchone()[0] for table, (sql, args) in queries.items()}


def fts_hits(data_dir: Path, word: str) -> int:
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection:
        return connection.execute("SELECT count(*) FROM text_blocks_fts WHERE text_blocks_fts MATCH ?", (f'"{word}"',)).fetchone()[0]


def tags(data_dir: Path) -> set[str]:
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection:
        return {row[0] for row in connection.execute("SELECT name FROM tags")}


def test_deleting_a_paper_removes_its_file_and_every_record_but_keeps_other_papers(app, client, data_dir):
    gone, kept = upload(client, "text-navigation.pdf"), upload(client, "text-digital.pdf")
    drain(app)
    fill(client, gone, ["공유", "지울 논문만"])
    fill(client, kept, ["공유"])
    gone_ids, kept_ids = ids(data_dir, gone["paper_id"]), ids(data_dir, kept["paper_id"])
    kept_before = counts(data_dir, kept["paper_id"], kept_ids)
    assert all(counts(data_dir, gone["paper_id"], gone_ids).values())  # 지울 논문은 표마다 기록이 있다
    source = data_dir / "sources" / f"{gone['current_version']['version_id']}.pdf"
    assert source.is_file()
    gone_words = {w for b in client.get(f"/api/v1/versions/{gone['current_version']['version_id']}/pages/0").json()["blocks"] for w in b["text"].split()}
    kept_words = {w for p in range(3) for b in client.get(f"/api/v1/versions/{kept['current_version']['version_id']}/pages/{p}").json()["blocks"] for w in b["text"].split()}
    word = next(w for w in sorted(gone_words - kept_words) if w.isalpha() and len(w) > 4)
    assert fts_hits(data_dir, word) > 0

    response = client.delete(f"/api/v1/papers/{gone['paper_id']}")

    assert response.status_code == 204
    assert counts(data_dir, gone["paper_id"], gone_ids) == {table: 0 for table in kept_before}
    assert counts(data_dir, kept["paper_id"], kept_ids) == kept_before
    assert fts_hits(data_dir, word) == 0  # 본문 검색 색인에서도 빠졌다
    assert not source.exists()
    assert (data_dir / "sources" / f"{kept['current_version']['version_id']}.pdf").is_file()
    assert tags(data_dir) == {"공유"}  # 지운 논문에만 있던 태그는 없어진다
    assert client.get(f"/api/v1/papers/{gone['paper_id']}").status_code == 404
    assert [paper["paper_id"] for paper in client.get("/api/v1/papers").json()["papers"]] == [kept["paper_id"]]
    assert client.delete(f"/api/v1/papers/{gone['paper_id']}").status_code == 404  # 다시 지우면 없다


def test_a_paper_cannot_be_deleted_while_its_text_is_being_extracted(app, client, data_dir):
    paper = upload(client, "text-navigation.pdf")
    version_id = paper["current_version"]["version_id"]
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection, connection:
        connection.execute("UPDATE parse_runs SET status = 'RUNNING' WHERE version_id = ?", (version_id,))

    response = client.delete(f"/api/v1/papers/{paper['paper_id']}")

    assert response.status_code == 409
    assert response.json()["code"] == "TEXT_EXTRACTION_RUNNING"
    assert client.get(f"/api/v1/papers/{paper['paper_id']}").status_code == 200
    assert (data_dir / "sources" / f"{version_id}.pdf").is_file()


def test_a_paper_waiting_for_extraction_is_deleted_with_its_queued_run(app, client, data_dir):
    paper = upload(client, "text-navigation.pdf")  # 추출 작업은 아직 대기 중(QUEUED)

    assert client.delete(f"/api/v1/papers/{paper['paper_id']}").status_code == 204
    assert app.state.parsing.run_next() is False  # 대기 중이던 작업도 함께 지웠다
    assert client.get("/api/v1/papers").json()["papers"] == []
