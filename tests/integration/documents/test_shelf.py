"""U6 서재 (UI_PLAN §5 U6, IMPL §8): 논문 목록의 태그·주석 수·대화 수·마지막 열람, 태그 붙이기, 열람 기록."""

import sqlite3
import uuid
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings

QUAD = [0.1, 0.1, 0.5, 0.1, 0.5, 0.12, 0.1, 0.12]


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def client(data_dir: Path) -> TestClient:
    return TestClient(create_app(Settings(app=AppSettings(mode="test", data_dir=data_dir))))


def upload(client: TestClient, make_pdf, title: str) -> dict:
    response = client.post(
        "/api/v1/papers",
        content=make_pdf(pages=2, title=title),
        headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote(f"{title}.pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


def listed(client: TestClient) -> list[dict]:
    return client.get("/api/v1/papers").json()["papers"]


def by_id(client: TestClient) -> dict[str, dict]:
    return {paper["paper_id"]: paper for paper in listed(client)}


def put_tags(client: TestClient, paper: dict, tags):
    return client.put(f"/api/v1/papers/{paper['paper_id']}/tags", json={"tags": tags})


def test_a_new_paper_has_no_tags_counts_or_opened_time(client, make_pdf):
    paper = upload(client, make_pdf, "Fresh")
    assert (paper["tags"], paper["annotation_count"], paper["conversation_count"], paper["last_opened_at"]) == ([], 0, 0, None)


def test_tags_are_set_per_paper_shared_case_insensitively_and_unused_ones_are_dropped(client, data_dir, make_pdf):
    first, second = upload(client, make_pdf, "First"), upload(client, make_pdf, "Second")

    saved = put_tags(client, first, ["  Scheduling ", "Cache Modeling", "scheduling"])
    assert saved.status_code == 200
    assert saved.json()["tags"] == ["Cache Modeling", "Scheduling"]  # 앞뒤 빈칸을 지우고, 대소문자만 다르면 하나, 이름 차례
    assert put_tags(client, second, ["SCHEDULING", "WCET"]).json()["tags"] == ["Scheduling", "WCET"]  # 있는 태그의 이름을 따른다
    assert put_tags(client, first, []).json()["tags"] == []
    assert by_id(client)[second["paper_id"]]["tags"] == ["Scheduling", "WCET"]
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection:  # 아무 논문에도 없는 태그는 남기지 않는다
        assert [row[0] for row in connection.execute("SELECT name FROM tags ORDER BY name")] == ["Scheduling", "WCET"]


@pytest.mark.parametrize("tags", [[""], ["   "], ["x" * 41], [f"t{n}" for n in range(21)], "Scheduling", [1]])
def test_bad_tags_are_rejected(client, make_pdf, tags):
    paper = upload(client, make_pdf, "Bad tags")
    response = put_tags(client, paper, tags)
    assert (response.status_code, response.json()["code"]) == (422, "INVALID_REQUEST")
    assert by_id(client)[paper["paper_id"]]["tags"] == []


def tag_url(name: str) -> str:
    return f"/api/v1/tags/{quote(name, safe='')}"


def test_a_tag_is_renamed_on_every_paper_and_merges_into_an_existing_tag(client, data_dir, make_pdf):
    """태그 이름 바꾸기 (2026-10-04 사용자 요청): 그 태그가 붙은 모든 논문에서 바뀐다. 대소문자만 바꿀 수 있고, 이미 있는
    다른 태그 이름이면 그 태그로 합친다(둘 다 붙은 논문은 하나)."""
    first, second = upload(client, make_pdf, "First"), upload(client, make_pdf, "Second")
    put_tags(client, first, ["ml", "Cache"])
    put_tags(client, second, ["ml", "Scheduling"])

    assert client.patch(tag_url("ml"), json={"name": "  ML "}).status_code == 204  # 대소문자만
    assert [paper["tags"] for paper in (by_id(client)[first["paper_id"]], by_id(client)[second["paper_id"]])] == [["Cache", "ML"], ["ML", "Scheduling"]]
    assert client.patch(tag_url("ml"), json={"name": "Machine Learning/Systems"}).status_code == 204  # 이름은 대소문자를 가리지 않는다
    assert by_id(client)[first["paper_id"]]["tags"] == ["Cache", "Machine Learning/Systems"]

    # 있는 태그로 합친다: first는 Cache 하나, second는 Cache + Scheduling
    assert client.patch(tag_url("Machine Learning/Systems"), json={"name": "cache"}).status_code == 204
    assert by_id(client)[first["paper_id"]]["tags"] == ["Cache"]
    assert by_id(client)[second["paper_id"]]["tags"] == ["Cache", "Scheduling"]
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection:
        assert [row[0] for row in connection.execute("SELECT name FROM tags ORDER BY name")] == ["Cache", "Scheduling"]


def test_a_tag_is_deleted_from_every_paper_and_unknown_or_bad_names_are_rejected(client, make_pdf):
    """태그 지우기 (2026-10-04 사용자 요청): 모든 논문에서 뗀다(논문은 그대로)."""
    first, second = upload(client, make_pdf, "First"), upload(client, make_pdf, "Second")
    put_tags(client, first, ["Cache", "WCET"])
    put_tags(client, second, ["cache"])
    assert client.delete(tag_url("CACHE")).status_code == 204
    assert [by_id(client)[paper["paper_id"]]["tags"] for paper in (first, second)] == [["WCET"], []]
    assert len(listed(client)) == 2

    for response in (client.delete(tag_url("Cache")), client.patch(tag_url("nothing"), json={"name": "x"})):
        assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")
    for bad in ({"name": "   "}, {"name": "x" * 41}, {"name": "x", "extra": 1}, {}):
        response = client.patch(tag_url("WCET"), json=bad)
        assert (response.status_code, response.json()["code"]) == (422, "INVALID_REQUEST")
    assert by_id(client)[first["paper_id"]]["tags"] == ["WCET"]


def test_tags_need_a_known_paper(client):
    missing = client.put("/api/v1/papers/no-such-paper/tags", json={"tags": ["x"]})
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")


def test_opening_a_paper_records_the_time_and_puts_it_first(client, make_pdf):
    older, newer = upload(client, make_pdf, "Older"), upload(client, make_pdf, "Newer")
    assert [paper["paper_id"] for paper in listed(client)] == [newer["paper_id"], older["paper_id"]]  # 연 적이 없으면 등록한 차례

    assert client.post(f"/api/v1/papers/{older['paper_id']}/opened").status_code == 204
    papers = listed(client)
    assert [paper["paper_id"] for paper in papers] == [older["paper_id"], newer["paper_id"]]  # 최근에 연 것 먼저
    assert papers[0]["last_opened_at"] is not None and papers[1]["last_opened_at"] is None
    assert client.post("/api/v1/papers/no-such-paper/opened").status_code == 404


def test_counts_annotations_and_conversations_about_each_paper(client, make_pdf):
    paper, other = upload(client, make_pdf, "Counted"), upload(client, make_pdf, "Other")
    version_id = paper["current_version"]["version_id"]
    anchor_id = client.post("/api/v1/anchors", json={
        "schema_version": "anchor.v1", "version_id": version_id, "page_index": 0, "quads": [QUAD],
        "quote": "q", "display_quote": None, "prefix": "", "suffix": "",
    }).json()["anchor_id"]
    for comment in ("하나", ""):
        assert client.post("/api/v1/annotations", json={"anchor_id": anchor_id, "comment": comment}).status_code == 201

    def answer(session: str, text: str) -> dict:
        packet_id = client.post("/api/v1/context-packets", json={
            "intent": "ask", "question": text, "anchors": [{"anchor_id": anchor_id}],
        }).json()["packet_id"]
        client.patch(f"/api/v1/context-packets/{packet_id}", json={"status": "HANDED_OFF", "handoff_method": "claude_code"})
        saved = client.post(f"/api/v1/context-packets/{packet_id}/answers", json={"markdown": text, "prompt": text, "session_id": session})
        assert saved.status_code == 201, saved.text
        return saved.json()

    kept, dropped = str(uuid.uuid4()), str(uuid.uuid4())
    answer(kept, "첫 질문")
    answer(kept, "이어 묻기")
    gone = answer(dropped, "버릴 질문")
    counted = by_id(client)[paper["paper_id"]]
    assert (counted["annotation_count"], counted["conversation_count"]) == (2, 2)

    client.delete(f"/api/v1/answers/{gone['answer_id']}")  # 답을 모두 버린 대화는 세지 않는다
    counted = by_id(client)
    assert counted[paper["paper_id"]]["conversation_count"] == 1
    assert (counted[other["paper_id"]]["annotation_count"], counted[other["paper_id"]]["conversation_count"]) == (0, 0)
    assert client.get(f"/api/v1/papers/{paper['paper_id']}").json()["conversation_count"] == 1
