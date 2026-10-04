"""논문 제목 검색 REST (IMPL §7.1, G3 S05). 본문 문단은 찾지 않는다(2026-10-01 사용자 결정)."""

import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "pdf-layout"
NAMES = ["text-digital.pdf", "text-mixed.pdf", "text-image-only.pdf"]


def build_library(data_dir: Path) -> tuple[TestClient, dict[str, dict]]:
    """(client, 파일 이름 → 논문). 제목은 'Paperloom text fixture … (synthetic)'다."""
    app = create_app(Settings(app=AppSettings(mode="test", data_dir=data_dir)))
    client = TestClient(app)
    papers = {}
    for name in NAMES:
        response = client.post(
            "/api/v1/papers",
            content=(FIXTURE_DIR / name).read_bytes(),
            headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote(name)},
        )
        papers[name] = response.json()
    while app.state.parsing.run_next():
        pass
    return client, papers


@pytest.fixture(scope="module")
def library(tmp_path_factory) -> tuple[TestClient, dict[str, dict]]:
    """검색만 하는 테스트가 함께 쓴다. 데이터를 바꾸는 테스트는 build_library로 따로 만든다."""
    return build_library(tmp_path_factory.mktemp("search") / "data")


def found(client: TestClient, q: str, **params) -> list[str]:
    return [hit["paper_id"] for hit in client.get("/api/v1/search", params={"q": q, **params}).json()["papers"]]


def test_title_words_find_papers_with_marks(library):
    client, papers = library
    response = client.get("/api/v1/search", params={"q": "synthetic digital"}).json()

    assert [hit["paper_id"] for hit in response["papers"]] == [papers["text-digital.pdf"]["paper_id"]]
    hit = response["papers"][0]
    assert hit["version_id"] == papers["text-digital.pdf"]["current_version"]["version_id"]
    assert {"text": "digital", "match": True} in hit["title"]
    assert "".join(part["text"] for part in hit["title"]) == papers["text-digital.pdf"]["title"]
    assert set(response) == {"query", "papers"}  # 본문 발췌는 돌려주지 않는다


def test_word_beginnings_match(library):
    client, papers = library

    assert set(found(client, "synth")) == {paper["paper_id"] for paper in papers.values()}
    assert found(client, "mix") == [papers["text-mixed.pdf"]["paper_id"]]
    assert found(client, '"image only"') == [papers["text-image-only.pdf"]["paper_id"]]
    assert found(client, '"only image"') == []


@pytest.mark.parametrize("word", ["alphaword", "gammaword", "kappaword", "Introduction"])
def test_body_text_is_not_searched(library, word):
    client, _ = library
    assert found(client, word) == []


@pytest.mark.parametrize(
    "q",
    ['"', '""', "fixture OR nothing", "NOT fixture", "NEAR(fixture", "fixture*", "^fixture", "text:fixture",
     "(fixture", 'fix"ture', "-fixture", "fixture AND", "{title}", "'; DROP TABLE papers; --"],
)
def test_fts_syntax_in_the_query_is_treated_as_text(library, q):
    client, _ = library
    response = client.get("/api/v1/search", params={"q": q})

    assert response.status_code in (200, 422), response.text
    if q == "fixture OR nothing":  # OR는 연산자가 아니라 낱말이다
        assert response.json()["papers"] == []
    assert client.get("/api/v1/papers").json()["papers"]


@pytest.mark.parametrize("params", [{"q": ""}, {"q": "  ...  "}, {"q": '" "'}, {}, {"q": "fixture", "limit": 0},
                                    {"q": "fixture", "limit": 51}, {"q": "x" * 1001}])
def test_invalid_queries_are_rejected(library, params):
    client, _ = library
    response = client.get("/api/v1/search", params=params)

    assert response.status_code == 422
    assert response.json()["code"] in ("INVALID_QUERY", "INVALID_REQUEST")


def test_limit_and_ligature_query(library):
    client, _ = library
    assert len(found(client, "paperloom")) == 3
    assert len(found(client, "paperloom", limit=2)) == 2
    assert len(found(client, "ﬁxture")) == 3  # 질의도 NFKC


def test_only_own_papers_are_searched(tmp_path):
    data_dir = tmp_path / "data"
    client, _ = build_library(data_dir)
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection, connection:
        connection.execute("INSERT INTO papers VALUES ('other-paper', 'someone-else', 'Secretword title', '[]', NULL, NULL, 'other-v', 'now', NULL)")
        connection.execute(
            "INSERT INTO source_versions (version_id, paper_id, sha256, size_bytes, page_count, storage_ref, status, created_at)"
            " VALUES ('other-v', 'other-paper', 'h', 1, 1, 'r', 'INDEXED', 'now')"
        )

    assert client.get("/api/v1/search", params={"q": "secretword"}).json() == {"query": "secretword", "papers": []}
