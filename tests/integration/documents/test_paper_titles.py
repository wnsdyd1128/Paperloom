"""메타데이터 제목이 없는 논문의 제목 (2026-10-05 사용자 요청 "등록 시에 파일 명이 아닌 해당 논문의 이름으로 해줘").

등록할 때 첫 쪽에서 제목을 찾는다(text-untitled.pdf: 메타데이터 제목 없음, 왼쪽 여백에 제목보다 큰 세로 도장). 예전에 파일
이름으로 등록한 논문(빈칸 없는 제목)은 서버를 시작할 때와 본문을 추출한 뒤 저장된 첫 쪽에서 고친다. 사용자가 고친
제목(빈칸이 있다)은 그대로 둔다.
"""

import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from paperloom.bootstrap.app import create_app
from paperloom.bootstrap.config import AppSettings, Settings

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "pdf-layout"
TITLE = "A Synthetic Study of Woven Paper Titles for Readers Without Metadata"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


def make_app(data_dir: Path):
    return create_app(Settings(app=AppSettings(mode="test", data_dir=data_dir)))


def upload(client: TestClient, name: str, filename: str) -> dict:
    response = client.post(
        "/api/v1/papers",
        content=(FIXTURE_DIR / name).read_bytes(),
        headers={"Content-Type": "application/pdf", "X-Paperloom-Filename": quote(filename)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def drain(app) -> None:
    while app.state.parsing.run_next():
        pass


def set_title(data_dir: Path, paper_id: str, title: str) -> None:
    with closing(sqlite3.connect(data_dir / "paperloom.sqlite3")) as connection, connection:
        connection.execute("UPDATE papers SET title = ? WHERE paper_id = ?", (title, paper_id))


def test_a_paper_without_title_metadata_is_registered_with_the_title_on_its_first_page(data_dir):
    client = TestClient(make_app(data_dir))

    paper = upload(client, "text-untitled.pdf", "2401.01234v2.pdf")

    assert paper["title"] == TITLE
    hits = client.get("/api/v1/search", params={"q": "woven readers"}).json()["papers"]
    assert [hit["paper_id"] for hit in hits] == [paper["paper_id"]]  # 제목 검색에도 쓰인다


def test_titles_registered_from_file_names_are_fixed_at_start_and_after_extraction(data_dir):
    app = make_app(data_dir)
    client = TestClient(app)
    old = upload(client, "text-untitled.pdf", "2401.01234v2.pdf")
    drain(app)
    set_title(data_dir, old["paper_id"], "2401.01234v2")  # 이 기능 전에 파일 이름으로 등록한 논문
    edited = upload(client, "text-digital.pdf", "digital.pdf")
    drain(app)
    set_title(data_dir, edited["paper_id"], "My Own Name")  # 사용자가 고친 제목

    restarted = make_app(data_dir)
    restarted.state.parsing.prepare()  # 서버 시작(lifespan)이 부른다
    restarted_client = TestClient(restarted)
    assert restarted_client.get(f"/api/v1/papers/{old['paper_id']}").json()["title"] == TITLE
    assert restarted_client.get(f"/api/v1/papers/{edited['paper_id']}").json()["title"] == "My Own Name"

    # 등록 때 첫 쪽을 읽지 못해 파일 이름이 되었어도 본문 추출이 끝나면 고친다
    set_title(data_dir, old["paper_id"], "2401.01234v2")
    version_id = old["current_version"]["version_id"]
    assert restarted_client.post(f"/api/v1/versions/{version_id}/parse-runs").status_code == 202
    drain(restarted)
    assert restarted_client.get(f"/api/v1/papers/{old['paper_id']}").json()["title"] == TITLE
