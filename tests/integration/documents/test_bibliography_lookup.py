"""서지 조회 (2026-11-16 사용자 결정, documents.bibliography_lookup): 본문 추출이 끝난 논문의 비어 있는 저자·연도를 DOI·arXiv 번호로
물어 채운다. 네트워크 대신 가짜 fetch를 쓰고, worker 스레드 대신 run_pending()을 직접 부른다(test_navigation과 같다)."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, MetadataSettings, Settings
from paperloom.documents import bibliography
from paperloom.documents.bibliography import Record
from paperloom.documents.bibliography_lookup import BibliographyService

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "pdf-layout"
NAVIGATION_DOI = json.loads((FIXTURE_DIR / "text-extraction.json").read_text(encoding="utf-8"))["documents"]["text-navigation.pdf"]["doi"]
UNTITLED_ARXIV = "2401.01234"  # text-untitled.pdf 왼쪽 여백의 세로 도장 arXiv:2401.01234v2
RECORD = Record(["Ada Lovelace", "Alan Turing"], 2022)


class FakeFetch:
    def __init__(self, answers: dict) -> None:
        self.answers = answers
        self.asked: list[tuple[str, str]] = []

    def __call__(self, kind: str, value: str) -> Record | None:
        self.asked.append((kind, value))
        answer = self.answers.get((kind, value))
        if isinstance(answer, Exception):
            raise answer
        return answer


def make_app(data_dir: Path, lookup: bool = False):
    return create_app(Settings(app=AppSettings(mode="test", data_dir=data_dir), metadata=MetadataSettings(lookup=lookup)))


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


def lookup(data_dir: Path, fetch: FakeFetch) -> int:
    return BibliographyService(data_dir / "paperloom.sqlite3", fetch=fetch, pause_seconds=0).run_pending()


def test_lookup_fills_empty_authors_and_year_once_extraction_is_done(app, client, data_dir):
    paper = upload(client, "text-navigation.pdf")
    plain = upload(client, "text-references.pdf")  # DOI도 arXiv 번호도 없다
    fetch = FakeFetch({("doi", NAVIGATION_DOI): RECORD})
    assert lookup(data_dir, fetch) == 0  # 추출 전에는 DOI·첫 쪽을 모른다
    drain(app)

    assert lookup(data_dir, fetch) == 2
    assert fetch.asked == [("doi", NAVIGATION_DOI)]
    saved = paper_of(client, paper)
    assert (saved["authors"], saved["year"]) == (RECORD.authors, RECORD.year)
    assert (paper_of(client, plain)["authors"], paper_of(client, plain)["year"]) == ([], None)
    # 한 번 물은 논문은 다시 묻지 않는다
    assert lookup(data_dir, fetch) == 0
    assert len(fetch.asked) == 1


def test_lookup_reads_the_arxiv_number_from_the_turned_margin_stamp(app, client, data_dir):
    paper = upload(client, "text-untitled.pdf")
    drain(app)
    fetch = FakeFetch({("arxiv", UNTITLED_ARXIV): Record(["Grace Hopper"], 2024)})
    assert lookup(data_dir, fetch) == 1
    assert fetch.asked == [("arxiv", UNTITLED_ARXIV)]
    assert (paper_of(client, paper)["authors"], paper_of(client, paper)["year"]) == (["Grace Hopper"], 2024)


def test_lookup_fills_only_what_is_empty_and_never_a_paper_the_user_edited(app, client, data_dir):
    kept = upload(client, "text-navigation.pdf")
    edited = upload(client, "text-untitled.pdf")
    body = {**{key: edited[key] for key in ("title", "authors", "doi")}, "year": None}
    assert client.put(f"/api/v1/papers/{edited['paper_id']}/metadata", json=body).status_code == 200  # 저자·연도를 비운 채 고쳤다
    drain(app)
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection, connection:
        connection.execute("UPDATE papers SET year = 2019 WHERE paper_id = ?", (kept["paper_id"],))  # 연도만 있던 논문
    fetch = FakeFetch({("doi", NAVIGATION_DOI): RECORD, ("arxiv", UNTITLED_ARXIV): RECORD})

    assert lookup(data_dir, fetch) == 1
    assert fetch.asked == [("doi", NAVIGATION_DOI)]
    assert (paper_of(client, kept)["authors"], paper_of(client, kept)["year"]) == (RECORD.authors, 2019)
    assert (paper_of(client, edited)["authors"], paper_of(client, edited)["year"]) == ([], None)


def test_a_network_error_leaves_the_paper_to_ask_again(app, client, data_dir):
    paper = upload(client, "text-navigation.pdf")
    drain(app)
    assert lookup(data_dir, FakeFetch({("doi", NAVIGATION_DOI): OSError("offline")})) == 0
    assert paper_of(client, paper)["authors"] == []

    assert lookup(data_dir, FakeFetch({("doi", NAVIGATION_DOI): RECORD})) == 1
    assert paper_of(client, paper)["authors"] == RECORD.authors


def test_an_unknown_doi_is_recorded_and_not_asked_again(app, client, data_dir):
    paper = upload(client, "text-navigation.pdf")
    drain(app)
    fetch = FakeFetch({})
    assert lookup(data_dir, fetch) == 1
    assert lookup(data_dir, fetch) == 0
    assert fetch.asked == [("doi", NAVIGATION_DOI)]
    assert (paper_of(client, paper)["authors"], paper_of(client, paper)["year"]) == ([], None)


def test_the_app_asks_after_extraction_only_when_lookup_is_on(monkeypatch, tmp_path):
    assert make_app(tmp_path / "off").state.bibliography is None  # 시험·E2E 설정은 밖으로 나가지 않는다

    woken = []
    monkeypatch.setattr(BibliographyService, "notify", lambda self: woken.append(True))
    monkeypatch.setattr(bibliography, "fetch", FakeFetch({("doi", NAVIGATION_DOI): RECORD}))
    app = make_app(tmp_path / "on", lookup=True)
    client = TestClient(app)
    paper = upload(client, "text-navigation.pdf")
    drain(app)

    assert woken == [True]  # 추출 결과를 저장한 뒤 깨운다
    assert app.state.bibliography.run_pending() == 1
    assert paper_of(client, paper)["year"] == RECORD.year
