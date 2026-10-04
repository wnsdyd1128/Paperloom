"""U4 탐색 REST (2026-10-02 사용자 결정 D5·D6, IMPL §8): 논문 정보(DOI 자동·고치기)와 본문 제목 목차.

worker 스레드 대신 app.state.parsing.run_next()로 본문 추출을 돌린다(test_parsing과 같다).
"""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "pdf-layout"
EXPECTED = json.loads((FIXTURE_DIR / "text-extraction.json").read_text(encoding="utf-8"))["documents"]
NAVIGATION_DOI = EXPECTED["text-navigation.pdf"]["doi"]


def make_app(data_dir: Path):
    return create_app(Settings(app=AppSettings(mode="test", data_dir=data_dir)))


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def app(data_dir):
    return make_app(data_dir)


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


def paper_of(client: TestClient, paper: dict) -> dict:
    return client.get(f"/api/v1/papers/{paper['paper_id']}").json()


def metadata(paper: dict, **changes) -> dict:
    body = {"title": paper["title"], "authors": paper["authors"], "year": paper["year"], "doi": paper["doi"]}
    return {**body, **changes}


def put_metadata(client: TestClient, paper: dict, body: dict):
    return client.put(f"/api/v1/papers/{paper['paper_id']}/metadata", json=body)


def test_extraction_fills_the_doi_from_the_first_pages(app, client):
    paper = upload(client, "text-navigation.pdf")
    other = upload(client, "text-references.pdf")
    assert paper["doi"] is None
    drain(app)
    assert paper_of(client, paper)["doi"] == NAVIGATION_DOI
    assert paper_of(client, other)["doi"] is None


def test_extraction_keeps_a_doi_the_user_set_or_cleared(app, client):
    paper = upload(client, "text-navigation.pdf")
    assert put_metadata(client, paper, metadata(paper, doi="10.1234/user.set")).status_code == 200
    drain(app)
    assert paper_of(client, paper)["doi"] == "10.1234/user.set"

    # 사용자가 지운 DOI는 다시 추출해도 채우지 않는다
    assert put_metadata(client, paper, metadata(paper_of(client, paper), doi=None)).json()["doi"] is None
    version_id = paper["current_version"]["version_id"]
    assert client.post(f"/api/v1/versions/{version_id}/parse-runs").status_code == 202
    drain(app)
    assert paper_of(client, paper)["doi"] is None


def test_start_removes_markup_from_titles_stored_before(app, client, data_dir):
    """예전에 메타데이터 제목을 그대로 저장한 논문(<underline>…)은 시작할 때 태그를 뺀다. 검색 색인도 바뀐다 (2026-10-03)."""
    paper = upload(client, "text-navigation.pdf")
    drain(app)
    marked = "Flexible <underline>C</underline>ache <underline>B</underline>ehavior Framework"
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection, connection:
        connection.execute("UPDATE papers SET title = ? WHERE paper_id = ?", (marked, paper["paper_id"]))

    make_app(data_dir).state.parsing.prepare()

    assert paper_of(client, paper)["title"] == "Flexible Cache Behavior Framework"
    found = client.get("/api/v1/search", params={"q": '"Cache Behavior"'}).json()["papers"]
    assert [item["paper_id"] for item in found] == [paper["paper_id"]]


def test_start_fills_the_doi_of_papers_extracted_before_without_extracting_again(app, client, data_dir):
    paper = upload(client, "text-navigation.pdf")
    drain(app)
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection, connection:
        connection.execute("UPDATE papers SET doi = NULL")  # DOI 찾기 전에 추출한 논문
        blocks = connection.execute("SELECT COUNT(*) FROM text_blocks").fetchone()[0]
        runs = connection.execute("SELECT COUNT(*) FROM parse_runs").fetchone()[0]

    make_app(data_dir).state.parsing.prepare()

    assert paper_of(client, paper)["doi"] == NAVIGATION_DOI
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection:
        # 다시 추출하지 않는다: 문단 ID가 바뀌면 저장된 답의 문단 근거가 끊긴다
        assert connection.execute("SELECT COUNT(*) FROM parse_runs").fetchone()[0] == runs
        assert connection.execute("SELECT COUNT(*) FROM text_blocks").fetchone()[0] == blocks


def test_metadata_put_replaces_title_authors_year_and_doi(client):
    paper = upload(client, "text-references.pdf")
    body = {"title": "  Cache Navigation Study ", "authors": [" Jun Xiao ", "", "Andy D. Pimentel"], "year": 2022, "doi": " 10.1145/3487581 "}
    response = put_metadata(client, paper, body)

    assert response.status_code == 200, response.text
    saved = response.json()
    assert (saved["title"], saved["authors"], saved["year"], saved["doi"]) == ("Cache Navigation Study", ["Jun Xiao", "Andy D. Pimentel"], 2022, "10.1145/3487581")
    assert paper_of(client, paper) == saved
    # 제목 검색 색인도 바뀐다
    hits = client.get("/api/v1/search", params={"q": "navigation study"}).json()["papers"]
    assert [hit["paper_id"] for hit in hits] == [paper["paper_id"]]


@pytest.mark.parametrize(
    "changes",
    [
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 501},
        {"year": 999},
        {"year": 2101},
        {"doi": "abc"},
        {"doi": "10.12/too-short"},
        {"authors": ["A"] * 101},
        {"authors": ["x" * 301]},
        {"extra": 1},
    ],
)
def test_metadata_put_rejects_bad_values(client, changes):
    paper = upload(client, "text-references.pdf")
    response = put_metadata(client, paper, metadata(paper, **changes))
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_REQUEST"
    assert paper_of(client, paper)["title"] == paper["title"]


def test_metadata_put_needs_every_field_and_a_known_paper(client):
    paper = upload(client, "text-references.pdf")
    assert client.put(f"/api/v1/papers/{paper['paper_id']}/metadata", json={"title": "Only title"}).status_code == 422
    missing = client.put("/api/v1/papers/no-such-paper/metadata", json=metadata(paper))
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")


def test_headings_are_read_from_the_extracted_paragraphs(app, client):
    paper = upload(client, "text-references.pdf")
    version_id = paper["current_version"]["version_id"]
    not_ready = client.get(f"/api/v1/versions/{version_id}/headings")
    assert (not_ready.status_code, not_ready.json()["code"]) == (409, "TEXT_NOT_READY")
    drain(app)

    body = client.get(f"/api/v1/versions/{version_id}/headings").json()
    assert body["version_id"] == version_id
    assert [[item["title"], item["page_index"], item["level"]] for item in body["headings"]] == EXPECTED["text-references.pdf"]["headings"]
    for item in body["headings"]:  # 그 문단의 첫 줄로 간다
        blocks = client.get(f"/api/v1/versions/{version_id}/pages/{item['page_index']}").json()["blocks"]
        [block] = [block for block in blocks if block["block_id"] == item["block_id"]]
        assert item["box"] == block["regions"][0]
    assert client.get("/api/v1/versions/no-such-version/headings").status_code == 404
